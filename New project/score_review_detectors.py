"""Each inspector detector measured against a person's review of a run.

    python "New project/score_review_detectors.py" <batch dir> <sample.json> <labels.jsonl>

The review labels an ITEM correct or incorrect (`karimi_normalise/review.py`).
A detector fires on the item when it fires on any of its requirements. Per
detector: the reviewed items it fired on, how many of them the person called
wrong (precision), the share of the person's wrong items it found (recall),
and how often it fires on the whole run (volume — what it would add to the
colour). The requirements are read from the run's own `results.jsonl`, so the
detectors judge exactly what the person judged, with today's code.

A detector enters the colour only when its precision on a review is high
enough that it does not invent errors (2026-11-18, the user's call: errors a
person finds become rules for future inspections, but measured first).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import errors  # noqa: E402


def item_detectors(reqs: list[dict]) -> set[str]:
    hits = {f for f in (errors.inspector_flag(r) for r in reqs) if f}
    hits |= set(errors.item_flags(reqs).values())
    keys = [r.get("key") for r in reqs if r.get("key")]
    if len(keys) != len(set(keys)):
        hits.add("duplicate_key")
    return hits


def main(batch: str, sample_path: str, labels_path: str) -> None:
    postings = {str(p["id"]): p for p in (json.loads(x) for x in open(Path(batch) / "results.jsonl", encoding="utf-8"))}
    sample = json.load(open(sample_path, encoding="utf-8"))["items"]
    subs = [json.loads(x) for x in open(labels_path, encoding="utf-8") if x.strip()]
    labels = {x["n"]: x["verdict"] for x in subs[-1]["labels"]}

    fired, wrong_hit = Counter(), Counter()
    wrong = {n for n, v in labels.items() if v == "incorrect"}
    found_any = set()
    for it in sample:
        if it["n"] not in labels:
            continue
        p = postings.get(str(it["posting"]))
        reqs = [r for r in (p or {}).get("requirements", []) if r.get("item_idx") == it["item_idx"]]
        for d in item_detectors(reqs):
            fired[d] += 1
            if it["n"] in wrong:
                wrong_hit[d] += 1
                found_any.add(it["n"])

    volume = Counter()
    n_reqs = 0
    for p in postings.values():
        by_item = defaultdict(list)
        for r in p.get("requirements") or []:
            by_item[r.get("item_idx")].append(r)
            n_reqs += 1
        for rs in by_item.values():
            across = errors.item_flags(rs)
            for j, r in enumerate(rs):
                f = errors.inspector_flag(r) or across.get(j)
                if f:
                    volume[f] += 1

    print(f"{len(labels)} items labelled, {len(wrong)} wrong; {n_reqs} requirements in the run")
    print(f"{'detector':26s} {'fired':>5s} {'right':>5s} {'prec':>6s} {'recall':>7s} {'run vol':>8s}")
    for d in sorted(set(fired) | set(volume), key=lambda d: -fired[d]):
        prec = wrong_hit[d] / fired[d] if fired[d] else float("nan")
        print(f"{d:26s} {fired[d]:5d} {wrong_hit[d]:5d} {prec:6.2f} {wrong_hit[d] / max(len(wrong), 1):7.2f} "
              f"{volume[d]:8d}")
    print(f"any detector: found {len(found_any)} of {len(wrong)} wrong items")


if __name__ == "__main__":
    main(*sys.argv[1:4])
