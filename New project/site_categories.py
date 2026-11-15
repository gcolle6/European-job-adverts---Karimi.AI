"""A category for each requirement of the site's explorer, so the list can be browsed by kind.

    python "New project/site_categories.py"        # print the categories of the current explorer list

The method, the seeds and the overrides live in `karimi_normalise/categories.py`
since 2026-11-15, so the check job on Cloud Run names new requirements the same
way. This file keeps the local cache of the model's answers and the listing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi_normalise.categories import ORDER, categorise as _categorise  # noqa: E402,F401

CACHE = HERE / "output" / "site_categories.json"


def categorise(names: list[str], spaces: list[str], model=None, judge_url: str | None = None) -> list[str]:
    """`categories.categorise` with the answers cached in CACHE."""
    asked = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    out = _categorise(names, spaces, asked, model=model, judge_url=judge_url)
    if judge_url:
        CACHE.write_text(json.dumps(asked, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    from collections import defaultdict

    ix = json.loads((HERE.parent.parent / "karimi-normalise-site" / "public" / "data" / "explore" / "index.json")
                    .read_text(encoding="utf-8"))
    by = defaultdict(list)
    for r in ix["requirements"]:
        by[r.get("category", "?")].append(r["name"])
    for c in ORDER + ["?"]:
        if by.get(c):
            print(f"\n== {c} ({len(by[c])})\n   " + " | ".join(sorted(by[c], key=str.casefold)))
