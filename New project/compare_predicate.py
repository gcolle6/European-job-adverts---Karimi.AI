"""Tagger predicate vs the word-list / suffix predicate it replaces, all else equal.

    python "New project/compare_predicate.py" adjectival [seed]

(`nominal_ing` and the P7 opener test were compared the same way on 2026-10-30
and the tagger lost both, so those branches were removed; see
`atomise._nominal_ing` and `atomise._opens_requirement`.)

Runs the pipeline with the tagger on twice; the second time the named predicate
falls back to its old rule. Totals on dev and holdout; a reading sample from
dev only.
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

OLD = {
    "ability_verb": ("_ability_verb", lambda w: w.lower() in atom._VERBS),
    "adjectival": ("_adjectival_pos",
                   lambda w: bool(atom.ADJECTIVAL_RE.match(w)) and not atom.NOMINAL_RE.search(w)),
}


def compare(name: str, which: str):
    config.SPLIT_REPAIRS = True
    config.SPLIT_POS = True
    rows = q.rows_for(name)
    tr = q.translations(name)
    occ = collections.Counter(tr.get(it, it) for r in rows for it in r["must_have"])
    texts = sorted(occ)
    pos.prime(texts)
    attr, old_fn = OLD[which]
    new = {s: atom.route(s)[0] for s in texts}
    real = getattr(atom, attr)
    setattr(atom, attr, old_fn)
    try:
        old = {s: atom.route(s)[0] for s in texts}
    finally:
        setattr(atom, attr, real)
    changed = [s for s in texts if new[s] != old[s]]
    delta = sum((len(new[s]) - len(old[s])) * occ[s] for s in changed)
    print(f"{name}: {which} by tagger changes {len(changed):,} items "
          f"({sum(occ[s] for s in changed) / sum(occ.values()):.2%} of occurrences); atoms {delta:+,}")
    return changed, new, old


if __name__ == "__main__":
    which = sys.argv[1]
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    compare("software_holdout", which)
    changed, new, old = compare("software_dev", which)
    random.seed(seed)
    for s in random.sample(changed, min(30, len(changed))):
        print(f"  {s[:120]}\n     old rule {old[s]}\n     tagger   {new[s]}")
