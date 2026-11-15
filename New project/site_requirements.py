"""The data behind the site's explorer, from the export alone: the local build and the base for GCP.

    python "New project/site_requirements.py" "../karimi-normalise-site/public/data/explore"

Writes the explorer's files from the August export's adverts (the batch,
`must_have_atoms.parquet` and `titles.parquet`), and `output/explore_base.jsonl`,
the same adverts as the store keeps them. Uploaded to `explore/base.jsonl` with
the dictionary, it is what the check job on Cloud Run adds every passing run to
(`karimi_normalise/explore.py`, since 2026-11-15). The site reads the API's
`/v1/explore`; the files written here are its fallback when the API is silent.

The counting rules, the floors and the five charts are in `explore.py`: one
code path for the local build and the live one.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi_normalise import explore  # noqa: E402
from site_categories import categorise  # noqa: E402

OUT = HERE / "output"
EXPORT = HERE.parent / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"


def main(dest: str) -> None:
    rows, dropped = explore.base_rows(OUT, EXPORT)
    (OUT / "explore_base.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                            encoding="utf-8")
    print(f"{len(rows)} adverts, {sum(len(r['r']) for r in rows)} requirements kept; dropped {dict(dropped)}")
    # the project's local model names the categories when it is running (`categories.py`)
    judge = os.environ.get("KARIMI_JUDGE_URL")
    index, reqs = explore.aggregate(rows, lambda names, spaces: categorise(names, spaces, judge_url=judge),
                                    {"what": explore.what(len(rows), 0, 0),
                                     "from": {"export": len(rows), "runs": 0, "run_jobs": 0}})

    base = Path(dest)
    (base / "req").mkdir(parents=True, exist_ok=True)
    for old in (base / "req").glob("*.json"):
        old.unlink()
    (base / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for r in reqs:
        (base / "req" / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")),
                                                     encoding="utf-8")
    size = sum(f.stat().st_size for f in (base / "req").glob("*.json"))
    print(f"{len(reqs)} requirements -> {base / 'index.json'} ({(base / 'index.json').stat().st_size / 1024:.0f} KB), "
          f"req/*.json ({size / 1024:.0f} KB in all, {size / len(reqs) / 1024:.1f} KB each)")


if __name__ == "__main__":
    main(sys.argv[1])
