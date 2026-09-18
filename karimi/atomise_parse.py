"""Splitting by dependency structure, for the segments regex cannot reach.

The regex splitter in `atomise` finds coordination by looking for commas and
conjunctions, which means it can only see *one* level: a head followed by a
flat list. Real requirements nest, and the nesting is invisible at the surface —
`Experience designing and operating ETL pipelines using Airflow, Azure Data
Factory` coordinates two activities *over* a list of tools, and no arrangement
of commas distinguishes that from a flat list of four things.

A dependency parse does distinguish it. `designing` and `operating` are linked
to each other by a `conj` relation and both hang off `Experience`; the tools are
a separate `conj` chain hanging off `using`. So the parse says which items are
coordinated with which, and what governs each group — exactly the two facts the
regex has to guess.

What this still cannot do, and why an LLM is not fully replaceable: the parse
tells us `credit` is coordinated inside `including credit, restructuring`, but
not that the natural head for it is `Experience with` rather than the source's
`Experience applying AI to complex financial domains, including`. Choosing a
head that is not in the text is generation, and a parser does not generate.

Local, deterministic, no API. Currently English only — `en_core_web_sm` is the
one installed model, and English is roughly 58% of requirement *text* after the
upstream translation described in `language.py`. Other languages need their own
model downloaded before this is worth running on them.
"""

from __future__ import annotations

import functools

from . import atomise as atom
from . import config

# Dependency labels whose subtree is part of the thing being coordinated rather
# than part of the shared governor.
_DROP_DEPS = {"cc", "punct"}


@functools.lru_cache(maxsize=4)
def load_parser(name: str = "en_core_web_sm"):
    """Load a spaCy pipeline with only what the parse needs.

    NER and lemmatisation are disabled: they cost time and nothing here uses
    them. Cached because loading dominates the cost on short strings.
    """
    import spacy

    return spacy.load(name, disable=["ner", "lemmatizer", "textcat"])


def _conjunct_groups(doc):
    """Map each coordination head to the conjuncts hanging off it.

    Returned in document order so the outermost coordination — the one whose
    head appears earliest — is handled first and the split reflects the
    sentence's own structure rather than the order tokens happened to parse in.
    """
    groups: dict[int, list] = {}
    for tok in doc:
        if tok.dep_ == "conj":
            groups.setdefault(tok.head.i, []).append(tok)
    return sorted(groups.items())


def _subtree_span(tok) -> set[int]:
    return {t.i for t in tok.subtree}


def _render(doc, keep: set[int]) -> str:
    """Rebuild text from a token-index set, dropping dangling connectives."""
    toks = [doc[i] for i in sorted(keep)]
    while toks and (toks[0].dep_ in _DROP_DEPS or toks[0].is_punct):
        toks.pop(0)
    while toks and (toks[-1].dep_ in _DROP_DEPS or toks[-1].is_punct):
        toks.pop()
    return atom.clean(" ".join(t.text for t in toks))


def split_by_parse(segment: str, nlp=None) -> list[str]:
    """Split one segment on its outermost coordination.

    Each conjunct is emitted with the shared governor kept and the *other*
    conjuncts' subtrees removed, which is head distribution done structurally
    instead of by pattern. Returns a single-element list when the parse finds no
    coordination, so the caller can fall through to the regex splitter.
    """
    nlp = nlp or load_parser()
    doc = nlp(segment)

    groups = _conjunct_groups(doc)
    if not groups:
        return [segment]

    head_i, conjuncts = groups[0]
    head_tok = doc[head_i]
    members = [head_tok] + conjuncts

    # Everything not inside any conjunct is shared context and is kept on every
    # output; the conjunct subtrees are what varies between them.
    member_spans = {m.i: _subtree_span(m) for m in members}
    all_member_tokens: set[int] = set()
    for s in member_spans.values():
        all_member_tokens |= s
    shared = {t.i for t in doc} - all_member_tokens

    out = []
    for m in members:
        keep = shared | member_spans[m.i]
        # The head's own subtree contains the other conjuncts, so remove them.
        for other in members:
            if other.i != m.i:
                keep -= member_spans[other.i]
        text = _render(doc, keep)
        if len(text) > 2:
            out.append(text)

    # A split that loses most of the segment is a parse failure, not a result.
    if len(out) < 2 or max(len(t) for t in out) < len(segment) * 0.25:
        return [segment]
    return out


