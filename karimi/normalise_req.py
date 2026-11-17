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
    # a number written out since rules 0.4.3: `At least five years of ...`
    r"\b(?P<a>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen)\s*(?P<plus>\+)?\s*"
    r"(?:(?:-|–|to)\s*(?P<b>\d{1,2})\s*\+?\s*)?"
    r"(?:years?|yrs?)(?:['’]s?)?(?:\s+of)?(?!\w)|"
    # `equivalent years of experience` (rules 0.4.2): no number, and not the core
    r"\b(?P<vague>several|many|a\s+few|multiple|some|a\s+couple\s+of|first|equivalent|relevant|comparable)"
    r"\s+years?(?:\s+of)?\b|"
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
    "experience": ["experience", "experiences", "background", "track record", "exposure", "experienced"],
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
        # the core already names the degree: `Master in Business`, `PhD (any field)`
        return core
    if " " not in core and core.islower() and core.endswith("al"):
        # `analytical` is what is left of `Strong analytical skills`
        return f"{core[:1].upper()}{core[1:]} skills"
    return core[:1].upper() + core[1:] if core[:1].islower() else core


# Education. Rules 0.3.0 grouped `MSc in Physics`, `PhD in Physics` and `Degree
# in Physics` as one, `education: Physics`; the user reversed that on 2026-11-11
# (rules 0.4.0): each degree is its own requirement, `education: Master in
# Physics`, with the level also in the `degree` column. Spellings of one degree
# are that degree (`DEGREES`).
DEGREES = [
    # `BS`, `B.E.`, `B.Tech` and the Dutch `HBO` (university of applied
    # sciences) are bachelors (rules 0.4.2, from the first batch of new
    # postings: `BA/BS Degree in STEM` and `HBO or WO degree` were read as no
    # degree at all). `B.E.` only with its dots: `Be in the office` is a verb.
    # `BS` and `MS` only in capitals: `MS Office` (`atomise._DEG_WORD`).
    # Rules 0.4.3, from batch 2: the French `L3` (third year of the licence),
    # `BSE`, the Canadian `Baccalaureate` and the Italian `triennial degree`.
    (r"bachelor(?:'s|’s|s)?|b\.?\s?sc\.?|b\.?\s?a\.?|(?-i:B\.?S\.?)|b\.\s?e\.|b\.?\s?tech\.?|bba|b\.?\s?eng\.?|"
     r"undergraduate|licen[cs]e|laurea triennale|hbo|(?-i:L3)|bse|baccalaureate|triennial(?=\s+degree)", "bachelor"),
    # `Master 2`, the French second year of the master (rules 0.4.3)
    (r"master\s*2(?!\d)|master(?:'s|’s|s)?|m\.?\s?sc\.?|m\.?\s?a\.?|(?-i:M\.?S\.?)|m\.?\s?tech\.?|mca|m\.?\s?eng\.?|"
     r"postgraduate|diplom|laurea magistrale", "master"),
    (r"ph\.?\s?d\.?|doctorate|doctoral|doktor(?:at)?", "phd"),
    (r"mba", "mba"),
    # The French level, years after the baccalauréat (rules 0.4.1): Bac+3 is
    # the licence, Bac+4/5 the master, Bac+8 the doctorate. A range (`Bac+3 à
    # Bac+5`) is read at its lowest step, the minimum the employer accepts.
    # `Bachelor's degree+5` is the translator's `Bac+5`, and `Bachelor's
    # degree student +4/5` its `Étudiant Bac+4/5` (rules 0.4.2).
    (r"(?:bac|bachelor(?:'s|’s)?\s+degree)(?:\s+student)?\s*\+\s*\d"
     r"(?:\s*(?:/|-|to|à|a|or|ou)\s*(?:bac\s*)?\+?\s*\d)?", "bac"),
    # `Associate's degree` and the Dutch `WO` (research university) name no
    # level the columns hold: a degree. `WO` only where it cannot be a word
    # (rules 0.4.2).
    # The Dutch `MBO` (vocational) too, rules 0.4.3: `Minimum completed MBO or
    # HBO training`.
    (r"associate(?:'s|’s)?(?=\s+degree)|(?-i:WO)(?=[\s-]+(?:degree|diploma|level|niveau|in|bachelor|master|training)\b"
     r"|$)|(?-i:MBO)",
     "degree"),
    (r"(?:university\s+|academic\s+|engineering\s+|technical\s+|college\s+|higher\s+)?(?:degree|diploma|"
     r"studies|study|education|qualification|graduate)", "degree"),
]
_DEGREE_ALT = "|".join(f"(?:{p})" for p, _ in DEGREES)
# Words after the degree that are still the degree (rules 0.4.1: `Bac+5
# training in`, `Master's student in`, `BAC+3 specialized in`).
_DEG_SUFFIX = (r"(?:\s+(?:degree|diploma|studies|programme|program|training|qualification|level|holder|student|"
               r"speciali[sz]ed|higher\s+education|course))*")
