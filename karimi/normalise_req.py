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
    r"\b(?P<vague>several|many|a\s+few|multiple|some|a\s+couple\s+of|first)\s+years?(?:\s+of)?\b|"
    # `Multi-year experience`, from German `Mehrjährige Erfahrung` (rules 0.3.0):
    # it was the core, `experience: Multi-year`, and the object went to `extra`.
    r"\b(?P<multi>multi-?years?|multiple-years?)\b",
    re.I)

# The frame nouns a requirement is asked through, by group. A closed set: the
# ways a job ad asks for something, not what it asks for.
HEAD_GROUPS = {
    "competence": ["knowledge", "understanding", "familiarity", "proficiency", "expertise",
                   "mastery", "command", "grasp", "awareness", "know-how", "skills", "skill",
                   "fluency",
                   # the same frames as adjectives (rules 0.3.0): `Proficient with Windows`
                   # had no head, so its whole text was the key
                   "proficient", "familiar", "knowledgeable", "skilled", "versed", "conversant",
                   # `competencies`, and `use of Excel` (only opening the requirement:
                   # `tool use` is not a frame; `_LEAD_ONLY`)
                   "competencies", "competences", "competency", "use", "usage"],
    "experience": ["experience", "background", "track record", "exposure", "experienced"],
    "ability": ["ability", "capacity", "capability", "aptitude", "abilities", "capabilities", "capacities"],
}
# Frames that count only at the start, after level words: `Use of Excel` is
# Excel, `AI use` is not `AI`.
_LEAD_ONLY = {"use", "usage"}
_HEAD_OF = {h: g for g, hs in HEAD_GROUPS.items() for h in hs}
# What the frame noun itself says about the level (`familiarity` is less than
# `expertise`), kept so that grouping on `competence` loses nothing.
HEAD_LEVEL = {"familiarity": "basic", "awareness": "basic", "exposure": "basic",
              "proficiency": "advanced", "command": "advanced", "fluency": "strong", "expertise": "expert",
              "mastery": "expert", "proficient": "advanced", "familiar": "basic", "versed": "good",
              "skilled": "good", "knowledgeable": "good", "conversant": "good"}

# Where a requirement is grouped (rules 0.3.0, decided by the user 2026-11-10):
# `Experience with Python`, `Knowledge of Python` and `Python skills` are ONE
# requirement, Python, and how it was asked stays in `head_group` like years
# and level. Languages and education keep a space of their own, since `English`
# the language and `education: Physics` the degree are not `Physics` the field.
SPACES = ("language", "education")


def space(head_group: str) -> str:
    return head_group if head_group in SPACES else ""


def key(head_group: str, core: str) -> str:
    """The grouping key: the core, in its space."""
    s = space(head_group)
    return f"{s}: {core}" if s else core


def display(space_: str, core: str) -> str:
    """How a reader names a requirement: `Python`, `English`, `Education in Physics`."""
    if not core:
        return ""
    if space_ == "education":
        return "Education (any field)" if core == "any field" else f"Education in {core}"
    if " " not in core and core.islower() and core.endswith("al"):
        # `analytical` is what is left of `Strong analytical skills`
        return f"{core[:1].upper()}{core[1:]} skills"
    return core[:1].upper() + core[1:] if core[:1].islower() else core


# Education (rules 0.3.0, the user's call 2026-11-10): `MSc in Physics`, `PhD in
# Physics` and `Degree in Physics` are one group, `education: Physics`, and the
# degree goes to its own column, as years go for experience.
DEGREES = [
    (r"bachelor(?:'s|’s|s)?|b\.?\s?sc\.?|b\.?\s?a\.?|b\.?\s?eng\.?|undergraduate|licen[cs]e|laurea triennale", "bachelor"),
    (r"master(?:'s|’s|s)?|m\.?\s?sc\.?|m\.?\s?a\.?|m\.?\s?eng\.?|postgraduate|diplom|laurea magistrale",
     "master"),
    (r"ph\.?\s?d\.?|doctorate|doctoral|doktor(?:at)?", "phd"),
    (r"mba", "mba"),
    (r"(?:university\s+|academic\s+|engineering\s+|technical\s+|college\s+|higher\s+)?(?:degree|diploma|"
     r"studies|study|education|qualification|graduate)", "degree"),
]
_DEGREE_ALT = "|".join(f"(?:{p})" for p, _ in DEGREES)
_EDU_RE = re.compile(
    rf"^(?P<pre>(?:[\w'’-]+\s+){{0,3}}?)(?P<deg>(?:{_DEGREE_ALT})(?:\s+(?:degree|diploma|studies|programme|program))?)"
    r"(?:\s*\([^)]*\))?(?:\s+(?:degree|diploma))?\s+(?:in|of|on)\s+(?:the\s+)?(?:field\s+of\s+)?(?P<field>.+)$",
    re.I)
