"""Label-free quality of a split, comparable across the frozen sets.

    python "New project/split_quality.py"                  # dev and holdout
    python "New project/split_quality.py" --pos            # with config.SPLIT_POS on
    python "New project/split_quality.py" --show orphan_verb software_dev   # read examples

Every change to the splitter is judged here on `software_holdout`, which
is never read (`datasets.py`, `PATTERNS.md`). With no labels there, the measures are DEFECTS a reader would see, found by parsing
the item and asking where each atom was cut:

per atom of a split item
* ``stranded_modifier`` — the atom ends on a modifier whose noun stayed outside:
  `EEA` from `EEA or Swiss citizenship`, `Excellent written`.
* ``orphan_verb``       — the atom ends on a verb whose object or partner verbs
  stayed outside: `Experience designing`, `Ability to recruit`.
* ``dangling_word``     — the atom ends on a word that can never end a
  requirement: `in a clear`, `with the`, `and`.
* ``duplicate``         — the same atom twice in one item.

per item
* ``lost_content``      — a noun of the item appears in no atom. Fillers dropped
  on purpose (`or similar`) are excluded; everything else is lost meaning.
* ``whole_compound``    — kept whole, yet the parse shows two coordinated nouns
  with different heads: the under-splitting side of the trade, kept visible so
  the measure cannot be improved by splitting less.

⚠️ The parser is also what the splitter will use for open word classes, so this
is not independent of it. The independent check is the human count sheet.
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import datasets  # noqa: E402
from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402

OUT = HERE / "output"
DEV_SAMPLE_POSTINGS = 3000
SEED = 20261030

FILLER = {"similar", "related", "equivalent", "comparable", "field", "fields", "area", "areas",
          "discipline", "disciplines", "plus", "advantage", "asset", "bonus", "like", "etc",
          "other", "others", "direction", "degree", "e.g.", "i.e.",
          # generic containers dropped by design when examples follow (PATTERNS.md P5)
          "tools", "tool", "technologies", "technology", "frameworks", "framework", "languages",
          "platforms", "solutions", "software", "role", "roles", "position", "following",
          "subject", "subjects"}
END_NEVER = {"DET", "ADP", "CCONJ", "SCONJ", "PART"}
MODIFIER_DEPS = {"amod", "compound", "nmod", "poss", "nummod"}
MEASURES_ATOM = ["stranded_modifier", "orphan_verb", "dangling_word", "duplicate"]
MEASURES_ITEM = ["lost_content", "whole_compound"]

_nlp = None


def nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    return _nlp


def rows_for(name: str) -> list[dict]:
    rows = datasets.load(name)
    if name == "software_dev":
        rows = random.Random(SEED).sample(rows, DEV_SAMPLE_POSTINGS)
    return rows


def translations(name: str) -> dict[str, str]:
    t = pd.read_parquet(OUT / "items_en.parquet")
    return dict(zip(t["item"], t["item_en"]))


def _words(s: str) -> list[str]:
    # Split as the parser does — on hyphens, slashes and dots — so that
    # `data-management` is not counted as lost when the atom keeps it.
    return re.findall(r"[^\W_]+|[#+]+", s.lower())


def _anchor(doc, a_words: list[str]):
    """The item token where the atom ends: its last word, preferring the
    occurrence preceded by the atom's second-to-last word."""
    toks = [t for t in doc if _words(t.text)]
    hits = [k for k, t in enumerate(toks) if _words(t.text)[-1] == a_words[-1]]
    if not hits:
        return None
    if len(a_words) > 1:
        good = [k for k in hits if k > 0 and _words(toks[k - 1].text)[-1] == a_words[-2]]
        if good:
            return toks[good[-1]]
    return toks[hits[-1]]


