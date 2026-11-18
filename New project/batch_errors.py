"""Every error the agents found in one batch, item by item: step 2 of the cycle per batch.

    python "New project/batch_errors.py" "New project/output/new_postings/batch_03"

The inspector's flags, read again with the detectors of today (so a kind
named since the batch ran shows too), each with the item, its English, what
the run made and the rules version; then the explorer's kinds with their
cases, from the run's own check. What is read here and found wrong, and not
yet in the catalogue, becomes a catalogue entry with a detector (the user's
process, 2026-11-17, `PIANO_SVILUPPO.md`).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import errors  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    batch = Path((argv or sys.argv[1:])[0])
    posts = [json.loads(x) for x in (batch / "results.jsonl").open(encoding="utf-8") if x.strip()]
    by = defaultdict(list)
    n = 0
    for p in posts:
        for r in p.get("requirements") or []:
            n += 1
            f = errors.inspector_flag(r)
            if f:
                by[f].append(r)
    versions = {r.get("rules_version") for p in posts for r in p.get("requirements") or []}
    print(f"{batch.name}: {len(posts)} postings, {n} requirements, rules {sorted(v for v in versions if v)}")
    for kind, rs in sorted(by.items(), key=lambda x: -len(x[1])):
        print(f"\n== inspector: {kind} ({len(rs)})")
        seen = set()
        for r in rs:
            if r["item"] in seen:
                continue
            seen.add(r["item"])
            en = r.get("item_split") if r.get("translated") else None
            print(f"   ITEM {r['item'][:120]}")
            if en and en != r["item"]:
                print(f"     en {en[:120]}")
            print(f"        {r['atom'][:70]} -> {r['key'][:70]}")
    check = batch / "check.json"
    ex = (json.loads(check.read_text(encoding="utf-8")) if check.exists() else {}).get("explorer") or {}
    if ex and not ex.get("grouped", True):
        print(f"\n## explorer: {ex.get('problems')} problems the model could not group")
    for kd in ex.get("kinds") or []:
        tag = "NEW" if kd.get("new") else f"= {kd.get('catalogue')}"
        print(f"\n## explorer {tag}: {kd['id']} ({kd.get('count')}) {kd.get('title')} | {kd.get('shape')}")
        for c in kd.get("cases") or []:
            print(f"   ITEM {c['item'][:120]}\n        {c.get('what')}\n        made {c.get('made')}")


if __name__ == "__main__":
    main()