_EDU_BARE_RE = re.compile(rf"^(?P<pre>(?:[\w'’-]+\s+){{0,3}}?)(?P<deg>{_DEGREE_ALT})(?:\s+(?:degree|diploma))?$",
                          re.I)
_STUDENT_RE = re.compile(r"\b(?:ongoing|current|currently|enrolled|pursuing|final[- ]year)\b", re.I)


def _degree(words: str, pre: str) -> str:
    if _STUDENT_RE.search(pre):
        return "student"
    w = words.strip().lower()
    for p, level in DEGREES:
        if re.fullmatch(rf"(?:{p})(?:\s+(?:degree|diploma|studies|programme|program))?", w, re.I):
            return level
    return "degree"


def _education(text: str) -> dict | None:
    """`Completed studies in Computer Science` -> education / degree / `Computer Science`."""
    m = _EDU_RE.match(text) or _EDU_BARE_RE.match(text)
    if not m:
        return None
    pre = m.group("pre") or ""
    # Only degree and evidence words in front: `Experience in a degree ...` is not one.
    if any(w.lower() not in _EDU_PRE for w in pre.split()):
        return None
    field = m.groupdict().get("field") or ""
    field = re.sub(r"^(?:a|an|the)\s+", "", field.strip(" ,.:-"), flags=re.I)
    field = re.sub(r"^(?:subject|discipline|field|area)s?\s+(?:of|in)\s+", "", field, flags=re.I)
    # `(economic) computer science`, `Computer Science (or equivalent)`: the field is outside the brackets
    field = re.sub(r"\s{2,}", " ", re.sub(r"\s*\([^()]*\)\s*", " ", field)).strip()
    return {"head": m.group("deg").strip(), "head_group": "education", "degree": _degree(m.group("deg"), pre),
            "core": field or "any field"}


_EDU_PRE = {"a", "an", "the", "completed", "complete", "finished", "successfully", "successful", "relevant",
            "related", "university", "academic", "technical", "higher", "ongoing", "current", "currently",
            "enrolled", "pursuing", "final-year", "recognised", "recognized", "accredited", "formal",
            "first", "second", "good", "excellent", "strong", "solid", "appropriate", "suitable", "minimum",
            "at", "least", "of", "or", "equivalent", "advanced", "scientific", "engineering", "college"}
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
    # Evidence words, not objects (rules 0.3.0): `related experience as a Data
    # Scientist` had the core `related`, `Overall understanding of ...` `Overall`.
    "related": "", "similar": "", "comparable": "", "overall": "", "general": "",
    # `Ideally Excel` is Excel, marked optional (`atomise.nice_to_have`)
    "ideally": "", "preferably": "", "especially": "", "particularly": "",
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
    if m.group("vague") or m.group("multi"):
        lo = hi = None
        raw = (m.group("vague") or m.group("multi")).lower()
    else:
        lo = int(m.group("a"))
        hi = int(m.group("b")) if m.group("b") else (None if m.group("plus") or "least" in m.group(0).lower()
                                                     or "minimum" in m.group(0).lower() else lo)
        raw = m.group(0).strip()
    rest = re.sub(r"\s{2,}", " ", (text[: m.start()] + " " + text[m.end():])).strip(" ,.-")
    return rest, lo, hi, raw