# Language name (as `language.detect` returns it) -> installed spaCy model.
TAGGERS = {
    "English": "en_core_web_sm",
    "Deutsch": "de_core_news_sm",
    "Français": "fr_core_news_sm",
    "Italiano": "it_core_news_sm",
    "Español": "es_core_news_sm",
    "Nederlands": "nl_core_news_sm",
}


@functools.lru_cache(maxsize=8)
def load_tagger(lang: str):
    """Load the tagger for a language, or None when there is no model for it."""
    name = TAGGERS.get(lang)
    if not name:
        return None
    import spacy

    try:
        return spacy.load(name, disable=["ner", "lemmatizer", "textcat", "parser"])
    except OSError:
        return None


def split_modifier_run(segment: str, lang: str) -> list[str]:
    """Split a run of coordinated adjectives sharing one noun.

    This is Karimi's tail observation done with real part-of-speech tags rather
    than suffix guessing. `Eigenverantwortliches, engagiertes und
    kundenorientiertes Arbeiten` tags as ``ADJ PUNCT ADJ CCONJ ADJ NOUN`` — an
    unambiguous shape — and each adjective is a separate requirement once the
    noun is copied onto it.

    Suffix rules could not do this. `ADJECTIVAL_RE` in `atomise` is built from
    English endings, so it never fired on the German case above and misfired on
    nouns elsewhere; a tagger reads the inflection directly. Returns a
    single-element list when the shape is absent, so the caller falls through.
    """
    nlp = load_tagger(lang)
    if nlp is None:
        return [segment]

    doc = nlp(segment)
    tag = {t.text: t.pos_ for t in doc}

    items = atom._cut(segment)
    if len(items) < 2 or len(items[-1].split()) < 2:
        return [segment]

    # The tail is the final chunk's own head noun.
    last_tokens = items[-1].split()
    if tag.get(last_tokens[-1]) not in {"NOUN", "PROPN"}:
        return [segment]
    tail = last_tokens[-1]

    # A single-word chunk in front of it is either a modifier of that noun or a
    # requirement in its own right, and the tag is what separates them:
    # `Selbststaendige` is ADJ and modifies `Arbeitsweise`; `Autonomy` is NOUN
    # and stands alone. This is the one judgement suffix rules could not make.
    out, distributed = [], 0
    for item in items[:-1]:
        words = item.split()
        if len(words) == 1 and tag.get(words[0]) == "ADJ":
            out.append(atom.clean(f"{item} {tail}"))
            distributed += 1
        else:
            out.append(item)
    out.append(items[-1])

    return out if distributed else [segment]


def atomise_pos(segment: str, lang: str | None = None) -> list[str]:
    """Regex splitter, with the tagger consulted where it left a bare modifier.

    Triggered by a one-word chunk in the regex output, not by the regex
    declining: the modifier-run failure *does* split, it just leaves `reliable`
    or `Selbststaendige` standing alone. Cost ordering is unchanged — the free
    layer answers first and the tagger is spent only on that specific defect.
    """
    pieces = atom.atomise(segment)
    # Only where the regex split AND left a bare one-word chunk. If it declined
    # to split at all, that was a deliberate precision call — the modifier-run
    # guard — and second-guessing it costs more than it recovers.
    if len(pieces) < 2 or not any(len(p.split()) == 1 for p in pieces):
        return pieces

    if lang is None:
        from . import language as lang_mod

        lang = lang_mod.detect(segment)[0] or "English"

    run = split_modifier_run(segment, lang)
    return run if len(run) > 1 else pieces


def atomise_hybrid(segment: str, nlp=None) -> list[str]:
    """Regex splitter first, parse only on what it leaves whole.

    Ordering is deliberate and is the same cost argument as the classifier's:
    the regex is free and already reaches 0.897 precision on short segments, so
    the parse is spent only where the cheap layer declined to act.
    """
    pieces = atom.atomise(segment)
    if len(pieces) > 1:
        return pieces
    if len(segment) <= config.LONG_SEGMENT_CHARS:
        return pieces

    parsed = split_by_parse(segment, nlp)
    if len(parsed) < 2:
        return pieces

    # Re-run the regex over each conjunct: the parse resolves the outer
    # coordination and the regex is good at the flat lists left inside it.
    out: list[str] = []
    for p in parsed:
        out.extend(atom.atomise(p) or [p])
    return out
