"""Normalised wording of one requirement atom, beside the atom itself.

Splitting decides HOW MANY requirements an item holds; this decides how each
one is WORDED, so that the same demand written in different ways reads the same.
The atom is never replaced: `atom_norm` sits next to it, and every step is a
deterministic rule, so the same atom always normalises the same way.

Two steps, both decided 2026-10-29/11-01:

1. **Translation calques** (`fix_translation`), only on translated text. The
   local MT model renders some fixed phrases word by word: `fließend` ->
   `Flowing`, `in Wort und Schrift` -> `in word and writing`. They were found by
   contrast — words frequent in translated atoms and near-absent in atoms that
   were English from the start — and each is corrected to the phrase an English
   writer uses. A closed list of one instrument's systematic errors, not rules
   about content.
2. **Activity verbs on an object** (`experience_with`): `Experience building and
   maintaining CI/CD pipelines` -> `Experience with CI/CD pipelines`, as decided
   on 2026-10-29 for coordinated verbs, applied to a single verb too. Verbs are
   found by the tagger (`karimi.pos`). A verb that IS the requirement is kept —
   `Experience leading teams` is not `Experience with teams`.
"""

from __future__ import annotations

import re

from . import atomise as atom
from . import pos

# (pattern, replacement) — applied in order, case-insensitive, word-bounded.
MT_FIXES = [
    (r"\bwell[- ]founded\b", "solid"),
    (r"\bin (?:word|speech) and (?:writing|font|scripture)\b", "written and spoken"),
    (r"\bin writing and (?:word|speech)\b", "written and spoken"),
    (r"\bflowing\b", "fluent"),
    (r"\bnegotiable\b", "business-fluent"),
    (r"\bexhibitable\b", "demonstrable"),
    (r"\b(?:safe|secure) handling of\b", "confident use of"),
    (r"\bsecure (communication|knowledge|command)\b", r"confident \1"),
    (r"\bself-employed\b", "independent"),
    (r"\bappetence for\b", "interest in"),
    (r"\baisance (?:in|with|for)\b", "ease with"),
    (r"\bpreparedness to\b", "willingness to"),
    (r"\bknown with\b", "familiar with"),
    (r"\bafinity\b", "affinity"),
    (r"\bdominion (?:of|in)\b", "mastery of"),
    (r"^mastering\b", "mastery of"),
]
_MT_FIXES = [(re.compile(p, re.I), r) for p, r in MT_FIXES]


