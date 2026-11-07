"""The splitting errors of this rules version, by kind and likely cause, on hand counts.

    python "New project/score_split_errors.py" --dict 0.1.0

The splitting half of the site's error table (`errors.py` says why it is
measured per version and not per run). Every one of the 115 hand-counted
items (`validation/count_holdout_LABELLED.csv`, both halves; aggregates only,
so the blind half is not read) is split by the library, and an item whose
count differs from the human's is one error: `merged` when the library found
fewer, `over_split` when more, with its cause from `errors.split_profile`.

The file also carries why there is no per-run figure: the best precision of
the shape rules (`score_error_detectors.py`) and of the judge's count
(`score_judge_counts.py`), when those have been run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import score_counts  # noqa: E402

from karimi_normalise import Dictionary, TranslationCache, errors, split_posting  # noqa: E402
from karimi_normalise.freeze import STORE  # noqa: E402
from karimi_normalise.quality import QUALITY  # noqa: E402
from karimi_normalise.versions import RULES_VERSION  # noqa: E402


def _read(name: str) -> dict | None:
    p = QUALITY / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="0.1.0")
    args = ap.parse_args(argv)
    d = Dictionary(STORE / args.dict)
    cache = TranslationCache(HERE / "output" / "translate_cache.jsonl")
    rows = []
    for r in score_counts.load():
        if r["n"] is None:
            continue
        reqs = [q.to_dict() for q in split_posting([r["item"]], d, cache=cache)]
        rows.append({"item": r["item"], "translated": any(q["translated"] for q in reqs),
                     "human": r["n"], "requirements": reqs})
    prof = errors.split_profile(rows)
    det = _read(f"error_detectors_{RULES_VERSION}__{args.dict}.json")
    judge = [x for x in (_read(f"judge_counts_{c}_read.json") for c in ("c1", "c2")) if x]
    out = {
        "rules_version": RULES_VERSION, "dict_version": args.dict,
        "source": "115 hand-counted holdout items (count_holdout_LABELLED.csv), both halves, aggregates only",
        **errors.table(prof),
        "wrong_items": sum(prof["counts"].values()),
        "per_run_instruments": {
            "shape_rules_best_precision": max((v["precision"] or 0 for v in (det or {}).get(
                "by_detector", {}).values()), default=None),
            "judge_count_best_precision": max((x["flag_precision"] or 0 for x in judge), default=None),
            "bar": 0.60,
        },
    }
    QUALITY.mkdir(parents=True, exist_ok=True)
    path = QUALITY / f"split_errors_{RULES_VERSION}__{args.dict}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
