"""Does the library give what the batch gave? Phase 1's first two criteria.

    python -m karimi_normalise.parity --dict 0.0.dev1 --n 200

Draws postings from the export (dev only: `software_holdout` stays unread),
runs them through the library one posting at a time, and compares with
`must_have_atoms.parquet`:

1. **split** — same atoms, item by item. Differences come from translation
   (decided per posting here, once per item in the batch) or from a rule
   changed since the batch ran;
2. **group** — the dictionary lookup against the batch's `req_group` and
   `req_topic`, on atoms both produced. Exact cores agree by construction, so
   the figure that matters is over cores the lookup had to place.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

import pandas as pd

from . import Dictionary, split_posting
from .freeze import BATCH, STORE

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"
HOLDOUT = ROOT / "New project" / "test_sets.json"
SEED = 20261104


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dict", required=True)
    p.add_argument("--n", type=int, default=200)
    args = p.parse_args(argv)
    d = Dictionary(STORE / args.dict)
    hold = set(json.loads(HOLDOUT.read_text(encoding="utf-8"))["software_holdout"])
    rows = [r for r in json.loads(EXPORT.read_text(encoding="utf-8"))
            if r["must_have"] and r["_id"] not in hold]
    sample = random.Random(SEED).sample(rows, args.n)
    batch = pd.read_parquet(BATCH / "must_have_atoms.parquet",
                            columns=["posting_id", "item_idx", "atom", "req_group", "req_topic"])
    batch = batch[batch.posting_id.isin({r["_id"] for r in sample})]
    want = batch.groupby(["posting_id", "item_idx"]).atom.agg(list).to_dict()
    group = {(a.posting_id, a.item_idx, a.atom): (a.req_group, a.req_topic) for a in batch.itertuples()}

    items = same_items = 0
    diffs = []
    match = collections.Counter()
    agree = collections.Counter()
    for r in sample:
        got = collections.defaultdict(list)
        for q in split_posting(r["must_have"], d):
            got[q.item_idx].append(q)
            g = group.get((r["_id"], q.item_idx, q.atom))
            if g is None:
                continue
            match[q.match] += 1
            agree[(q.match, "group")] += q.req_group == g[0]
            agree[(q.match, "topic")] += q.req_topic == g[1]
        for i in range(len(r["must_have"])):
            items += 1
            mine = [q.atom for q in got[i]]
            if mine == want.get((r["_id"], i), []):
                same_items += 1
            elif len(diffs) < 15:
                diffs.append((r["must_have"][i], want.get((r["_id"], i)), mine))
    from .versions import RULES_VERSION
    from .quality import QUALITY
    QUALITY.mkdir(parents=True, exist_ok=True)
    (QUALITY / f"parity_{RULES_VERSION}__{args.dict}.json").write_text(json.dumps({
        "postings": args.n, "items": items, "items_identical": same_items,
        "share_identical": round(same_items / items, 4),
        "lookup_same_group": {k: round(agree[(k, "group")] / n, 4) for k, n in match.items()},
    }, indent=2), encoding="utf-8")
    print(f"split: {same_items}/{items} items identical ({same_items / items:.1%})")
    for item, w, m in diffs:
        print(f"  - {item[:90]}\n      batch:   {w}\n      library: {m}")
    print("\ngroup lookup, on atoms both produced:")
    for k, n in sorted(match.items(), key=lambda x: -x[1]):
        print(f"  {k:6s} {n:6,}   same req_group {agree[(k, 'group')] / n:6.1%}"
              f"   same req_topic {agree[(k, 'topic')] / n:6.1%}")


if __name__ == "__main__":
    main()