def _named(text: str) -> bool:
    """A capital or a digit anywhere, the first letter included: `Python` alone is a name here,
    where `names` reads a first capital as the start of a sentence."""
    return any(ch.isupper() or ch.isdigit() for ch in text)


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
           "level_words": "", "head": "", "head_group": "", "degree": "", "core": rest, "extra": ""}
    edu = _education(rest)
    if edu:
        out.update(edu, qualifier="", modes="")
        out["space"] = space(out["head_group"])
        out["key"] = key(out["head_group"], out["core"])
        return out
    m = _HEAD_RE2.match(rest)
    if m and m.group("head").lower() in _LEAD_ONLY and (
            any(w.lower() not in LEVEL_WORDS for w in m.group("pre").split())
            or not re.match(r"\s+(?:of|in)\s", m.group("post"))):
        m = None
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
        post_obj = re.sub(r"^(?:of|in|with|on|for|at|to|regarding|around|within|across|as|using)\s+", "",
                          post, flags=re.I) if post else ""
        if object_words and post_obj != post.strip() and _named(post_obj) and not _named(" ".join(object_words)):
            # `Good programming knowledge in Python`: the words in front say what
            # kind, the name after the preposition is what is asked (rules 0.3.0;
            # the core was `programming`, and Python went to `extra`).
            core, extra = post_obj, " ".join(object_words)
        elif object_words:
            core, extra = " ".join(object_words), post.strip(" ,.:-")
        else:
            core, extra = post_obj, ""
        # `Python for modelling, data analysis and automation`: what it is for
        # goes to `extra`, the name is the requirement.
        fm = re.match(r"^(?P<obj>.+?)\s+for\s+(?P<why>.+)$", core)
        if fm and _named(fm.group("obj")) and not _named(fm.group("why")):
            core, extra = fm.group("obj"), " ".join(x for x in (extra, f"for {fm.group('why')}") if x)
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
    # `Speak English fluently` (rules 0.3.0): the verb and the adverb say how,
    # the language is the demand.
    spoken = _SPEAK_RE.match(lang_core)
    if spoken:
        lang_core = spoken.group("lang")
    # `English (B2)`, `level of English`, `English required`, `technical
    # English`, `communication in English`, `German is a plus`: one language
    # with words around it that say how much or how, one key (rules 0.3.0; the
    # site listed 15 Englishes).
    cefr = _CEFR_RE.search(lang_core)
    bare = _LANG_NOISE_RE.sub(" ", _CEFR_RE.sub(" ", lang_core))
    bare = re.sub(r"[()\s,:-]+", " ", bare).strip()
    if not _LANG_ONLY_RE.match(lang_core) and _LANG_ONLY_RE.match(bare):
        lang_core = bare
    elif not _LANG_ONLY_RE.match(lang_core):
        # Word by word, for what the phrases above miss (`Communicate in English`,
        # `High level of English`, `English, both in speech and writing`): one
        # language, and every other word says how much or how.
        words = re.findall(r"[^\W\d_]+|[ABCabc][12]", out["core"])
        langs = {w.title() for w in words if _LANG_ONLY_RE.match(w)}
        if len(langs) == 1 and all(_LANG_ONLY_RE.match(w) or w.lower() in _LANG_FILLER
                                   or re.fullmatch(r"[ABCabc][12]", w) for w in words):
            lang_core = langs.pop()
    if _LANG_ONLY_RE.match(lang_core):
        out.update(head_group="language", core=lang_core.title(),
                   modes=mm.group(0).strip().lower() if mm else "")
        if spoken and spoken.group("how") and not out["level"]:
            out.update(level="strong", level_words=spoken.group("how").lower())
        if cefr and not out["level_words"]:
            out["level_words"] = cefr.group("cefr").upper()
            out["level"] = out["level"] or _CEFR_LEVEL[cefr.group("cefr")[0].upper()]
    elif out["core"]:
        # An example in brackets at the end says which, not what (rules 0.3.0):
        # `Containerization (Docker)` is Containerization, Docker goes to `extra`.
        # And a preposition left in front names nothing (`In Python`).
        pm = re.match(r"^(?P<c>.+?)\s*\((?P<p>[^()]+)\)$", out["core"])
        if pm:
            out["core"] = pm.group("c")
            out["extra"] = " ".join(x for x in (out["extra"], pm.group("p")) if x)
        out["core"] = re.sub(r"^(?:in|of|with|on|for)\s+(?=\S)", "", out["core"], flags=re.I)
        # Degree words after the frame (`Safe handling of especially Excel`,
        # `use of in particular Excel`): the level, not the object.
        out["core"] = re.sub(r"^(?:in particular|expert-level)\s+(?=\S)", "", out["core"], flags=re.I)
        lead = out["core"].split()
        k = 0
        while k < len(lead) - 1 and lead[k].lower() in LEVEL_WORDS:
            k += 1
        if k:
            if not out["level"]:
                lv = [LEVEL_WORDS[w.lower()] for w in lead[:k]]
                out["level"] = max(lv, key=lambda l: _LEVEL_RANK[l])
            out["core"] = " ".join(lead[k:])
        # Product names written several ways (`Golang`, `PowerBI`, `MS Office`):
        # one spelling, from a closed list (`ALIASES`). Then what names nothing.
        out["core"] = ALIASES.get(canon(out["core"]), out["core"])
        if canon(out["core"]) in JUNK or all(w.lower() in LEVEL_WORDS for w in out["core"].split()):
            out["core"] = ""
    # Grouped on the core alone, in its space (`key`, decided 2026-11-10): how it
    # was asked is in `head_group`, as years are in `years_*`.
    out["space"] = space(out["head_group"])
    out["key"] = key(out["head_group"], out["core"])
    return out


