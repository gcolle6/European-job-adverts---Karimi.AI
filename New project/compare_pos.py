"""What changes when open word classes come from the tagger instead of word lists.

    python "New project/compare_pos.py" [set] [seed]     # default software_dev

Splits every item of a frozen set twice — `config.SPLIT_POS` off and on — and
prints the totals and a random sample of items whose split differs. Read the
sample on `software_dev` only; on the test sets look at the totals alone.
"""

from __future__ import annotations

import collections
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import split_quality as q  # noqa: E402
from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402
from karimi import pos  # noqa: E402


def main(name: str, seed: int) -> None:
    config.SPLIT_REPAIRS = True
    rows = q.rows_for(name)
    tr = q.translations(name)
    occ = collections.Counter(tr.get(it, it) for r in rows for it in r["must_have"])
    texts = sorted(occ)
    config.SPLIT_POS = False
    off = {s: atom.route(s)[0] for s in texts}
    config.SPLIT_POS = True
    pos.prime(texts)
    on = {s: atom.route(s)[0] for s in texts}
    changed = [s for s in texts if on[s] != off[s]]
    delta = sum((len(on[s]) - len(off[s])) * occ[s] for s in changed)
    print(f"{name}: {len(texts):,} unique items; split differs on {len(changed):,} "
          f"({sum(occ[s] for s in changed) / sum(occ.values()):.2%} of occurrences); "
          f"atoms {delta:+,}")
    if name != "software_dev":
        return
    random.seed(seed)
    for s in random.sample(changed, min(30, len(changed))):
        print(f"  {s[:120]}\n     lists {off[s]}\n     POS   {on[s]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "software_dev",
         int(sys.argv[2]) if len(sys.argv) > 2 else 1)
