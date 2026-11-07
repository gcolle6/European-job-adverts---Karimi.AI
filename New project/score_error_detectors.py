"""How often a splitting error the site counts is a real one.

    python "New project/score_error_detectors.py" --dict 0.1.0

The site's error table counts splitting errors by DETECTORS (`errors.py`),
rules that recognise a damaged split from its shape. A count is only worth
what its detector is, so each is scored here against the 120 items counted by
hand (`validation/count_holdout_LABELLED.csv`, the same sheet as
`score_counts.py`), and the result travels in the quality card beside the
table.

What a hand COUNT can check, and what it cannot:

* ``merged`` (two requirements left in one) predicts the library counting
  FEWER than the human: that is scored, as precision (a flagged item really
  is under-counted) and recall (an under-counted item is flagged);
* ``fragment`` (a piece missing its head) usually leaves the count right, so
  a count cannot confirm it. Reported as how often it fires, not as accuracy.

Aggregates only: no item text is printed or written.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import score_counts  # noqa: E402

from karimi_normalise import Dictionary, TranslationCache, split_posting  # noqa: E402
from karimi_normalise import errors  # noqa: E402
from karimi_normalise.freeze import STORE  # noqa: E402
from karimi_normalise.quality import QUALITY  # noqa: E402
from karimi_normalise.versions import RULES_VERSION  # noqa: E402


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="0.1.0")
    args = ap.parse_args(argv)
    d = Dictionary(STORE / args.dict)
    cache = TranslationCache(HERE / "output" / "translate_cache.jsonl")
    rows = [r for r in score_counts.load() if r["n"] is not None]

    fired, right, tally = Counter(), Counter(), Counter()
    for r in rows:
        reqs = [q.to_dict() for q in split_posting([r["item"]], d, cache=cache)]
        flags = [f for f in errors.split_flags(reqs) if f]
        system = sum(q["counted"] for q in reqs)
        under, over = system < r["n"], system > r["n"]
        merged = any(f[0] == "merged" for f in flags)
        fragment = any(f[0] == "fragment" for f in flags)
        for mech in {f[1] for f in flags}:
            kind = next(f[0] for f in flags if f[1] == mech)
            fired[mech] += 1
            # what the count says of an item this detector fired on
            right[mech] += under if kind == "merged" else over
        tally["items"] += 1
        tally["under"] += under
        tally["over"] += over
        tally["merged_flagged"] += merged
        tally["merged_right"] += merged and under
        tally["under_flagged"] += under and merged
        tally["fragment_flagged"] += fragment
        tally["fragment_with_over"] += fragment and over

    out = {
        "rules_version": RULES_VERSION, "dict_version": args.dict, "items": tally["items"],
        "source": "120 hand-counted holdout items (count_holdout_LABELLED.csv), 5 left blank",
        "under_counted_items": tally["under"], "over_counted_items": tally["over"],
        "merged": {"flagged": tally["merged_flagged"],
                   "precision": _rate(tally["merged_right"], tally["merged_flagged"]),
                   "recall": _rate(tally["under_flagged"], tally["under"])},
        "fragment": {"flagged": tally["fragment_flagged"],
                     "with_count_too_high": tally["fragment_with_over"],
                     "note": "a missing head leaves the count right: not checkable on counts"},
        # per detector: items it fired on, and how many of them the hand count
        # confirms (under-counted for a merge, over-counted for a fragment)
        "by_detector": {m: {"fired": n, "confirmed": right[m], "precision": _rate(right[m], n)}
                        for m, n in sorted(fired.items())},
        "over_split_flagged": _rate(tally["fragment_with_over"], tally["over"]),
    }
    QUALITY.mkdir(parents=True, exist_ok=True)
    path = QUALITY / f"error_detectors_{RULES_VERSION}__{args.dict}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