def _match_case(src: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def fix_translation(text: str) -> str:
    for rx, repl in _MT_FIXES:
        text = rx.sub(lambda m: _match_case(m.group(0), m.expand(repl)), text)
    return re.sub(r"\bmastery of (?:the )?of\b", "mastery of", text, flags=re.I)


# Verbs that name the requirement itself: dropping them changes what is asked.
KEEP_VERBS = {
    "leading", "managing", "mentoring", "coaching", "supervising", "coordinating", "selling",
    "negotiating", "teaching", "training", "recruiting", "hiring", "advising", "consulting",
    "presenting", "communicating", "facilitating", "directing", "steering", "motivating",
}
# No `with`: after `experience with` an `-ing` word is a noun (`logging solutions`).
_HEAD_RE = re.compile(r"^(?P<head>.*?\bexperience)\s+(?:(?:in|of)\s+)?(?P<rest>.+)$", re.I)
_CONNECT = {"and", "or", "and/or", ",", "&"}
# `working` is the one light verb: `working in agile teams` -> `experience in agile
# teams`. Any other verb before a preposition carries meaning (`contributing to`).
_LIGHT_PREP = {"in", "on", "with", "within", "across", "at"}
# The verb governs more than its object (`turning X into Y`, `deploying X to
# production`), or a second activity follows: leave the wording as written.
_VERB_COMPLEMENT_RE = re.compile(r"\b(?:into|to|as|from|onto)\b|\band\s+\w+ing\b", re.I)


def experience_with(text: str) -> str:
    """`<... experience> <verb>(, <verb>)* <object>` -> `<... experience> with <object>`."""
    m = _HEAD_RE.match(text)
    if not m:
        return text
    pos.set_context(text)
    words = re.findall(r",|[^\s,]+", m.group("rest"))
    k, verbs = 0, []
    while k < len(words):
        w = words[k]
        if w.lower() in _CONNECT and verbs:
            k += 1
            continue
        # A verb opens the run or follows a conjunction; an `-ing` word straight
        # after a verb is the object's modifier (`implementing monitoring
        # solutions`). A gerund by the tagger, or by the splitter's verb test,
        # since the tagger alone reads the first of a run as a noun
        # (`experience designing, building and deploying`).
        after_verb = bool(verbs) and words[k - 1].lower() not in _CONNECT
        if not after_verb and w.lower().endswith("ing") and (pos.tag(w)[1] == "VBG" or atom._verb(w)):
            verbs.append(w)
            k += 1
            continue
        break
    obj = " ".join(words[k:]).replace(" ,", ",").strip()
    if not verbs or not obj or any(v.lower() in KEEP_VERBS for v in verbs):
        return text
    # The tagger must see a verb somewhere in the run, so a field name the list
    # also knows as a verb stays (`experience in marketing campaigns`). And a run
    # ending on a conjunction was a list of nouns: `marketing and sales`.
    if not any(pos.tag(v)[1] == "VBG" for v in verbs) or words[k - 1].lower() in _CONNECT:
        return text
    if _VERB_COMPLEMENT_RE.search(obj):
        return text
    first = obj.split()[0].lower()
    if pos.tag(first)[0] in ("ADP", "SCONJ") or first in _LIGHT_PREP:
        if [v.lower() for v in verbs] == ["working"] and first in _LIGHT_PREP:
            return f"{m.group('head')} {obj}"
        return text
    return f"{m.group('head')} with {obj}"


def normalise_requirement(atom: str, translated: bool) -> str:
    out = fix_translation(atom) if translated else atom
    return experience_with(out)


# --- Decomposition: years, level, head, core (decided 2026-11-01) -------------
#
# To group requirements without losing information, what varies around the
# same demand is moved into its own column first: `3+ years of strong hands-on
# experience with Kubernetes` is experience / 3+ years / strong hands-on /
# `Kubernetes`. Grouping then runs on the head group and the core alone, and
# every removed part stays readable in its column.

_YEARS_RE = re.compile(
    r"(?:\b(?:at\s+least|minimum(?:\s+of)?|min\.?|more\s+than|over|up\s+to)\s+)?"
    r"\b(?P<a>\d{1,2})\s*(?P<plus>\+)?\s*(?:(?:-|–|to)\s*(?P<b>\d{1,2})\s*\+?\s*)?"
    r"(?:years?|yrs?)(?:['’]s?)?(?:\s+of)?(?!\w)|"
    r"\b(?P<vague>several|many|a\s+few|multiple|some|a\s+couple\s+of|first)\s+years?(?:\s+of)?\b",
    re.I)

# The frame nouns a requirement is asked through, by group. A closed set: the
# ways a job ad asks for something, not what it asks for.
HEAD_GROUPS = {
    "competence": ["knowledge", "understanding", "familiarity", "proficiency", "expertise",
                   "mastery", "command", "grasp", "awareness", "know-how", "skills", "skill",
                   "fluency"],
    "experience": ["experience", "background", "track record", "exposure"],
    "ability": ["ability", "capacity", "capability", "aptitude"],
}
_HEAD_OF = {h: g for g, hs in HEAD_GROUPS.items() for h in hs}
# What the frame noun itself says about the level (`familiarity` is less than
# `expertise`), kept so that grouping on `competence` loses nothing.
HEAD_LEVEL = {"familiarity": "basic", "awareness": "basic", "exposure": "basic",
              "proficiency": "advanced", "command": "advanced", "fluency": "strong", "expertise": "expert",
              "mastery": "expert"}
# Degree and evidence words in front of the head: a small closed class.
LEVEL_WORDS = {
    "basic": "basic", "first": "basic", "some": "basic", "initial": "basic", "fundamental": "basic",
    "good": "good", "solid": "good", "sound": "good", "working": "good", "practical": "good",
    "decent": "good", "fair": "good", "adequate": "good", "confident": "good", "hands-on": "good",
    "strong": "strong", "very": "strong", "excellent": "strong", "deep": "strong",
    "in-depth": "strong", "extensive": "strong", "advanced": "strong", "thorough": "strong",
    "robust": "strong", "great": "strong", "significant": "strong", "comprehensive": "strong",
    "broad": "strong", "profound": "strong", "considerable": "strong", "substantial": "strong",
    "fluent": "strong", "business-fluent": "strong", "native": "expert",
    "outstanding": "expert", "exceptional": "expert", "expert": "expert", "superior": "expert",
    "proven": "", "demonstrated": "", "demonstrable": "", "previous": "", "prior": "",
    "relevant": "", "professional": "", "a": "", "an": "", "the": "",
}
_LEVEL_RANK = {"": 0, "basic": 1, "good": 2, "strong": 3, "advanced": 3, "expert": 4}
_HEAD_RE2 = re.compile(
    r"^(?P<pre>(?:[\w'’-]+\s+){0,4}?)(?P<head>track record|know-how|"
    + "|".join(sorted((h for h in _HEAD_OF if " " not in h and h != "know-how"), key=len, reverse=True))
    + r")\b(?P<post>.*)$", re.I)


def _years(text: str) -> tuple[str, int | None, int | None, str]:
    m = _YEARS_RE.search(text)
    if not m:
        return text, None, None, ""
    if m.group("vague"):
        lo = hi = None
        raw = m.group("vague").lower()
    else:
        lo = int(m.group("a"))
        hi = int(m.group("b")) if m.group("b") else (None if m.group("plus") or "least" in m.group(0).lower()
                                                     or "minimum" in m.group(0).lower() else lo)
        raw = m.group(0).strip()
    rest = re.sub(r"\s{2,}", " ", (text[: m.start()] + " " + text[m.end():])).strip(" ,.-")
    return rest, lo, hi, raw


def decompose(text: str) -> dict:
    """Split one normalised requirement into the parts it is asked with.

    Returns years (min, max, as written), level (coarse and the words), head
    (as written and its group), the core the requirement is about, and
    ``key`` = ``group: core``, the grouping key. Nothing is guessed: a part
    that is not there stays empty, and an atom with no frame noun keeps all of
    itself as the core (`Python`, `Team player`).
    """
    rest, lo, hi, years_raw = _years(text)
    out = {"years_min": lo, "years_max": hi, "years_raw": years_raw, "level": "",
           "level_words": "", "head": "", "head_group": "", "core": rest, "extra": ""}
    m = _HEAD_RE2.match(rest)
    if m:
        pre = m.group("pre").split()
        head = m.group("head").lower()
        post = m.group("post").strip()
        known = [w for w in pre if w.lower() in LEVEL_WORDS]
        # Words in front that are not degree words belong to the core:
        # `strong communication skills`, `Python programming experience`. When
        # there are such words, they ARE the object, and what follows the head
        # is something else (`problem-solving skills with excellent attention
        # to detail`): it goes to `extra`, not into the key.
        object_words = [w for w in pre if w.lower() not in LEVEL_WORDS]
        post_obj = re.sub(r"^(?:of|in|with|on|for|at|to|regarding|around|within|across)\s+", "",
                          post, flags=re.I) if post else ""
        if object_words:
            core, extra = " ".join(object_words), post.strip(" ,.:-")
        else:
            core, extra = post_obj, ""
        core = re.sub(r"^(?:the|a|an)\s+", "", core.strip(" ,.:-"), flags=re.I)
        # A preposition in front means the head was found inside a longer
        # phrase (`Analytical mindset with the ability to ...`): not a frame.
        if any(w.lower() in ("with", "of", "in", "for", "to", "on") for w in object_words):
            core = ""
        out["extra"] = extra if core else ""
        if core:
            levels = [LEVEL_WORDS[w.lower()] for w in known] + [HEAD_LEVEL.get(head, "")]
            out.update(level=max(levels, key=lambda l: _LEVEL_RANK[l]),
                       level_words=" ".join(w for w in known if LEVEL_WORDS[w.lower()] != "" or
                                            w.lower() in ("proven", "demonstrated", "demonstrable")),
                       head=head, head_group=_HEAD_OF[head], core=core)
    elif years_raw:
        # `5 years in software development`: years imply experience.
        core = re.sub(r"^(?:of|in|with|on|for|at|as)\s+", "", rest, flags=re.I)
        out.update(head="(years)", head_group="experience", core=core)
    else:
        # No frame noun: degree words in front are still the level, not the
        # demand (`Excellent written and verbal communication`).
        words = rest.split()
        k = 0
        while k < len(words) - 1 and words[k].lower() in LEVEL_WORDS:
            k += 1
        if k:
            lv = [LEVEL_WORDS[w.lower()] for w in words[:k]]
            out.update(level=max(lv, key=lambda l: _LEVEL_RANK[l]),
                       level_words=" ".join(w for w in words[:k] if LEVEL_WORDS[w.lower()]),
                       core=" ".join(words[k:]))
    # A qualifier narrows the demand (PATTERNS.md P6); it gets its own column so
    # the key is the demand alone.
    q = atom._qualifier(out["core"]) if atom._use_pos() else None
    out["qualifier"] = ""
    if q and q[2] == "narrow" and q[0]:
        out["core"], out["qualifier"] = q[0], q[1]
    # Languages are a closed set and are written a hundred ways (`Fluent English`,
    # `Excellent written and verbal English skills`, `Knowledge of English`):
    # one key per language, the modes in their own column.
    out["modes"] = ""
    mm = _MODES_RE.search(out["core"])
    lang_core = _MODES_RE.sub(" ", out["core"]) if mm else out["core"]
    lang_core = re.sub(r"\s+(?:language|languages|skills?)$", "", re.sub(r"\s{2,}", " ", lang_core).strip(" ,"),
                       flags=re.I)
    lang_core = re.sub(r"^(?:in|of)\s+", "", lang_core, flags=re.I)
    if _LANG_ONLY_RE.match(lang_core):
        out.update(head_group="language", core=lang_core.title(),
                   modes=mm.group(0).strip().lower() if mm else "")
    out["key"] = f"{out['head_group']}: {out['core']}" if out["head_group"] else out["core"]
    return out


_MODES_RE = re.compile(
    r"\b(?:both\s+)?(?:(?:in\s+)?(?:written|spoken|oral|verbal|orally)(?:\s+(?:and|&|as well as)\s+"
    r"(?:written|spoken|oral|verbal|orally|in\s+writing))?|in\s+writing(?:\s+and\s+(?:speech|orally))?)\b", re.I)
_LANG_ONLY_RE = re.compile(rf"^(?:the\s+)?(?:{atom._LANGS})$", re.I)
