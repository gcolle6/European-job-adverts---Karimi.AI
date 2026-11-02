"""Which rules splits come out damaged, and do the damages share a pattern?

`atomise.route` accepts any split into two or more pieces as finished. On the
re-delivered software export that is 50,939 unique items, and the labelled
sample cannot say how many of them are broken: the damage detector fires on 3 of
its 150 rows and moves holdout F1 by 0.002, while it fires on 3,385 corpus items.
**A sample that rarely contains a construction cannot measure it** — so the
damage is grouped here over the whole export instead, by features read off the
input and output, never by eye.

Each damaged split is put in exactly one class, first match wins, and every
class prints its members' examples so a striking count can be checked against
what it actually contains before anything is built on it.

    python "New project/split_damage.py"            # taxonomy, current splitter
    python "New project/split_damage.py" --repair   # same, with config.SPLIT_REPAIRS on
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402

EXPORT = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"

_FILLER_TAIL_RE = re.compile(
    r"^(?:an?\s+|the\s+)?(?:equivalent|similar|comparable|related|relevant|"
    r"[eé]quivalent|vergleichbar|gleichwertig|gelijkwaardig|equivalente|simil)", re.I)


def load_items() -> collections.Counter:
    rows = json.loads(EXPORT.read_text(encoding="utf-8"))
    return collections.Counter(it for r in rows for it in r["must_have"])


def classify_damage(segment: str, pieces: list[str]) -> str | None:
    """The finest damage class that applies, or None for a clean split."""
    reason = atom.damage_reason(segment, pieces)
    if reason is None:
        return None
    has_paren = bool(atom.PAREN_LIST_RE.search(segment))
    if reason == "duplicate":
        return "D4 duplicate atoms"
    if reason == "leading_conjunction":
        bad = next(p for p in pieces[1:] if atom.LEAD_CONJ_RE.match(p))
        rest = atom.LEAD_CONJ_RE.sub("", bad)
        if _FILLER_TAIL_RE.match(rest):
            return "D1b conjunction + filler ('or equivalent ...')"
        if has_paren:
            return "D1a conjunction left after a bracket"
        return "D1c conjunction, other"
    if reason == "leaked_introducer":
        bad = next(p for p in pieces if atom.LEAKED_INTRO_RE.search(p))
        if re.search(r"z\.\s+b\.", bad, re.I):
            return "D2a spaced 'z. B.' not recognised"
        return "D2b 'e.g.'/'bzw.' outside a bracket"
    if reason == "bracket_juxtaposition":
        before = segment[: atom.PAREN_LIST_RE.search(segment).start()]
        heads = atom._head_alternatives(before)
        if len(heads) > 1:
            return "D3c alternatives in the head ('stockage et sauvegarde (...)')"
        if atom.PREP_RE.search(before):
            return "D3a head has a preposition, generic noun kept"
        return "D3b head has no preposition ('Strong testing habits (...)')"
    return f"other: {reason}"


def main(repair: bool) -> None:
    config.SPLIT_REPAIRS = repair
    occ = load_items()
    total_occ = sum(occ.values())
    routes = collections.Counter()
    classes: dict[str, list[tuple[str, list[str]]]] = collections.defaultdict(list)
    class_occ = collections.Counter()
    for it, n in occ.items():
        pieces = atom.atomise(it)
        if len(pieces) < 2:
            routes["unsplit"] += 1
            continue
        routes["split"] += 1
        c = classify_damage(it, pieces)
        if c:
            classes[c].append((it, pieces))
            class_occ[c] += n

    n_dmg = sum(len(v) for v in classes.values())
    print(f"SPLIT_REPAIRS={repair}  unique items {len(occ):,}  split {routes['split']:,}  "
          f"damaged {n_dmg:,} ({n_dmg / routes['split']:.1%} of splits, "
          f"{sum(class_occ.values()) / total_occ:.2%} of occurrences)\n")
    random.seed(20261029)
    for c in sorted(classes, key=lambda k: -len(classes[k])):
        members = classes[c]
        print(f"=== {c}: {len(members):,} unique, {class_occ[c]:,} occurrences")
        for it, pieces in random.sample(members, min(5, len(members))):
            print(f"    {it[:120]}")
            for p in pieces:
                print(f"        -> {p[:110]}")
        print()


if __name__ == "__main__":
    main(repair="--repair" in sys.argv)
