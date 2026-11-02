"""Part-of-speech tags for the splitter's open word classes.

Decided 2026-10-30 (`New project/PATTERNS.md`): the splitter must work on
`must_have` text nobody has seen yet, so whether a word is a verb or an
adjective is decided by a tagger, not by a list of verbs or adjectives that
breaks on the first word it lacks. Closed classes (prepositions, conjunctions,
language names) stay as lists — the language has no others.

One English model is enough because the text is translated to English first
(decided 2026-10-29). In Week 1 the same idea needed six models and was not
worth it (`atomise_parse.py`); that objection no longer applies.

A word is tagged IN THE ITEM IT CAME FROM. Alone, `design` reads as a noun; in
`Ability to design, run, and debug systems` it is a verb, and the splitter only
ever sees the chunk. `route` sets the item as context; `tag` looks the word up
there and falls back to tagging it alone. Same input, same tags: spaCy on CPU is
deterministic, and the model version is pinned in `config.POS_MODEL`.
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import config

_nlp = None
_context: list[tuple[str, str, str]] = []   # (word lowercased, coarse pos, fine tag)


def _model():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load(config.POS_MODEL, disable=["parser", "ner", "lemmatizer"])
        got = _nlp.meta.get("version")
        if got != config.POS_MODEL_VERSION:
            raise RuntimeError(f"{config.POS_MODEL} is {got}, config pins "
                               f"{config.POS_MODEL_VERSION}: tags, and so splits, could differ")
    return _nlp


@lru_cache(maxsize=400_000)
def _tagged(text: str) -> tuple[tuple[str, str, str], ...]:
    return tuple((t.text.lower(), t.pos_, t.tag_) for t in _model()(text))


_PRIMED: dict[str, tuple[tuple[str, str, str], ...]] = {}


def prime(texts) -> None:
    """Tag many items in one batch, which is far faster than one at a time."""
    todo = [t for t in dict.fromkeys(texts) if t and t not in _PRIMED]
    for text, doc in zip(todo, _model().pipe(todo, batch_size=512)):
        _PRIMED[text] = tuple((t.text.lower(), t.pos_, t.tag_) for t in doc)


def set_context(text: str) -> None:
    global _context
    _context = list(_PRIMED.get(text) or _tagged(text))


def tag(word: str) -> tuple[str, str]:
    """(coarse pos, fine tag) of `word`, read in the current item if it is there."""
    w = re.sub(r"[^\w-]", "", word).lower()
    for text, pos, fine in _context:
        if text == w:
            return pos, fine
    alone = _tagged(word)
    return (alone[-1][1], alone[-1][2]) if alone else ("X", "XX")


def is_verb(word: str) -> bool:
    return tag(word)[0] == "VERB"


def is_gerund(word: str) -> bool:
    return tag(word)[1] == "VBG"


def is_adjective(word: str) -> bool:
    return tag(word)[0] == "ADJ"
