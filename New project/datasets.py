"""The postings the splitter is built on, and the ones it is TESTED on.

Decided 2026-10-30: the splitter must work on `must_have` text nobody has seen
yet, so every rule is a grammatical pattern, and every change is accepted only
if it also holds on postings that were never read while writing rules.

The project uses `software_data_europe.json` only (decided 2026-10-30; the
SALES_BD export is out of scope). It is split once, frozen in `test_sets.json`:

* ``software_dev``     — rules are developed here; samples may be read.
* ``software_holdout`` — the most recent 15% of postings (by `created_at`, read
  from the older export that carries dates). The closest stand-in for future
  postings. Never read from 2026-10-30 on. ⚠️ Not pristine: random samples of
  the whole export were read before that date.

    python "New project/datasets.py"   # freeze the split (refuses to overwrite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346"
SOFTWARE = DATA / "software_data_europe.json"
SOFTWARE_DATED = DATA / "europe_jobs_SOFTWARE_DATA.json"
FROZEN = Path(__file__).resolve().parent / "test_sets.json"

SEED = 20261030
HOLDOUT_SHARE = 0.15


def _software_rows() -> list[dict]:
    return json.loads(SOFTWARE.read_text(encoding="utf-8"))


def freeze() -> dict:
    if FROZEN.exists():
        sys.exit(f"{FROZEN} exists: the split is frozen and must not be redrawn")
    dated = {r["vacancy_id"]: r["created_at"]
             for r in json.loads(SOFTWARE_DATED.read_text(encoding="utf-8"))}
    soft = sorted((dated[r["_id"]], r["_id"]) for r in _software_rows() if r["_id"] in dated)
    holdout = sorted(i for _, i in soft[-round(len(soft) * HOLDOUT_SHARE):])
    out = {"seed": SEED, "software_holdout": holdout,
           "software_holdout_from": soft[-len(holdout)][0]}
    FROZEN.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load(name: str) -> list[dict]:
    """Rows of one set, each with `_id` and a list `must_have`."""
    hold = set(json.loads(FROZEN.read_text(encoding="utf-8"))["software_holdout"])
    rows = _software_rows()
    if name == "software_holdout":
        return [r for r in rows if r["_id"] in hold]
    if name == "software_dev":
        return [r for r in rows if r["_id"] not in hold]
    if name == "software":
        return rows
    raise ValueError(name)


if __name__ == "__main__":
    f = freeze()
    print(f"software holdout: {len(f['software_holdout']):,} postings created from "
          f"{f['software_holdout_from']}")