_EDU_RE = re.compile(
    rf"^(?P<pre>(?:[\w'’-]+\s+){{0,3}}?)(?P<deg>(?:{_DEGREE_ALT}){_DEG_SUFFIX})"
    r"(?:\s*\([^)]*\))?(?:\s+(?:degree|diploma))?"
    # `Bachelor's degree required in X`, `A bachelor's degree, or equivalent
    # in X`, `Master's degree, preferably in X` (rules 0.4.2); several, and
    # `minimum`, `strongly preferred` since 0.4.3 (`Bac +3 training minimum,
    # ideally in trade`, `PhD strongly preferred in Biology`)
    r"(?:\s*,?\s+(?:minimum|required|(?:strongly\s+|highly\s+)?preferred|mandatory|preferably|ideally|"
    r"or\s+equivalent))*\s+"
    # `with specialisation in` (rules 0.4.2): the guard on `_EDU_NOPREP_RE`
    # works now, and it had been the only path to these; `towards` (0.4.3) is
    # the translator's Dutch `richting`
    r"(?:in|of|on|towards?|in\s+the\s+direction\s+of|"
    r"with\s+(?:an?\s+)?(?:speciali[sz]ation|focus|major|concentration|emphasis)\s+(?:in|on))\s+"
    r"(?:the\s+)?(?:field\s+of\s+)?(?P<field>.+)$",
    re.I)
# A bracket after a bare degree names it again or says nothing of a field
# (rules 0.4.3): `Bachelor's degree (Graduate)`, `Master's degree (MSc)`.
_EDU_BARE_RE = re.compile(rf"^(?P<pre>(?:[\w'’-]+\s+){{0,3}}?)(?P<deg>(?:{_DEGREE_ALT}){_DEG_SUFFIX})"
                          r"(?:\s*\([^)]*\))?(?:\s+(?:minimum|obtained|completed|required))?$", re.I)
# `HBO Electrical engineering`, `Completed HBO IT` (rules 0.4.3): the Dutch
# levels before a field with no preposition, as the translator writes them.
_EDU_HBO_RE = re.compile(
    r"^(?P<pre>(?:[\w'’-]+\s+){0,3}?)(?P<deg>(?-i:HBO|WO|MBO)(?:[\s-]+(?:training|education|degree|diploma|level))?)"
    r"\s+(?!(?:or|and|of|level|work|training|education)\b)(?P<field>(?-i:[A-Z])[^,;]*)$", re.I)
# `Master's degree Signal Processing`: the field with no `in`, only after the
# word `degree`, and not opening on a word that starts something else. 0.4.1.
# The guard closed on a backspace, not `\b`, until rules 0.4.2, so it never
# stopped anything: `Master's degree and 4 years` had the field `and 4 years`.
_EDU_NOPREP_RE = re.compile(
    rf"^(?P<pre>(?:[\w'’-]+\s+){{0,3}}?)(?P<deg>(?:{_DEGREE_ALT})\s+degree)\s+"
    r"(?!(?:with|or|and|from|at|for|to|by|as|obtained|completed|required|holder|preferably|ideally|is|are)\b)"
    r"(?P<field>[^\W\d_][^,;+]*)$", re.I)
_STUDENT_RE = re.compile(r"\b(?:ongoing|current|currently|enrolled|pursuing|final[- ]year)\b", re.I)
_BAC_STEP = {2: "degree", 3: "bachelor", 4: "master", 5: "master", 6: "master", 7: "master", 8: "phd"}
# `Master of Science in Physics`: `of Science` names the degree, not the field (rules 0.4.1)
_DEGREE_NAME_RE = re.compile(r"^(?:(?:applied\s+)?sciences?|arts|engineering|technology|commerce|laws?)\s+(?:in|of)\s+",
                             re.I)
