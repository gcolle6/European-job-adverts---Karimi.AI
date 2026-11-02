"""The effect of ONE rule: split with it and without it, everything else equal.

    python "New project/isolate_rule.py" _shared_tail [seed]

The named function in `karimi.atomise` is replaced by one returning None (the
rule abstains). Prints totals for `software_dev` and `software_holdout`, then a
sample of changed items from `software_dev` only — the holdout is never read.
Pipeline as in `split_must_have.py`: repairs and tagger on, English input.
"""

from __future__ import annotations

import collections
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import split_quality as q  # noqa: E402
from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402
from karimi import pos  # noqa: E402


def compare(name: str, rule: str):
    config.SPLIT_REPAIRS = True
    config.SPLIT_POS = True
    rows = q.rows_for(name)
    tr = q.translations(name)
    occ = collections.Counter(tr.get(it, it) for r in rows for it in r["must_have"])
    texts = sorted(occ)
    pos.prime(texts)
    real = getattr(atom, rule)
    on = {s: atom.route(s)[0] for s in texts}
    # A function abstains by returning None; a pattern by never matching.
    off_value = (re.compile(r"(?!x)x") if isinstance(real, re.Pattern)
                 else False if isinstance(real, bool) else (lambda *a, **k: None))
    setattr(atom, rule, off_value)
    try:
        off = {s: atom.route(s)[0] for s in texts}
    finally:
        setattr(atom, rule, real)
    changed = [s for s in texts if on[s] != off[s]]
    delta = sum((len(on[s]) - len(off[s])) * occ[s] for s in changed)
    print(f"{name}: {len(texts):,} unique items; {rule} changes {len(changed):,} "
          f"({sum(occ[s] for s in changed) / sum(occ.values()):.2%} of occurrences); atoms {delta:+,}")
    return changed, on, off


if __name__ == "__main__":
    rule = sys.argv[1]
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    compare("software_holdout", rule)
    changed, on, off = compare("software_dev", rule)
    random.seed(seed)
    for s in random.sample(changed, min(30, len(changed))):
        print(f"  {s[:120]}\n     without {off[s]}\n     with    {on[s]}")
