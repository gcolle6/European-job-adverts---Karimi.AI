"""Try the API on your own CSV, with nothing to install but `requests`.

    pip install requests
    python try_api.py adverts.csv --url https://karimi-api-....run.app --key <key>

Reads your CSV, sends the postings in batches of 200 to /v1/process, and
writes next to it `<name>_normalised.csv`: your rows, every column kept, with
the added ones (role, counts, groups, topics), one row per advert.

With --per-requirement, also `<name>_requirements.csv`: one row per
requirement found, for counting or pivoting by requirement, which the joined
columns of the first file do not allow. A short summary is printed at the end.

Columns it looks for (case does not matter): `must_have` (required), `id`,
`title` (or `job_title`, `job_title_english`), `language`, `must_have_english`.
Pass other names with --col-must-have, --col-id, --col-title.

`must_have` can be a JSON list (`["3+ years of Python", "Fluent English"]`),
or one requirement per line, or items separated by ` | ` or `;`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import requests

BATCH = 200
ADDED = ["title_role", "title_level", "title_extra", "title_name", "title_match", "n_items", "n_requirements",
         "n_counted", "n_known", "n_group", "n_topic", "n_nuovo", "n_items_kept_whole", "req_groups",
         "req_topics", "rules_version", "dict_version", "karimi_job"]


def split_items(cell: str) -> list[str]:
    cell = (cell or "").strip()
    if not cell:
        return []
    if cell.startswith("["):
        try:
            v = json.loads(cell)
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
        except ValueError:
            pass
    for sep in ("\n", " | ", ";"):
        if sep in cell:
            return [x.strip(" -•*\t") for x in cell.split(sep) if x.strip(" -•*\t")]
    return [cell]


def find_col(columns: list[str], wanted: list[str], given: str | None) -> str | None:
    if given:
        return given
    low = {c.lower(): c for c in columns}
    return next((low[w] for w in wanted if w in low), None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv")
    p.add_argument("--url", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--col-must-have")
    p.add_argument("--col-id")
    p.add_argument("--col-title")
    p.add_argument("--no-translate", action="store_true", help="split non-English items as written")
    p.add_argument("--limit", type=int, help="only the first N rows")
    p.add_argument("--per-requirement", action="store_true", help="also write one row per requirement")
    a = p.parse_args(argv)

    src = Path(a.csv)
    with src.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("empty CSV")
    cols = list(rows[0].keys())
    c_mh = find_col(cols, ["must_have", "must have", "musthave", "requirements"], a.col_must_have)
    c_id = find_col(cols, ["id", "_id", "job_id", "posting_id"], a.col_id)
    c_title = find_col(cols, ["title", "job_title_english", "job_title", "job title"], a.col_title)
    c_lang = find_col(cols, ["language", "lang"], None)
    c_en = find_col(cols, ["must_have_english"], None)
    if not c_mh:
        sys.exit(f"no must_have column found among {cols}; pass --col-must-have")
    rows = rows[: a.limit] if a.limit else rows
    print(f"{len(rows)} rows; must_have={c_mh!r} id={c_id!r} title={c_title!r}")

    url, headers = a.url.rstrip("/"), {"X-API-Key": a.key}
    h = requests.get(f"{url}/health", timeout=60).json()
    print(f"API rules {h['rules_version']}, dictionary {h['dict_version']}")

    out_rows, req_rows, jobs, report = [], [], [], None
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        postings = []
        for i, r in enumerate(chunk):
            post = {"id": r[c_id] if c_id and r.get(c_id) else str(start + i + 1),
                    "must_have": split_items(r[c_mh])}
            if c_title and r.get(c_title):
                post["title"] = r[c_title]
            if c_lang and r.get(c_lang):
                post["language"] = r[c_lang]
            if c_en and r.get(c_en):
                en = split_items(r[c_en])
                if len(en) == len(post["must_have"]):
                    post["must_have_english"] = en
            postings.append(post)
        resp = requests.post(f"{url}/v1/process", headers=headers, timeout=3600,
                             json={"postings": postings, "translate": not a.no_translate})
        if resp.status_code != 200:
            sys.exit(f"HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        jobs.append(body["job"])
        report = body["report"]
        # the per-posting table the API wrote for this batch, keyed by id
        added = {r["id"]: r for r in csv.DictReader(
            requests.get(body["files"]["postings"], headers=headers, timeout=600).text.splitlines())}
        if a.per_requirement:
            req_text = requests.get(body["files"]["requirements"], headers=headers, timeout=600).text
            req_rows += list(csv.DictReader(req_text.splitlines()))
        for r, post in zip(chunk, postings):
            add = added.get(str(post["id"]), {})
            out_rows.append({**r, **{k: add.get(k, "") for k in ADDED if k != "karimi_job"}, "karimi_job": body["job"]})
        print(f"  {min(start + BATCH, len(rows))}/{len(rows)} rows, run {body['job']}, "
              f"report {report['overall']}, {report['summary']['requirements']} requirements")

    stem = src.with_suffix("")
    with open(f"{stem}_normalised.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + ADDED, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    written = [f"{stem}_normalised.csv"]
    if a.per_requirement and req_rows:
        with open(f"{stem}_requirements.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(req_rows[0].keys()))
            w.writeheader()
            w.writerows(req_rows)
        written.append(f"{stem}_requirements.csv")
    n_req = sum(int(r.get("n_requirements") or 0) for r in out_rows)
    print(f"written: {', '.join(written)}")
    print(f"{len(out_rows)} adverts -> {n_req} requirements; runs {', '.join(jobs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