def judge(text: str, atoms: list[str], doc, atom_docs: dict) -> dict:
    """Defects of one item's split. `doc` is the parsed item text."""
    out = collections.Counter()
    if len(atoms) == 1:
        masked = atom.PAREN_RE.sub("", text)
        for t in doc:
            if t.dep_ == "conj" and t.pos_ in ("NOUN", "PROPN") and t.head.pos_ in ("NOUN", "PROPN") \
                    and t.text.lower() != t.head.text.lower() and t.text in masked \
                    and not atom.MODIFIER_RE.match(t.text) and not atom.MODIFIER_RE.match(t.head.text):
                out["whole_compound"] = 1
                break
        return out

    seen = set()
    for a in atoms:
        key = atom.normalise(a)
        out["duplicate"] += key in seen
        seen.add(key)
        aw = set(_words(a))
        ad = atom_docs[a]
        last = [t for t in ad if not t.is_punct]
        if last and last[-1].pos_ in END_NEVER:
            out["dangling_word"] += 1
        t = _anchor(doc, _words(a)) if _words(a) else None
        if t is None:
            continue
        if t.dep_ in MODIFIER_DEPS and not set(_words(t.head.text)) <= aw and t.head.i > t.i:
            out["stranded_modifier"] += 1
        if t.pos_ == "VERB":
            outside = [d for d in t.subtree if d.i > t.i and not d.is_punct and d.dep_ != "cc"
                       and not set(_words(d.text)) <= aw]
            if outside:
                out["orphan_verb"] += 1

    have = set()
    for a in atoms:
        have |= set(_words(a))
    # The category before examples (`scripting languages such as ...`, `tools
    # (...)`) may be dropped by design (PATTERNS.md P5): not lost content.
    category = set()
    for ch in doc.noun_chunks:
        nxt = doc[ch.end: ch.end + 3].text.lower().lstrip(", ")
        if re.match(r"^(?:\(|:|such as|like|including|e\.g|for example|namely)", nxt):
            category |= {t.i for t in ch}
        # `or similar AI orchestration frameworks`: the filler's own noun phrase.
        if any(t.text.lower() in ("similar", "related", "equivalent", "comparable") for t in ch):
            category |= {t.i for t in ch}
    lost = [t for t in doc if t.pos_ in ("NOUN", "PROPN") and _words(t.text) and t.i not in category
            and not set(_words(t.text)) <= have and t.text.lower() not in FILLER]
    out["lost_content"] = int(bool(lost))
    return out


def measure(name: str, show: str | None = None, k: int = 25) -> dict:
    config.SPLIT_REPAIRS = True
    config.SPLIT_POS = "--pos" in sys.argv
    rows = rows_for(name)
    tr = translations(name)
    occ = collections.Counter(tr.get(it, it) for r in rows for it in r["must_have"])
    texts = sorted(occ)
    if config.SPLIT_POS:
        from karimi import pos
        pos.prime(texts)
    routed = {s: atom.route(s)[0] for s in texts}
    docs = dict(zip(texts, nlp().pipe(texts, batch_size=256)))
    uniq_atoms = sorted({a for v in routed.values() for a in v})
    with nlp().select_pipes(disable=["parser"]):
        atom_docs = dict(zip(uniq_atoms, nlp().pipe(uniq_atoms, batch_size=512)))

    totals = collections.Counter()
    examples = collections.defaultdict(list)
    n_items = sum(occ.values())
    n_atoms = sum(len(routed[s]) * n for s, n in occ.items())
    n_split_atoms = sum(len(routed[s]) * n for s, n in occ.items() if len(routed[s]) > 1)
    n_whole = sum(n for s, n in occ.items() if len(routed[s]) == 1)
    for s in texts:
        j = judge(s, routed[s], docs[s], atom_docs)
        for m, v in j.items():
            totals[m] += v * occ[s]
            if v:
                examples[m].append(s)
    res = {
        "set": name, "postings": len(rows), "items": n_items, "atoms": n_atoms,
        "atoms_per_item": round(n_atoms / n_items, 3),
        **{m: round(totals[m] / max(n_split_atoms, 1), 4) for m in MEASURES_ATOM},
        "lost_content": round(totals["lost_content"] / max(n_items - n_whole, 1), 4),
        "whole_compound": round(totals["whole_compound"] / max(n_whole, 1), 4),
    }
    if show:
        random.seed(SEED)
        for s in random.sample(examples[show], min(k, len(examples[show]))):
            print(f"  {s[:120]}\n     {routed[s]}")
    return res


if __name__ == "__main__":
    if "--show" in sys.argv:
        i = sys.argv.index("--show")
        print(measure(sys.argv[i + 2], show=sys.argv[i + 1]))
        sys.exit()
    sets = ["software_dev", "software_holdout"]
    table = pd.DataFrame([measure(s) for s in sets]).set_index("set")
    print("atom measures are per atom of a SPLIT item; lost_content per split item; "
          "whole_compound per item kept whole\n")
    print(table.T.to_string())