_DEGREE_START_RE = re.compile(rf"^(?:{_DEGREE_ALT})\b", re.I)


def _degree(words: str, pre: str) -> str:
    if _STUDENT_RE.search(pre):
        return "student"
    # Case kept: `BS` and `MS` are degrees only in capitals (rules 0.4.2)
    w = words.strip()
    # `\b`, not a backspace: the 0.4.1 patch wrote it through a shell heredoc,
    # so `Master's student` was never read as a student (rules 0.4.2)
    if re.search(r"\bstudent\b", w, re.I):
        return "student"
    w = re.sub(r"(?:\s+(?:training|qualification|level|holder|speciali[sz]ed|higher\s+education))+$", "", w,
               flags=re.I)
    bac = re.match(r"(?:bac|bachelor(?:'s|’s)?\s+degree)\s*\+\s*(\d)", w, re.I)
    if bac:
        return _BAC_STEP.get(int(bac.group(1)), "degree")
    for p, level in DEGREES:
        if re.fullmatch(rf"(?:{p})(?:\s+(?:degree|diploma|studies|programme|program))?", w, re.I):
            return level
    return "degree"


_SLASH_DEGREES_RE = re.compile(rf"^(?P<a>(?:{_DEGREE_ALT}))\s*/\s*(?P<b>(?:{_DEGREE_ALT}))(?=\s|$)", re.I)


def _education(text: str) -> dict | None:
    """`Completed studies in Computer Science` -> education / degree / `Computer Science`."""
    s = _SLASH_DEGREES_RE.match(text)
    if s and _degree(s.group("a"), "") == _degree(s.group("b"), ""):
        # `BA/BS degree`: one degree written two ways. Two levels stay unread,
        # for the splitter and the inspector (rules 0.4.2).
        text = s.group("a") + text[s.end():]
    m = _EDU_RE.match(text) or _EDU_BARE_RE.match(text) or _EDU_NOPREP_RE.match(text) or _EDU_HBO_RE.match(text)
    if not m:
        return None
    pre = m.group("pre") or ""
    # Only degree and evidence words in front: `Experience in a degree ...` is not one.
    if any(w.lower() not in _EDU_PRE for w in pre.split()):
        return None
    field = m.groupdict().get("field") or ""
    field = re.sub(r"^(?:a|an|the)\s+", "", field.strip(" ,.:-"), flags=re.I)
    field = re.sub(r"^(?:subject|discipline|field|area)s?\s+(?:of|in)\s+", "", field, flags=re.I)
    # `Data Science or a related field`: filler, as the splitter drops it (rules 0.4.2)
    field = re.sub(r"\s*,?\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:related|similar|equivalent|comparable|relevant)"
                   r"(?:\s+\w+)?\s+(?:fields?|disciplines?|areas?|subjects?|studies|degrees?|qualifications?|"
                   r"education|programs?|programmes?|directions?)$", "", field, flags=re.I)
    # `computer science with specialization in cybersecurity`: the field is the first (rules 0.4.3)
    field = re.sub(r"\s+with\s+(?:an?\s+)?(?:speciali[sz]ation|focus|major|concentration|emphasis)\s+(?:in|on)\s+.+$",
                   "", field, flags=re.I)
    # `(economic) computer science`, `Computer Science (or equivalent)`: the field is outside the brackets
    field = re.sub(r"\s{2,}", " ", re.sub(r"\s*\([^()]*\)\s*", " ", field)).strip()
    field = _DEGREE_NAME_RE.sub("", field)
    if re.fullmatch(atom._SCHOOL, field, re.I):
        # `Bac+4/5 in Business School` says where, not what (rules 0.4.2)
        field = ""
    degree = _degree(m.group("deg"), pre)
    # A degree named inside the field (`Degree of Master of Science`, `Graduate
    # in Bachelor's`): the inner one is the requirement. Under a named outer
    # degree only its field is taken. Rules 0.4.1.
    inner = _education(field) if _DEGREE_START_RE.match(field) else None
    if inner and inner["degree"] != "degree":       # `Degree in Education` keeps its field
        if degree == "degree":
            return inner
        field = inner["field"]
    # The degree is part of the requirement (rules 0.4.0, the user's call
    # 2026-11-11): `Master in Business` and `Bachelor in Business` are two, and
    # every spelling of one degree is that degree (`MSc`, `M.Sc.`, `Master's`).
    label = DEGREE_LABEL[degree]
    return {"head": m.group("deg").strip(), "head_group": "education", "degree": degree,
            "core": f"{label} in {field}" if field else f"{label} (any field)", "field": field}


