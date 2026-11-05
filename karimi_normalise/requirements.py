"""From raw `must_have` items to single, normalised requirements.

The same steps as the batch (`New project/translate_must_have.py`, then
`split_must_have.py`), one posting at a time:

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
    head_group: str
    core: str
    extra: str
    qualifier: str
    modes: str
    key: str
    req_group: str = ""
    req_topic: str = ""
    match: str = ""         # known | group | topic | nuovo | empty | non_cercato, "" without a dictionary
    match_cosine: float | None = None
    match_via: str = ""      # the known core it was placed by: what a check compares it with
    rules_version: str = RULES_VERSION
    dict_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _opus_mt(cache):
    def opus_mt(pairs):
        try:
            return tr.translate(pairs, cache)
        except ImportError as e:
            raise ImportError("opus-mt is not installed: pip install karimi-normalise[translate], "
                              "or pass the English text (must_have_english) or a translator") from e
    return opus_mt


def english_items(postings: list[tuple[list[str], str | None, list[str] | None]], cache=None,
                  translator=None) -> list[dict[str, tuple[str, str]]]:
    """item -> (English, translated_by) for each posting, in ONE pass over all of them.

    Each posting is (items, language hint, the caller's English or None). The
    caller's English, aligned with the items, is used as given. The rest is
    decided per item in its own posting (`translate.item_code`) and the unique
    (language, item) pairs go to ``translator`` together: a function taking
    [(code, text)] and returning {(code, text): English}, opus-mt with
    ``cache`` by default. Batching and the cache are where translation, the
    costliest step, gets cheap.
    """
    fn = translator or _opus_mt(cache)
    by = "opus-mt" if translator is None else getattr(translator, "__name__", "custom")
    given = [dict(zip(items, en)) if en else {} for items, _, en in postings]
    codes = [{it: tr.item_code(it, items, language) for it in items if it not in g}
             for (items, language, _), g in zip(postings, given)]
    todo = [(c, it) for cs in codes for it, c in cs.items() if c]
    done = fn(todo) if todo else {}
    return [{**{it: (done[(c, it)], by) for it, c in cs.items() if c},
             **{it: (en, "given") for it, en in g.items()}}
            for cs, g in zip(codes, given)]


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
    if not translate:
        english = {}
    elif english is None:
        english = english_items([(items, language, None)], cache, translator)[0]
    if translate:
        pos.prime(english[it][0] if it in english else it for it in items)

    out: list[Requirement] = []
    for i, item in enumerate(items):
        text, by = english.get(item, (item, ""))
        was = text != item
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
        for r, m in zip(out, dictionary.lookup_requirements([(r.head_group, r.core) for r in out])):
            r.req_group, r.req_topic, r.match, r.match_cosine = m.group, m.topic, m.status, m.cosine
            r.match_via = m.via
            r.dict_version = dictionary.version
    return out


def split(item: str, dictionary=None, translate: bool = True,
          language: str | None = None, cache=None, translator=None) -> list[Requirement]:
    """The requirements in one item, when the rest of the posting is not at hand."""
    return split_posting([item], dictionary, translate, language, cache, translator)