_CEFR_RE = re.compile(r"\b(?:(?:at\s+least|min(?:imum)?\.?)\s*)?(?:level\s+)?(?P<cefr>[ABCabc][12])\b(?:\s*level)?(?:\s*or\s+(?:higher|above))?")
_CEFR_LEVEL = {"A": "basic", "B": "good", "C": "strong"}
# The words that may stand around ONE language name and leave it the requirement.
_LANG_FILLER = {
    "communicate", "communicating", "communication", "speak", "speaks", "speaking", "spoken", "speech", "write",
    "writes", "writing", "written", "read", "reading", "oral", "orally", "verbal", "verbally", "are", "is", "be",
    "you", "fluent", "fluently", "fluency", "level", "knowledge", "command", "control", "mastery", "proficiency",
    "proficient", "skills", "skill", "high", "good", "very", "excellent", "clear", "current", "professional",
    "business", "technical", "strong", "solid", "basic", "native", "advanced", "working", "conversational",
    "in", "of", "and", "both", "with", "a", "an", "the", "at", "least", "min", "minimum", "required",
    "mandatory", "plus", "asset", "advantage", "as", "well", "language", "languages", "word", "words", "perfect",
    "perfectly", "full", "complete", "proven", "demonstrated", "ability", "able", "to", "must", "have", "has",
    "or", "equivalent", "certified", "certification", "nice"}
_LANG_NOISE_RE = re.compile(
    r"\b(?:is\s+(?:a\s+(?:strong\s+|big\s+)?plus|an?\s+(?:asset|advantage)|desirable|preferred|required|mandatory)|"
    r"required|mandatory|preferred|essential|"
    r"you\s+are\s+fluent\s+in|(?:with\s+)?(?:a\s+)?(?:good|very\s+good|excellent|strong|solid|basic)?\s*"
    r"(?:knowledge|command|control|mastery|proficiency|level|fluency|communication|skills)\s+(?:of|in)|"
    r"fluent\s+in|proficient\s+in|"
    r"technical|business|professional|current|conversational|working|native|fluent|good|very|excellent|"
    r"in\s+words?\s+and\s+(?:in\s+)?writing|language|languages|communication|skills?|level)\b",
    re.I)

# One spelling for a product or a standard written several ways (rules 0.3.0,
# from the duplicates on the site's explorer, 2026-11-10). Keys are `canon`
# forms. A closed list: what an embedding cannot merge because the NAMES differ
# (`names` keeps `Golang` and `Go` apart, rightly for unknown pairs).
ALIASES = {
    "golang": "Go", "powerbi": "Power BI", "power bi": "Power BI", "microsoft power bi": "Power BI",
    "ms office": "Microsoft Office", "microsoft office": "Microsoft Office",
    "office package": "Microsoft Office", "office suite": "Microsoft Office", "ms office suite": "Microsoft Office",
    "microsoft office suite": "Microsoft Office", "office": "Microsoft Office",
    "microsoft excel": "Excel", "ms excel": "Excel", "excel": "Excel",
    "microsoft azure": "Azure", "azure cloud": "Azure", "azure": "Azure",
    "google cloud platform": "GCP", "google cloud": "GCP", "gcp": "GCP",
    "amazon web service": "AWS", "aws cloud": "AWS",
    "vue.j": "Vue", "vuej": "Vue", "vue": "Vue", "react.j": "React", "reactj": "React",
    "node": "Node.js", "nodej": "Node.js", "node.j": "Node.js",
    "apache spark": "Spark", "apache kafka": "Kafka", "apache airflow": "Airflow",
    "restful api": "REST APIs", "rest api": "REST APIs", "rest": "REST APIs",
    "k8": "Kubernetes", "postgre": "PostgreSQL", "postgresql": "PostgreSQL", "js": "JavaScript",
    "html5": "HTML", "css3": "CSS", ".net": ".NET", "net": ".NET",
    "ms sql server": "SQL Server", "microsoft sql server": "SQL Server", "mssql": "SQL Server",
    "ci cd pipeline": "CI/CD", "ci/cd pipeline": "CI/CD", "ci/cd": "CI/CD", "ci cd": "CI/CD",
    "infrastructure as code": "Infrastructure as Code", "iac": "Infrastructure as Code",
    "llm": "LLMs", "large language model": "LLMs",
    "ml": "machine learning", "artificial intelligence": "AI",
    # keys are `canon` forms, so `licence` is already `license`
    "driving license": "Driving licence", "driving license b": "Driving licence", "driver's license": "Driving licence",
    "valid driver's license": "Driving licence", "valid driving license": "Driving licence",
    "git version control": "Git",
}
# Cores that name nothing once the frame and level are out: debris of a split.
JUNK = {"of", "one", "you have", "ideally", "preferably", "minimum", "confirmed", "consolidated", "successful",
        "specific", "direct", "clear", "full", "high", "foundational", "general", "expert level", "senior level",
        "multi year", "language", "interest", "unit", "equivalent", "equivalent through", "relevant", "similar",
        "comparable", "required", "mandatory", "plus", "asset", "advantage", "other", "etc", "various", "good",
        "ability", "skill", "knowledge", "experience", "competence", "understanding"}