# How each degree is written in a requirement's core and name.
DEGREE_LABEL = {"bachelor": "Bachelor", "master": "Master", "phd": "PhD", "mba": "MBA", "degree": "Degree",
                "student": "Student"}


_EDU_PRE = {"a", "an", "the", "completed", "complete", "finished", "successfully", "successful", "relevant",
            "related", "university", "academic", "technical", "higher", "ongoing", "current", "currently",
            "enrolled", "pursuing", "final-year", "recognised", "recognized", "accredited", "formal",
            "first", "second", "good", "excellent", "strong", "solid", "appropriate", "suitable", "minimum",
            "at", "least", "of", "or", "equivalent", "advanced", "scientific", "engineering", "college",
            "graduated", "from", "diploma"}
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
    # rules 0.4.3: `equivalent research experience`, `directly related professional experience`
    "equivalent": "", "directly": "",
    # `Ideally Excel` is Excel, marked optional (`atomise.nice_to_have`)
    "ideally": "", "preferably": "", "especially": "", "particularly": "",
}
_LEVEL_RANK = {"": 0, "basic": 1, "good": 2, "strong": 3, "advanced": 3, "expert": 4}
_HEAD_RE2 = re.compile(
    r"^(?P<pre>(?:[\w'’-]+\s+){0,4}?)(?P<head>track record|know-how|"
    + "|".join(sorted((h for h in _HEAD_OF if " " not in h and h != "know-how"), key=len, reverse=True))
    + r")\b(?P<post>.*)$", re.I)


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15}


def _years(text: str) -> tuple[str, int | None, int | None, str]:
    m = _YEARS_RE.search(text)
    if not m:
        return text, None, None, ""
    if m.group("vague") or m.group("multi"):
        lo = hi = None
        raw = (m.group("vague") or m.group("multi")).lower()
    else:
        lo = int(m.group("a")) if m.group("a").isdigit() else _NUMBER_WORDS[m.group("a").lower()]
        hi = int(m.group("b")) if m.group("b") else (None if m.group("plus") or "least" in m.group(0).lower()
                                                     or "minimum" in m.group(0).lower() else lo)
        raw = m.group(0).strip()
    rest = re.sub(r"\s{2,}", " ", (text[: m.start()] + " " + text[m.end():])).strip(" ,.-")
    return rest, lo, hi, raw


# How much the employer wants it, closing the requirement: `PhD is a plus`,
# `Master's preferred`, `Python (preferred)`. Whether it counts is decided on
# the atom (`atomise.nice_to_have`); the requirement is what comes before.
# Left in, it was part of the core (`Python is a plus`, `Master's preferred`
# read as no degree): 100 atoms of the 16,098 in the first batch of new
# postings, 2026-11-15. Rules 0.4.2. `asset`, `plus` and `benefit` only after
# a verb or an article: `digital asset` is a requirement.
_ADJ = (r"(?:big|strong|real|huge|definite|great|significant|distinct|nice|clear|additional|major|key|"
        r"express|added|particular|decisive|important)")
_BE = r"(?:(?:(?:this|that|it|which)\s+)?(?:is|are|would\s+be|will\s+be|being))"
_MARK = (rf"(?:(?:{_BE}|(?:is\s+|are\s+)?(?:also\s+)?considered(?:\s+as)?|seen\s+as)\s+)"
         rf"(?:an?\s+)?(?:{_ADJ}\s+)?(?:plus|advantage|asset|bonus|benefit)|"
         rf"an?\s+(?:{_ADJ}\s+)?(?:plus|advantage|bonus)|"
         rf"(?:{_BE}\s+)?(?:(?:very|highly|strongly|much)\s+)?(?:preferred|desirable|advantageous)|"
         rf"{_BE}\s+(?:(?:very|highly|much)\s+)?(?:beneficial|appreciated|welcome|valued|desired)|"
         rf"(?:{_BE}\s+)?nice[- ]to[- ]have|"
         # Rules 0.4.3, from batch 2: how the translator writes the French
         # `apprécié(e)`, `valorisé`, `vítány` and the German `von Vorteil` —
         # no verb in front (`Green Belt appreciated`, `SAP Advantage`,
         # `programming advantage`, `languages of advantage`). Not after
         # `competitive` or `strategic`, where the advantage is the object.
         r"(?:(?:very|highly|much|also)\s+)?(?:appreciated|valued|welcome|desired)|"
         r"(?<!competitive\s)(?<!strategic\s)(?:of\s+)?advantage|"
         # `is a plus, but not required`: optional said twice
         rf"(?:(?:{_BE}\s+)?an?\s+(?:{_ADJ}\s+)?plus,?\s*)?(?:but|though)\s+not\s+(?:required|mandatory|essential)")
