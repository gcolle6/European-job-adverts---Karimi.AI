"""An outside caller, by API.md only: sample N postings, send them as ONE job, wait, fetch.

    python "New project/external_job.py" software_data_missing_from_ids_used.json \
        "New project/output/new_postings/batch_03" --n 1000 --seed 20261115 --offset 2000
    python "New project/external_job.py" ... --job <id>      # a job already run: fetch and wait for its check
    python "New project/external_job.py" x "New project/output/new_postings/batch_01/retest_0.4.6" \n        --postings "New project/output/new_postings/batch_01/postings.jsonl" --retest-of <job of batch 1>

A retest (2026-11-19, every four batches) sends a batch's own postings.jsonl
again under today's rules; the site shows it on the original's row.

Batch k is offset (k-1)*1000 of one shuffled order (seed 20261115), the
batches of the new postings since 2026-11-15; each batch's errors are fixed
before the next one measures (`PIANO_SVILUPPO.md`, the cycle per batch).

Only `requests` and the standard library: nothing from karimi_normalise.
The key comes from KARIMI_API_KEY, never from the command line or the output.
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

URL = "https://karimi-api-166523545713.europe-west1.run.app"
EXTRA = ("company", "country", "company_industry", "seniority", "work_type")


def log(out: Path, **kw) -> None:
    kw["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = json.dumps(kw, ensure_ascii=False)
    print(line, flush=True)
    with open(out / "client_log.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(url: str, timeout: int, **kw) -> requests.Response:
    """GET with retries: on 2026-11-16 one signed-URL download broke on an SSL EOF
    after a 25-minute job had finished, and the client died with the results unread."""
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(10 * 2 ** attempt)


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("export")
    a.add_argument("out")
    a.add_argument("--n", type=int, default=1000)
    a.add_argument("--offset", type=int, default=0)
    a.add_argument("--seed", type=int, default=20261115)
    a.add_argument("--job", help="a job already run: only fetch its files and wait for its check")
    a.add_argument("--postings", help="send this postings.jsonl as it is, instead of sampling the export")
    a.add_argument("--retest-of", help="the job these postings first ran as: a retest")
    a = a.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    H = {"X-API-Key": os.environ["KARIMI_API_KEY"]}
    if a.job:
        log(out, step="resumed", job=a.job)
        return fetch(out, H, a.job, time.time())

    if a.postings:
        (out / "postings.jsonl").write_bytes(Path(a.postings).read_bytes())
        log(out, step="input", postings=sum(1 for x in open(a.postings, encoding="utf-8") if x.strip()),
            source=a.postings, retest_of=a.retest_of)
        return send(out, H, {"retest_of": a.retest_of} if a.retest_of else {})
    rows = [r for r in json.load(open(a.export, encoding="utf-8")) if (r.get("must_have") or "").strip()]
    random.Random(a.seed).shuffle(rows)      # one fixed order: batch k is rows[k*n:(k+1)*n]
    batch = rows[a.offset:a.offset + a.n]
    with open(out / "postings.jsonl", "w", encoding="utf-8") as f:
        for r in batch:
            p = {"id": r["id"], "title": r.get("job_title_english") or r.get("job_title_original") or "",
                 "must_have": [x.strip(" -•*\t") for x in r["must_have"].split("\n") if x.strip(" -•*\t")]}
            p.update({k: r.get(k) or "" for k in EXTRA})
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    log(out, step="input", postings=len(batch), items=sum(len(r["must_have"].split("\n")) for r in batch),
        offset=a.offset, seed=a.seed)
    return send(out, H, {})


def send(out: Path, H: dict, opts: dict) -> int:
    health = requests.get(f"{URL}/health", timeout=60).json()
    log(out, step="health", **health)

    job = requests.post(f"{URL}/v1/jobs", headers=H, json=opts, timeout=120)
    job.raise_for_status()
    job = job.json()
    jid = job["job"]
    log(out, step="created", job=jid)
    up = job["upload"]
    r = requests.put(up["url"], headers=up.get("headers") or {}, data=open(out / "postings.jsonl", "rb"), timeout=600)
    log(out, step="uploaded", status=r.status_code)
    r.raise_for_status()
    r = requests.post(f"{URL}/v1/jobs/{jid}/start", headers=H, timeout=120)
    log(out, step="started", status=r.status_code)
    r.raise_for_status()

    t0, last = time.time(), None
    while True:
        time.sleep(60)
        try:
            s = requests.get(f"{URL}/v1/jobs/{jid}", headers=H, timeout=120).json()
        except requests.RequestException as e:
            log(out, step="poll_error", error=type(e).__name__)
            continue
        state = (s.get("state"), s.get("postings_done"))
        if state != last:
            log(out, step="status", state=s.get("state"), done=s.get("postings_done"),
                total=s.get("postings_total"), minutes=round((time.time() - t0) / 60, 1))
            last = state
        if s.get("state") in ("done", "failed"):
            break
        if time.time() - t0 > 3 * 3600:
            log(out, step="gave_up")
            return 1
    if s.get("state") != "done":
        log(out, step="failed", status=s)
        return 1
    return fetch(out, H, jid, t0)


def fetch(out: Path, H: dict, jid: str, t0: float) -> int:
    res = get(f"{URL}/v1/jobs/{jid}/result", 120, headers=H).json()
    (out / "results.jsonl").write_bytes(get(res["results"], 600).content)
    (out / "report.json").write_bytes(get(res["report"], 120).content)
    (out / "postings.csv").write_bytes(get(res["postings"], 600).content)
    (out / "requirements.csv").write_bytes(get(res["requirements"], 600).content)
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    log(out, step="fetched", files=sorted(p.name for p in out.iterdir()),
        overall=rep.get("overall") or (rep.get("report") or {}).get("overall"))

    # the check comes a few minutes after `done` (API.md): wait for it like a caller would
    for _ in range(60):
        res = get(f"{URL}/v1/jobs/{jid}/result", 120, headers=H).json()
        if res.get("check"):
            (out / "check.json").write_bytes(get(res["check"], 120).content)
            c = json.loads((out / "check.json").read_text(encoding="utf-8"))
            log(out, step="checked", overall=c.get("overall"), minutes=round((time.time() - t0) / 60, 1))
            return 0
        time.sleep(60)
    log(out, step="no_check_after_an_hour")
    return 1


if __name__ == "__main__":
    sys.exit(main())
