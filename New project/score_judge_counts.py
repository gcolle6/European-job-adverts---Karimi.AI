"""Can the judge tell a wrong split? Its count against the hand count.

    python "New project/score_judge_counts.py" --half read     # the prompt is worked on here
    python "New project/score_judge_counts.py" --half blind    # read once per prompt version

The site's splitting errors need an instrument that reads an item and says
how many requirements it holds. The rule detectors failed at it
(`score_error_detectors.py`: the best was right on 22% of what it flagged),
so the judge is asked to COUNT (`tester.count`), by the guide the human
counted with. A split is flagged where the judge's count and the library's
differ.

The figure that decides is the flag's PRECISION: of the items where judge and
library disagree, how often the judge is the one that matches the human.
Fixed 2026-11-07, BEFORE the judge counted any item: at least
MIN_FLAG_PRECISION on the blind half, else the check does not count splitting
errors and the site says they are not measured. Halves as in `score_counts.py`
(the read half for error analysis, the blind half never read).

Aggregates only: no item text is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import score_counts  # noqa: E402

from karimi_normalise import Dictionary, TranslationCache, split_posting, tester  # noqa: E402
from karimi_normalise.freeze import STORE  # noqa: E402
from karimi_normalise.quality import QUALITY  # noqa: E402
from karimi_normalise.versions import RULES_VERSION  # noqa: E402

MIN_FLAG_PRECISION = 0.60


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", choices=["read", "blind"], required=True)
    ap.add_argument("--dict", default="0.1.0")
    ap.add_argument("--url", default=os.environ.get("KARIMI_JUDGE_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--name", default="qwen3_4b")
    ap.add_argument("--prompt", default=tester.COUNT_PROMPT, choices=sorted(tester.COUNT_PROMPTS))
    args = ap.parse_args(argv)
    rows = score_counts.load()
    score_counts.halves(rows)
    rows = [r for r in rows if r["n"] is not None and r["half"] == args.half]

    d = Dictionary(STORE / args.dict)
    cache = TranslationCache(HERE / "output" / "translate_cache.jsonl")
    lib = [sum(q.counted for q in split_posting([r["item"]], d, cache=cache)) for r in rows]
    judge = tester.count(args.url, args.name, [r["item"] for r in rows], args.prompt)
    human = [r["n"] for r in rows]

    answered = [k for k, j in enumerate(judge) if j is not None]
    disagree = [k for k in answered if judge[k] != lib[k]]
    judge_right = [k for k in disagree if judge[k] == human[k]]
    lib_right = [k for k in disagree if lib[k] == human[k]]
    lib_wrong = [k for k in answered if lib[k] != human[k]]
    out = {
        "half": args.half, "items": len(rows), "answered": len(answered),
        "judge": args.name, "prompt": args.prompt, "rules_version": RULES_VERSION,
        "judge_exact": _rate(sum(judge[k] == human[k] for k in answered), len(answered)),
        "library_exact": _rate(sum(lib[k] == human[k] for k in answered), len(answered)),
        "flags": len(disagree),
        "flag_precision": _rate(len(judge_right), len(disagree)),
        "flags_where_library_was_right": len(lib_right),
        "flag_recall": _rate(sum(k in disagree for k in lib_wrong), len(lib_wrong)),
        "fewer_than_judge": {"flags": sum(lib[k] < judge[k] for k in disagree),
                             "right": sum(lib[k] < judge[k] for k in judge_right)},
        "more_than_judge": {"flags": sum(lib[k] > judge[k] for k in disagree),
                            "right": sum(lib[k] > judge[k] for k in judge_right)},
        "min_flag_precision": MIN_FLAG_PRECISION,
    }
    out["passes"] = out["flag_precision"] is not None and out["flag_precision"] >= MIN_FLAG_PRECISION
    QUALITY.mkdir(parents=True, exist_ok=True)
    path = QUALITY / f"judge_counts_{args.prompt}_{args.half}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