# The marker alone in a bracket, or bare at a word's start: `(AWS preferred)`
# names AWS and stays for the bracket rule, and `software preferred` is not
# `softw` + `are preferred`.
_OPTIONAL_TAIL_RE = re.compile(rf"\s*[,;:–—-]?\s*(?:\(\s*(?:{_MARK})\s*\)|\b(?:{_MARK}))\s*[.!]?$", re.I)
# Opening the requirement (rules 0.4.3; `optional_head` in the archivist's
# catalogue): `Desirable experience in design` was read as `Desirable`.
# `Preferred` only before a frame word: `Preferred Shares` is a name.
_OPTIONAL_HEAD_RE = re.compile(
    r"^(?:desirable|desired|advantageous|optional(?:ly)?|nice[- ]to[- ]have|an?\s+plus|bonus|"
    r"preferred(?=\s+(?:experience|knowledge|skills?|qualifications?|background|familiarity|exposure)\b))"
    r"\s*:?\s+(?=\S)", re.I)
# Before a closing bracket of examples: `Relevant certifications preferred
# (e.g., CISSP, CISM)` (rules 0.4.3)
_MARK_BEFORE_BRACKET_RE = re.compile(rf"\s+(?:{_MARK})(?=\s*\([^()]*\)\s*[.!]?$)", re.I)


def strip_optional(text: str) -> str:
    """The requirement without the words saying it is optional: closing it
    (`_OPTIONAL_TAIL_RE`), before its examples, or opening it."""
    t = _OPTIONAL_HEAD_RE.sub("", text)
    t = _MARK_BEFORE_BRACKET_RE.sub("", t)
    return _OPTIONAL_TAIL_RE.sub("", t).strip()


# How the requirement is asked, closing it (rules 0.4.3; `required_left` in
# the archivist's catalogue): `U.S. Citizenship is required`, `English B2+
# required`, `Graduation is mandatory`. It is still counted, unlike an
# optional one. Not after `if`, `when`, `as`, `where`, `unless`: `travel when
# required` is a condition.
_REQUIRED_TAIL_RE = re.compile(r"\s*[,;:–—-]?\s*\b(?:(?:is|are)\s+)?(?:required|mandatory|compulsory|a\s+must)"
                               r"\s*[.!]?$", re.I)


def strip_required(text: str) -> str:
    m = _REQUIRED_TAIL_RE.search(text)
    if not m or not text[: m.start()].strip():
        return text
    before = text[: m.start()].split()
    if before and before[-1].lower() in ("if", "when", "as", "where", "unless", "whenever"):
        return text
    return text[: m.start()].strip(" ,;:–—-")


# `or similar`, `or similar role`, `or equivalent tools` closing a requirement
# add nothing (the count guide); after degrees `_education` drops them, and
# here everywhere else (rules 0.4.3, `or_similar_left`). Never `or equivalent
# experience`: that is a second route, counted.
_OR_SIMILAR_TAIL_RE = re.compile(
    r"\s*,?\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:similar|equivalent|comparable|related)"
    r"(?:\s+(?:roles?|positions?|functions?|titles?|tools?|technolog(?:y|ies)|platforms?|solutions?|software|"
    r"languages?|frameworks?|products?|systems?|environments?))?\s*[.]?$", re.I)
# A level after the name, as skill grids write it (rules 0.4.3, `level_left`):
# `Python Advanced`, `LangChain Intermediate`. Not `Visual Basic`, and only
# after a name: `basic` closing a phrase may be the object.
_LEVEL_TAIL_RE = re.compile(
    r"^(?P<obj>.+?)(?<!\bvisual)[\s,(–-]+(?P<lvl>beginner|basic|elementary|intermediate|upper[\s-]intermediate|"
    r"advanced|proficient|confirmed|experienced)\s*\)?$", re.I)
