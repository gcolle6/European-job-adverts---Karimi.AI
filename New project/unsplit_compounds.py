"""The items the rules leave whole although they look compound — grouped.

`atomise.route` labels them `llm`: more than one requirement appears to be in
there and the rules cannot separate it. With no LLM stage they are kept whole,
so each counts as ONE requirement — which makes this the largest source of
under-counting: 20% of all items, against 0.08% still damaged.

But `needs_llm` was tuned for recall (precision 0.759 on the labelled sample),
so a share of these are genuinely one requirement: `excellent written and
verbal communication` is one by the guide. The first job is therefore to tell
the classes apart, by features read off the text, before writing any rule.

    python "New project/unsplit_compounds.py"              # English items as written
    python "New project/unsplit_compounds.py" --translated # after translate_must_have.py
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402
from karimi import language  # noqa: E402

EXPORT = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"
TRANSLATIONS = Path(__file__).resolve().parent / "output" / "items_en.parquet"

CONJ_EN = re.compile(r"\s(and|or|as well as|and/or|&)\s", re.I)
CORREL = re.compile(r"\b(both|either|neither|whether)\b", re.I)
GERUND = re.compile(r"^\w{3,}ing$", re.I)


def classify(text: str) -> str:
    """One class per item, first match wins. Features only, no judgement."""
    words = text.split()
    has_comma = "," in atom.PAREN_RE.sub("", text)
    m = CONJ_EN.search(atom.PAREN_RE.sub("", text))
    if CORREL.search(text):
        return "U1 correlative (both/either ... and/or)"
    if m:
        before = text[: m.start()].split()
        after = text[m.end():].split()
        w_before = re.sub(r"\W", "", before[-1]) if before else ""
        w_after = re.sub(r"\W", "", after[0]) if after else ""
        if GERUND.match(w_before) and GERUND.match(w_after):
            # DECIDED 2026-10-29: one requirement, correctly whole — `building
            # and maintaining CI/CD pipelines` names one demand, and the later
            # normalisation step reduces it to `Experience with CI/CD
            # pipelines`. Not under-counting; no rule should split it.
            return "U2 coordinated verbs (designing and operating ...) - ONE, decided"
        if atom._adjectival(w_before.lower()) and atom._adjectival(w_after.lower()):
            return "U3 coordinated modifiers (written and verbal ...)"
        if len(before) <= 2 and len(after) <= 2:
            return "U4 short pair (X and Y, <=2 words each side)"
        if has_comma:
            return "U5 commas + conjunction, not read as a list"
        return "U6 two phrases joined by a conjunction"
    if has_comma:
        return "U7 commas, no conjunction"
    if atom.INTRODUCER_RE_V2.search(text):
        return "U8 introducer, not split"
    if len(text) > config.LLM_ROUTE_MIN_CHARS:
        return "U9 long, no comma or conjunction"
    return "U0 other"


def main(translated: bool) -> None:
    config.SPLIT_REPAIRS = True
    rows = json.loads(EXPORT.read_text(encoding="utf-8"))
    occ = collections.Counter(it for r in rows for it in r["must_have"])
    if translated:
        t = pd.read_parquet(TRANSLATIONS)
        en = dict(zip(t["item"], t["item_en"]))
        texts = collections.Counter()
        for it, n in occ.items():
            texts[en.get(it, it)] += n
    else:
        texts = collections.Counter({it: n for it, n in occ.items()
                                     if language.detect(it)[0] == "English"})

    total_items = sum(texts.values())
    groups: dict[str, list[str]] = collections.defaultdict(list)
    g_occ = collections.Counter()
    for text, n in texts.items():
        if atom.route(text)[1] != "llm":
            continue
        c = classify(text)
        groups[c].append(text)
        g_occ[c] += n
    n_unsplit = sum(g_occ.values())
    print(f"{'translated' if translated else 'English-as-written'}: {len(texts):,} unique, "
          f"{total_items:,} occurrences; unsplit compounds {sum(len(v) for v in groups.values()):,} "
          f"unique, {n_unsplit:,} occurrences ({n_unsplit / total_items:.1%})\n")
    random.seed(20261029)
    for c in sorted(groups):
        print(f"=== {c}: {len(groups[c]):,} unique, {g_occ[c]:,} occ ({g_occ[c] / n_unsplit:.1%})")
        for s in random.sample(groups[c], min(8, len(groups[c]))):
            print(f"    {s[:130]}")
        print()


if __name__ == "__main__":
    main(translated="--translated" in sys.argv)
