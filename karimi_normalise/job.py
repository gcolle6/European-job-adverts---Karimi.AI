"""One large run, start to finish: the Cloud Run Job behind `POST /v1/jobs/{id}/start`.

    python -m karimi_normalise.job --job <id>        # or KARIMI_JOB_ID=<id>

Reads `<id>/input.jsonl` from the store (`store.py`), runs `process` on it
CHUNK postings at a time, appends each posting to `<id>/results.jsonl` and
keeps `<id>/status.json` current, then writes `<id>/report.json`, the run
report over the WHOLE job, and the two CSV tables (`exports.py`).

Why a job and not a request: a Cloud Run request ends at 60 minutes, and
100,000 requirements (~50,000 items) take about an hour. Measured on Cloud
Run, 4 CPUs, 2026-11-06: 2,247 items in 172 s, 28% of them translated, so
1.3 minutes per 1,000 items. (A laptop measurement the day before gave 8.1,
taken while a Docker build ran beside it: not the number to plan with.) A
job runs until it is done (up to 24 hours) and costs nothing while none runs.

Chunks keep memory flat and make progress visible. The result is the same as
one `process` call over everything: translation is cached per item within the
job, and the report is rebuilt from all postings at the end.

The log says how many and how long, never what: one `karimi_timing` line per
chunk (postings, items, seconds), no requirement text.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import Dictionary, check, exports, process
from .metrics import run_report
from .store import jf, now, open_store, read_json, write_json
from .versions import RULES_VERSION

CHUNK = 500


def _status(store, job: str, **change) -> dict:
    s = read_json(store, jf(job, "status.json")) or {"job": job}
    s.update(change, updated=now())
    write_json(store, jf(job, "status.json"), s)
    return s


def run(job: str, store=None, dictionary=None) -> dict:
    store = store or open_store()
    s = read_json(store, jf(job, "status.json")) or {}
    try:
        d = dictionary or Dictionary(os.environ["KARIMI_DICT"])
        with store.open_read(jf(job, "input.jsonl")) as f:
            postings = [json.loads(line) for line in f if line.strip()]
        _status(store, job, state="running", started=now(), postings_total=len(postings), postings_done=0,
                rules_version=RULES_VERSION, dict_version=d.version)
        check._log("INFO", event="karimi_job_start", job=job, postings=len(postings))
        runs, titles, results, t0 = [], [], [], time.time()
        with store.open_write(jf(job, "results.jsonl")) as out:
            for i in range(0, len(postings), CHUNK):
                t1 = time.time()
                part = process(postings[i:i + CHUNK], d, translate=s.get("translate", True))
                for p in part["postings"]:
                    line = {"id": p["id"], "requirements": [r.to_dict() for r in p["requirements"]],
                            "title": p["title"].to_dict() if p["title"] else None}
                    out.write(json.dumps(line, ensure_ascii=False) + "\n")
                    results.append(line)
                    runs.append(p["requirements"])
                    titles += [p["title"]] if p["title"] else []
                done = min(i + CHUNK, len(postings))
                _status(store, job, postings_done=done)
                check._log("INFO", event="karimi_timing", job=job, postings=done - i,
                           items=sum(len(p.get("must_have") or []) for p in postings[i:done]),
                           seconds=round(time.time() - t1, 1), done=done, total=len(postings))
        write_json(store, jf(job, "report.json"), run_report(runs, titles, d))
        req_csv, post_csv = exports.tables(postings, results)
        store.write_text(jf(job, "requirements.csv"), req_csv)
        store.write_text(jf(job, "postings.csv"), post_csv)
        out = _status(store, job, state="done", finished=now(), seconds=round(time.time() - t0, 1))
        check._log("INFO", event="karimi_job_done", job=job, postings=len(postings),
                   requirements=sum(len(r) for r in runs), seconds=out["seconds"])
        after(job, store)
        return out
    except Exception as e:  # the status must say it failed, or the caller waits for ever
        _status(store, job, state="failed", finished=now(), error=f"{type(e).__name__}: {e}")
        check._log("ERROR", event="karimi_job_failed", job=job, error=type(e).__name__)
        after(job, store)
        raise


def after(job: str, store) -> None:
    """The check (`check.py`). With `KARIMI_RUN_CHECK` set it is its own Cloud Run
    Job, which carries the judge; otherwise it runs here, with the judge only if
    `KARIMI_JUDGE_URL` points at one. A check that fails never fails the run."""
    try:
        name = os.environ.get("KARIMI_RUN_CHECK")
        if name:
            check.start_cloud_job(name, job)
        else:
            check.check(job, store, judge_url=os.environ.get("KARIMI_JUDGE_URL"))
    except Exception as e:  # noqa: BLE001
        check._log("ERROR", event="karimi_check_failed", job=job, error=type(e).__name__)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--job", default=os.environ.get("KARIMI_JOB_ID"))
    args = p.parse_args(argv)
    if not args.job:
        sys.exit("no job id: --job or KARIMI_JOB_ID")
    print(json.dumps(run(args.job)))


if __name__ == "__main__":
    main()