_TAIL_LEVEL = {"beginner": "basic", "basic": "basic", "elementary": "basic", "intermediate": "good",
               "upper intermediate": "good", "upper-intermediate": "good", "proficient": "good",
               "advanced": "strong", "confirmed": "strong", "experienced": "strong"}
# Several frame nouns at once (`Qualifications/experience/knowledge of data
# science`) and a German frame glued on (`CATIA V6-Kenntnisse`, translated
# `CATIA V6-Knowledge`). Rules 0.4.3, from the explorer on batch 2.
_SLASHED_HEADS_RE = re.compile(r"^(?:qualifications?|experience|knowledge|skills?|expertise)"
                               r"(?:\s*/\s*(?:qualifications?|experience|knowledge|skills?|expertise))+\s+(?=of\b|in\b|with\b)",
                               re.I)
_GLUED_HEAD_RE = re.compile(r"(?<=\w)-(?:knowledge|skills|experience|expertise)$", re.I)


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
    text = strip_required(strip_optional(text))
    # `a suitable combination of education, experience and training`: the
    # second route beside a degree, an experience with no object (rules 0.4.3)
    text = re.sub(r"^(?:an?\s+)?(?:suitable|equivalent|relevant|appropriate)\s+combination\s+of\s+.*$",
                  "equivalent experience", text, flags=re.I)
    text = _GLUED_HEAD_RE.sub("", _SLASHED_HEADS_RE.sub("knowledge ", text))
    # `Seven (7) years`, `progressively responsible experience` (rules 0.4.3):
    # the number once, and how the experience grew is not its object
    text = re.sub(r"\b([a-z]+)\s*\((\d{1,2})\)(?=\s+years?\b)", r"\2", text, flags=re.I)
    text = re.sub(r"\b(?:progressively|increasingly)\s+(?:responsible|senior)\s+(?=experience\b)", "", text,
                  flags=re.I)
    rest, lo, hi, years_raw = _years(text)
    if years_raw:
        # `Bachelor's degree (5–7 years experience)`: the years are out, the
        # bracket that held them says nothing more (rules 0.4.2)
        rest = re.sub(r"\s*\(\s*(?:of\s+)?(?:(?:relevant|professional|work|related)\s+)*(?:experience)?\s*\)", "",
                      rest).strip()
    out = {"years_min": lo, "years_max": hi, "years_raw": years_raw, "level": "",
           "level_words": "", "head": "", "head_group": "", "degree": "", "core": rest, "extra": ""}
    edu = _education(rest)
    if edu:
        edu.pop("field")
        out.update(edu, qualifier="", modes="")
        out["space"] = space(out["head_group"])
        out["key"] = key(out["head_group"], out["core"])
        return out
    rest = _OR_SIMILAR_TAIL_RE.sub("", rest).strip()
    tail_level = None
    lv = _LEVEL_TAIL_RE.match(rest)
    if lv and _named(lv.group("obj")) and not _LANG_ONLY_RE.match(lv.group("obj")):
        rest, tail_level = lv.group("obj").strip(" ,(–-"), lv.group("lvl").lower()
    out["core"] = rest
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
        # `about` since rules 0.4.3: `Practical knowledge about microservices` kept `about`
        post_obj = re.sub(r"^(?:of|in|with|on|for|at|to|regarding|about|around|within|across|as|using)\s+", "",
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
    if tail_level and not out["level"]:
        out["level"] = _TAIL_LEVEL.get(re.sub(r"\s+", " ", tail_level), "")
        out["level_words"] = " ".join(x for x in (out["level_words"], tail_level) if x)
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
    "or", "equivalent", "certified", "certification", "nice",
    # the translator's Chinese `听说读写` (listen, speak, read, write) came out
    # `I hear English is very fluent in reading and writing` (rules 0.4.3)
    "i", "hear", "hearing", "listen", "listening"}
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
    "pack office": "Microsoft Office", "office pack": "Microsoft Office",
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
        "through",
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
    # Not an acronym (rules 0.4.3): `IDMS` is not the plural of `IDM`, nor `HRIS` of `HRI`.
    tokens = re.findall(r"[\w+#./']+", core)
    acronym = bool(tokens) and tokens[-1].isupper() and len(tokens[-1]) > 1
    if words and not acronym and len(words[-1]) > 3 and words[-1].endswith("s") \
            and not words[-1].endswith(("ss", "us", "sis")):
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
