"""From raw `must_have` items to single, normalised requirements.

The same steps as the batch (`New project/translate_must_have.py`, then
`split_must_have.py`), one posting at a time:

0. clean what is written around the requirement (`clean_item`, rules 0.2.0):
   a bullet, doubled spaces, a closing full stop; and an item with no
   capital at all gets the dictionary's capitals back;
1. translate the item to English when it is not English (decided 2026-10-29).
   The translator is the caller's choice: their own English text, their own
   function, or opus-mt by default — the one the quality card was measured
   with. ``translated_by`` on every requirement says which;
2. split it with the rules, repairs and tagger on (`atomise.route`);
3. normalise the wording (`normalise_req.normalise_requirement`);
4. move years, level, head and qualifier into their own fields (`decompose`);
5. with a dictionary, look the core up: group, topic, `nuovo`, or
   `non_cercato` when the embedding model is not installed.

Every requirement carries the original item, the route it took and both
versions, so any output can be traced to the employer's words and to the rules
that made it.

⚠️ The rules keep state at module level (`config` switches, the tagger's
context in `pos`), so one process splits one posting at a time. The API runs
one worker per container for this reason.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from karimi import atomise as atom
from karimi import config
from karimi import normalise_req
from karimi import pos

from . import translate as tr
from .versions import RULES_VERSION


@dataclass
class Requirement:
    item_idx: int
    item: str               # as the employer wrote it
    item_split: str         # what was split: the English translation, or the item
    translated: bool
    translated_by: str      # "" | opus-mt | given (the caller's text) | the caller's function name
    route: str              # rules | single | llm | damaged (`atomise.route`)
    atom_idx: int
    atom: str
    atom_norm: str
    nice_to_have: bool
    counted: bool
    years_min: int | None
    years_max: int | None
    years_raw: str
    level: str
    level_words: str
    head: str
    head_group: str         # how it was asked: experience | competence | ability | language | education | ""
    degree: str             # education only: bachelor | master | phd | mba | degree | student
    core: str
    extra: str
    qualifier: str
    modes: str
    space: str              # where it is grouped: language | education | "" (rules 0.3.0)
    key: str
    req_group: str = ""
    req_topic: str = ""
    req_name: str = ""      # the requirement as a reader names it: its group's, else its own key
    match: str = ""         # known | group | topic | nuovo | empty | non_cercato, "" without a dictionary
    match_cosine: float | None = None
    match_via: str = ""      # the known core it was placed by: what a check compares it with
    match_by: str = ""       # "" the frozen dictionary; `curator` an agent's resolved spelling (`curator.py`)
    rules_version: str = RULES_VERSION
    dict_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_BULLET = re.compile(r"^\s*(?:[-–—•·*▪◦●►✓✔]+|\(?\d{1,2}[.)])\s+")
_END = re.compile(r"(?<=[\w)\]%])\s*[.;,]$")
_ABBREVIATIONS = {"etc.", "e.g.", "i.e.", "ecc.", "usw.", "bzw.", "z.b.", "inkl.", "evtl.", "ca.",
                  "p.ex.", "ex.", "incl.", "approx.", "min.", "max.", "u.a.", "d.h."}


def clean_item(item: str, casing: dict[str, str] | None = None) -> str:
    """The item as the rules read it: what was written AROUND the requirement removed.

    Added 2026-11-07 (rules 0.2.0) after `New project/invariance.py`: a bullet
    or a full stop changed the result of 17.7% of non-English items, through
    the translator, and a whole item in lower case 41.9% of all items.

    * a bullet or a list number in front, doubled spaces, one closing `.`,
      `;` or `,` (an abbreviation's dot is kept: `etc.`, `e.g.`);
    * an item with NO capital at all gets them back from ``casing``, the map
      of its own language (`Dictionary.casing`, through `clean_items`):
      `python` -> `Python`, `ci/cd` -> `CI/CD`, German `erfahrung` ->
      `Erfahrung`, and a capital on its first letter. An item with some
      capitals keeps the employer's: there they are information, and the
      batch read them as such.

    ``Requirement.item`` stays as the employer wrote it.
    """
    s = " ".join(_BULLET.sub("", item).split())
    if s.rsplit(" ", 1)[-1].lower() not in _ABBREVIATIONS:
        s = _END.sub("", s)
    if casing is not None and s and not any(ch.isupper() for ch in s):
        s = normalise_req._NAME_TOKEN.sub(lambda m: casing.get(m.group(0), m.group(0)), s)
        s = s[0].upper() + s[1:]
    return s


def clean_items(items: list[str], casing: dict[str, dict[str, str]] | None = None,
                language: str | None = None) -> dict[str, tuple[str, str | None]]:
    """item -> (cleaned text, language code or None for English), for one posting.

    The language is decided on the text without its bullet (`translate.item_code`,
    which reads case-free), so a lower-case item finds its language's capitals."""
    base = {it: clean_item(it) for it in items}
    codes = {it: tr.item_code(base[it], list(base.values()), language) for it in items}
    if casing is None:
        return {it: (base[it], codes[it]) for it in items}
    return {it: (clean_item(it, casing.get(codes[it] or "en")), codes[it]) for it in items}


def _opus_mt(cache):
    def opus_mt(pairs):
        try:
            return tr.translate(pairs, cache)
        except ImportError as e:
            raise ImportError("opus-mt is not installed: pip install karimi-normalise[translate], "
                              "or pass the English text (must_have_english) or a translator") from e
    return opus_mt


def english_items(postings: list[tuple[list[str], str | None, list[str] | None]], cache=None,
                  translator=None, casing: dict[str, dict[str, str]] | None = None
                  ) -> list[dict[str, tuple[str, str]]]:
    """item -> (English, translated_by) for each posting, in ONE pass over all of them.

    Each posting is (items, language hint, the caller's English or None). The
    caller's English, aligned with the items, is used as given. The rest is
    decided per item in its own posting (`translate.item_code`) and the unique
    (language, item) pairs go to ``translator`` together: a function taking
    [(code, text)] and returning {(code, text): English}, opus-mt with
    ``cache`` by default. Batching and the cache are where translation, the
    costliest step, gets cheap. What is decided and translated is the item
    as `clean_items` leaves it (``casing`` as there); the keys stay the items.
    """
    fn = translator or _opus_mt(cache)
    by = "opus-mt" if translator is None else getattr(translator, "__name__", "custom")
    given = [dict(zip(items, en)) if en else {} for items, _, en in postings]
    clean = [clean_items(items, casing, language) for items, language, _ in postings]
    todo = [(cl[it][1], cl[it][0]) for (items, _, _), g, cl in zip(postings, given, clean)
            for it in items if it not in g and cl[it][1]]
    done = fn(todo) if todo else {}
    return [{**{it: (done[(cl[it][1], cl[it][0])], by) for it in items if it not in g and cl[it][1]},
             **{it: (en, "given") for it, en in g.items()}}
            for (items, _, _), g, cl in zip(postings, given, clean)]


def split_posting(items: list[str], dictionary=None, translate: bool = True,
                  language: str | None = None, cache=None, translator=None,
                  english: dict[str, tuple[str, str]] | None = None) -> list[Requirement]:
    """All requirements of one posting's `must_have` list.

    Pass the whole list, not item by item: a short item's language is read
    from its posting (`translate.item_code`). ``language`` is a fallback name
    (`Deutsch`) for when neither decides. ``translate=False`` splits the text
    as written, with the tagger off, as `split_must_have.py --original` does:
    the tagger is English-only. ``translator`` as in `english_items`.
    ``english`` takes translations already made (`english_items`, as `process`
    does for many postings at once).
    """
    config.SPLIT_REPAIRS = True
    config.SPLIT_POS = translate
    casing = dictionary.casing if dictionary is not None else None
    clean = {it: c[0] for it, c in clean_items(items, casing, language).items()}
    if not translate:
        english = {}
    elif english is None:
        english = english_items([(items, language, None)], cache, translator, casing)[0]
    if translate:
        pos.prime(english[it][0] if it in english else clean[it] for it in items)

    out: list[Requirement] = []
    for i, item in enumerate(items):
        text, by = english.get(item, (clean[item], ""))
        text = atom.repair_translation(item, text)
        was = item in english and text != clean[item]
        atoms, how = atom.route(text)
        counts = atom.counted(atoms)
        for j, a in enumerate(atoms):
            norm = normalise_req.normalise_requirement(a, was)
            out.append(Requirement(item_idx=i, item=item, item_split=text, translated=was,
                                   translated_by=by if was else "", route=how,
                                   atom_idx=j, atom=a, atom_norm=norm,
                                   nice_to_have=atom.nice_to_have(a), counted=counts[j],
                                   **normalise_req.decompose(norm)))
    if dictionary is not None:
        for r, m in zip(out, dictionary.lookup_requirements([(r.space, r.core) for r in out])):
            r.req_group, r.req_topic, r.match, r.match_cosine = m.group, m.topic, m.status, m.cosine
            r.match_via, r.match_by = m.via, m.by
            r.req_name = dictionary.name(m.group or m.topic) or normalise_req.display(r.space, r.core)
            r.dict_version = dictionary.version
    return out


def split(item: str, dictionary=None, translate: bool = True,
          language: str | None = None, cache=None, translator=None) -> list[Requirement]:
    """The requirements in one item, when the rest of the posting is not at hand."""
    return split_posting([item], dictionary, translate, language, cache, translator)