_BRITISH = {"modelling": "modeling", "labelling": "labeling", "organisation": "organization",
            "organisational": "organizational", "optimisation": "optimization", "visualisation": "visualization",
            "rigour": "rigor", "behaviour": "behavior", "colour": "color", "licence": "license",
            "programme": "program", "centre": "center", "catalogue": "catalog", "analyse": "analyze",
            "standardisation": "standardization", "digitalisation": "digitalization", "prioritisation": "prioritization",
            "virtualisation": "virtualization", "containerisation": "containerization", "realisation": "realization",
            "specialisation": "specialization", "utilisation": "utilization", "customisation": "customization"}


def canon(core: str) -> str:
    """The form two spellings of one requirement share, for comparison only.

    Case, `’`, a hyphen for a space (`problem-solving`), British spelling
    (`modelling`), and a plural on the last word (`data platforms`). Never
    shown: what a reader sees is the commonest wording of the group."""
    s = core.casefold().replace("’", "'").replace("&", " and ")
    s = re.sub(r"(?<=\w)-(?=\w)", " ", s)
    s = re.sub(r"[^\w+#./' ]+", " ", s)
    words = [_BRITISH.get(w, w) for w in s.split()]
    if words and len(words[-1]) > 3 and words[-1].endswith("s") and not words[-1].endswith(("ss", "us", "sis")):
        words[-1] = words[-1][:-1]
    return " ".join(words)


_SPEAK_RE = re.compile(r"^(?:speak|speaks|speaking|write|writes|read|be)\s+(?P<lang>\w+)"
                       r"(?:\s+(?P<how>fluently|well|fluent|natively))?$", re.I)


_NAME_TOKEN = re.compile(r"[\w+#./-]+")
# Credential words are names wherever they stand: `Master's degree` and
# `Bachelor degree` sit at cosine 0.95 and are different requirements. A closed set.
_CREDENTIALS = {"bachelor", "master", "phd", "msc", "bsc", "mba", "ma", "ba", "graduate",
                "undergraduate", "postgraduate", "doctorate", "doctoral", "diploma", "hbo", "wo",
                "mbo", "associate", "bac", "licence", "license", "certificate", "certification"}


def names(core: str) -> frozenset[str]:
    """The proper names, acronyms and numbers of a core, plural- and case-free.

    The embedding places `degree in Computer Science` and `degree in Computer
    Engineering` at cosine 0.95, and `STP` next to `STL`: one different name is
    one different requirement, however close the rest. A token is a name when
    it holds a digit or a capital anywhere but the start of the first word.
    Grouping (`New project/group_requirements.py`) and dictionary lookup
    (`karimi_normalise.dictionary`) both use this one function.
    """
    out = set()
    for i, tok in enumerate(_NAME_TOKEN.findall(core)):
        if re.sub(r"[^\w]", "", tok.lower()).rstrip("s") in _CREDENTIALS:
            out.add(re.sub(r"[^\w]", "", tok.lower()).rstrip("s"))
            continue
        if any(ch.isdigit() for ch in tok) or any(ch.isupper() for ch in (tok[1:] if i == 0 else tok)):
            t = re.sub(r"[^\w+#]", "", tok.lower())
            out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return frozenset(out)


_MODES_RE = re.compile(
    r"\b(?:both\s+)?(?:(?:in\s+)?(?:written|spoken|oral|verbal|orally)(?:\s+(?:and|&|as well as)\s+"
    r"(?:written|spoken|oral|verbal|orally|in\s+writing))?|in\s+writing(?:\s+and\s+(?:speech|orally))?)\b", re.I)
_LANG_ONLY_RE = re.compile(rf"^(?:the\s+)?(?:{atom._LANGS})$", re.I)
