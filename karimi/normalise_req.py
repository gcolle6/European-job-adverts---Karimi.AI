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
    # rules 0.4.7: the Portuguese `Domínio em` came out `Domain in` (review of batch 5)
    (r"^domain in\b", "mastery of"),
    (r"\bin-depth learning\b", "deep learning"),
    # rules 0.4.8: the Dutch `is een pré` (a plus) came out `is a preview` / `is a pré`
    (r"\b(is|are)\s+an?\s+(?:preview|pré|pre)\b(?!-)", r"\1 a plus"),
    (r"\b(is|are)\s+an?\s+pre-requisite\b", r"\1 a plus"),
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
# rules 0.4.9, batch 7: `applying`, `using`, `leveraging` say nothing either
# (`Experience applying thorough testing` is testing; 16 rows, all flagged)
_LIGHT_VERBS = {"working", "applying", "using", "utilizing", "utilising", "leveraging", "employing"}
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
    if re.match(r"(?:directly|closely|hands-on|side\s+by\s+side)\b", obj, re.I):
        return text
    if not _name_runs(obj) and not all(v.lower() in _LIGHT_VERBS for v in verbs):
        # `Experience in developing urban plans` keeps `developing` (review of batch 6)
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


_BE_FRAME_RE = re.compile(r"^(?:be|being|are|i\s*['’]?\s*m|i\s+am)\s+(?=(?:familiar|proficient|fluent|comfortable|experienced|skilled|"
                          r"knowledgeable|able)\b)", re.I)


def normalise_requirement(atom: str, translated: bool) -> str:
    out = fix_translation(atom) if translated else atom
    # rules 0.4.8, review of batch 6: `Sufficient technical depth in X`, `Experiences related to X`
    out = re.sub(r"^sufficient\s+(?:technical\s+)?depth\s+(?:in|of)\s+", "Good knowledge of ", out, flags=re.I)
    out = re.sub(r"^((?:\w+\s+)?)(?:technical\s+)?depth\s+(?:in|of)\s+", r"\1knowledge of ", out, flags=re.I)
    out = re.sub(r"\bexperiences?\s+related\s+to\s+", "experience in ", out, flags=re.I)
    out = re.sub(r"^operating\s+knowledge\b", "Working knowledge", out, flags=re.I)
    # `Be familiar with Eth` (rules 0.4.4, batch 3): `Be` was the core
    out = _BE_FRAME_RE.sub("", out)
    out = out[:1].upper() + out[1:] if out != atom else out
    return experience_with(out)


# --- Decomposition: years, level, head, core (decided 2026-11-01) -------------
#
# To group requirements without losing information, what varies around the
# same demand is moved into its own column first: `3+ years of strong hands-on
# experience with Kubernetes` is experience / 3+ years / strong hands-on /
# `Kubernetes`. Grouping then runs on the head group and the core alone, and
# every removed part stays readable in its column.

_YEARS_RE = re.compile(
    r"(?:\b(?:at\s+least|minimum(?:\s+of)?|min\.?|more\s+than|over|up\s+to|max\.?|maximum|approx\.?|"
    r"approximately|around|about|typically|ca\.)\s+)?"
    # a number written out since rules 0.4.3: `At least five years of ...`
    r"(?:\bfrom\s+)?"
    r"\b(?P<a>\d{1,2}(?:[.,]\d)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen)\s*(?P<plus>\+)?\s*"
    r"(?:(?:-|–|to|/)\s*(?P<b>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen)\s*\+?\s*)?"
    r"(?:years?|yrs?|-years?(?=\s+(?:of\s+)?(?:[\w-]+\s+){0,2}(?:experience|background|track)))"
    r"(?:['’]s?)?(?P<plus2>\+)?(?:\s+or\s+more)?(?:\s+(?:minimum|min\.?|at\s+least))?(?:\s+of)?(?!\w)|"
    # months (rules 0.4.9): whole years when there are twelve or more, else only the text
    r"(?:\b(?:at\s+least|minimum(?:\s+of)?|min\.?|more\s+than|over|approx\.?|around|about)\s+)?"
    r"(?<!within\s)(?<![-–\d])\b(?P<mo>\d{1,3})\s*\+?\s*months?(?:\s+(?:minimum|min\.?))?(?:\s+of)?(?!\w)|"
    # `equivalent years of experience` (rules 0.4.2): no number, and not the core
    r"\b(?P<vague>several|many|a\s+few|multiple|some|a\s+couple\s+of|first|equivalent|relevant|comparable)"
    r"\s+years?(?:\s+of)?\b|"
    # `Multi-year experience`, from German `Mehrjährige Erfahrung` (rules 0.3.0):
    # it was the core, `experience: Multi-year`, and the object went to `extra`.
    r"\b(?P<multi>multi-?years?|multiple-years?|multi-?annual)\b",
    re.I)

# The frame nouns a requirement is asked through, by group. A closed set: the
# ways a job ad asks for something, not what it asks for.
HEAD_GROUPS = {
    "competence": ["knowledge", "understanding", "familiarity", "proficiency", "expertise",
                   "mastery", "command", "grasp", "awareness", "know-how", "skills", "skill",
                   "fluency",
                   # the same frames as adjectives (rules 0.3.0): `Proficient with Windows`
                   # had no head, so its whole text was the key
                   "proficient", "familiar", "knowledgeable", "skilled", "versed", "conversant", "comfortable",
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
    # rules 0.4.7, batch 5: the school-leaving diploma, read as no degree at
    # all (`High School Diploma or equivalent`, `Successful middle school
    # degree`). Its own level, below any degree, named `High school diploma`.
    (r"(?:high|secondary|middle)\s+school(?:\s+leaving)?|(?-i:GED)", "school"),
    # `BS`, `B.E.`, `B.Tech` and the Dutch `HBO` (university of applied
    # sciences) are bachelors (rules 0.4.2, from the first batch of new
    # postings: `BA/BS Degree in STEM` and `HBO or WO degree` were read as no
    # degree at all). `B.E.` only with its dots: `Be in the office` is a verb.
    # `BS` and `MS` only in capitals: `MS Office` (`atomise._DEG_WORD`).
    # Rules 0.4.3, from batch 2: the French `L3` (third year of the licence),
    # `BSE`, the Canadian `Baccalaureate` and the Italian `triennial degree`.
    (r"bachelor(?:['’`´]s|s['’`´]?)?|b\.?\s?sc\.?|b\.?\s?a\.?|(?-i:B\.?S\.?)|b\.\s?e\.|b[.-]?\s?tech\.?|bba|b\.?\s?eng\.?|"
     r"undergraduate|licen[cs]e|laurea triennale|hbo\+?|(?-i:L3)|bse|baccalaureate|triennial(?=\s+degree)|"
     # rules 0.4.6: the translator's Italian `Laurea triennale`
     r"three-year(?=\s+degree)|"
     # rules 0.4.4: the translator's Dutch `HBO`, `higher professional education`
     r"higher\s+professional\s+education", "bachelor"),
    # `Master 2`, the French second year of the master (rules 0.4.3)
    (r"master\s*2(?!\d)|master(?:['’`´]s|s['’`´]?)?|m\.?\s?sc\.?|m\.?\s?a\.?|(?-i:M\.?S\.?)|m\.?\s?tech\.?|mca|m\.?\s?eng\.?|"
     r"post[-\s]?graduate|diplom|laurea magistrale", "master"),
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
    (r"associates?(?:'s|’s)?(?=\s+(?:degree|or|and|/))|(?-i:WO)(?=[\s-]+(?:degree|diploma|level|niveau|in|bachelor|master|training|programme|program)\b"
     r"|$)|(?-i:MBO)",
     "degree"),
    (r"(?:university\s+|academic\s+|engineer(?:ing)?\s+|technical\s+|college\s+|higher\s+|national\s+|post-?secondary\s+|"
     r"vocational\s+)?(?:degree|diploma|"
     r"studies|study|education|qualification|graduate)", "degree"),
]
_DEGREE_ALT = "|".join(f"(?:{p})" for p, _ in DEGREES)
# Words after the degree that are still the degree (rules 0.4.1: `Bac+5
# training in`, `Master's student in`, `BAC+3 specialized in`).
_DEG_SUFFIX = (r"(?:\s+(?:degree|diploma|studies|programme|program|training|qualification|level|holder|student|"
               r"speciali[sz]ed|higher\s+education|course))*")
_EDU_RE = re.compile(
    rf"^(?P<pre>(?:[\w'’/-]+,?\s+){{0,5}}?)(?P<deg>(?:{_DEGREE_ALT}){_DEG_SUFFIX})"
    rf"(?:\s*(?:or|/)\s*(?P<deg2>(?:{_DEGREE_ALT}){_DEG_SUFFIX}))?"
    r"(?:\s*\([^)]*\))?(?:\s+(?:degree|diploma))?"
    # `Bachelor's degree required in X`, `A bachelor's degree, or equivalent
    # in X`, `Master's degree, preferably in X` (rules 0.4.2); several, and
    # `minimum`, `strongly preferred` since 0.4.3 (`Bac +3 training minimum,
    # ideally in trade`, `PhD strongly preferred in Biology`)
    r"(?:\s*[,–—-]?\s+(?:minimum|required|(?:strongly\s+|highly\s+)?preferred|mandatory|preferably|ideally|"
    r"or\s+equivalent|completed\s+or\s+(?:currently\s+)?in\s+(?:the\s+)?(?:final|last)\s+(?:semester|year)))*\s+"
    # `with specialisation in` (rules 0.4.2): the guard on `_EDU_NOPREP_RE`
    # works now, and it had been the only path to these; `towards` (0.4.3) is
    # the translator's Dutch `richting`; `within`, `with preference for`, a
    # dash before `preferably` (0.4.4)
    r"(?:in|of|on|en|within|towards?|in\s+the\s+direction\s+of|with\s+(?:a\s+)?preference\s+for|"
    r"with\s+(?:an?\s+)?(?:speciali[sz]ation|focus|major|concentration|emphasis)\s+(?:in|on))\s+"
    r"(?:the\s+)?(?:field\s+of\s+)?(?P<field>.+)$",
    re.I)
# A bracket after a bare degree names it again or says nothing of a field
# (rules 0.4.3): `Bachelor's degree (Graduate)`, `Master's degree (MSc)`.
_EDU_BARE_RE = re.compile(rf"^(?P<pre>(?:[\w'’/-]+,?\s+){{0,5}}?)(?P<deg>(?:{_DEGREE_ALT}){_DEG_SUFFIX})"
                          r"(?:\s*\([^)]*\))?(?:\s+(?:minimum|obtained|completed|required))?$", re.I)
# `HBO Electrical engineering`, `Completed HBO IT` (rules 0.4.3): the Dutch
# levels before a field with no preposition, as the translator writes them.
_EDU_HBO_RE = re.compile(
    r"^(?P<pre>(?:[\w'’-]+,?\s+){0,5}?)(?P<deg>(?-i:HBO|Hbo|WO|MBO|Mbo)(?:[\s-]+(?:training|education|degree|diploma|level))?)"
    r"\s+(?!(?:or|and|of|level|work|training|education)\b)(?P<field>(?-i:[A-Z])[^,;]*)$", re.I)
# `Master's degree Signal Processing`: the field with no `in`, only after the
# word `degree`, and not opening on a word that starts something else. 0.4.1.
# The guard closed on a backspace, not `\b`, until rules 0.4.2, so it never
# stopped anything: `Master's degree and 4 years` had the field `and 4 years`.
_EDU_NOPREP_RE = re.compile(
    rf"^(?P<pre>(?:[\w'’/-]+,?\s+){{0,5}}?)(?P<deg>(?:{_DEGREE_ALT})\s+degree)\s+"
    r"(?!(?:with|or|and|from|at|for|to|by|as|obtained|completed|required|holder|preferably|ideally|is|are)\b)"
    r"(?P<field>[^\W\d_][^,;+]*)$", re.I)
_EDU_CAPFIELD_RE = re.compile(
    r"^(?P<pre>(?:[\w'’/-]+,?\s+){0,5}?)(?P<deg>(?:degree|diploma|bachelor(?:'s|’s)?))\s+"
    r"(?P<field>(?-i:[A-Z])[\w&+-]*(?:\s+(?-i:[A-Z&])[\w&+-]*){0,3})$", re.I)
_STUDENT_RE = re.compile(r"\b(?:ongoing|current|currently|enrolled|pursuing|final[- ]year|following|completing|"
                         r"studying|entering|obtaining|"
                         r"taking|candidate|last\s+year|enrolment)\b",
                         re.I)
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


_SLASH_DEGREES_RE = re.compile(rf"^(?P<a>(?:{_DEGREE_ALT}))\s*[/,]\s*(?P<b>(?:{_DEGREE_ALT}))(?=\s|$)", re.I)


_EDU_FIELD_FIRST_RE = re.compile(
    r"^(?P<pre>(?:[\w'’-]+,?\s+){0,4}?)(?P<field>[A-Za-z][\w&+.-]*(?:\s+[\w&+.-]+){0,2}?)\s+(?P<deg>degree|diploma)"
    r"(?:\s*\([^)]*\))?$", re.I)


def _field_first(text: str):
    """`STEM degree`, `computer science degree`: the field before the word `degree` (rules 0.4.7).
    Only when no word of the field is a degree, level or evidence word: `relevant
    technical degree` is the generic path's."""
    m = _EDU_FIELD_FIRST_RE.match(text)
    if not m:
        return None
    # `A computer science degree`: the evidence words in front are not the field
    words = m.group("field").split()
    k = 0
    while k < len(words) - 1 and words[k].lower().strip(",") in _EDU_PRE:
        k += 1
    pre, field = " ".join([m.group("pre").strip()] + words[:k]).strip(), words[k:]
    if any(w.lower() in _EDU_PRE or w.lower() in LEVEL_WORDS or _DEGREE_START_RE.match(w) for w in field):
        return None
    return _Found(pre=pre, field=" ".join(field), deg=m.group("deg"))


def _pre_ok(pre: str | None) -> bool:
    """Every word in front a degree or evidence word (`Enrolled/Fresh graduated in a`)."""
    return all(w.lower().strip(",") in _EDU_PRE for w in re.split(r"[\s/]+", pre or "") if w)


class _Found(dict):
    """A match read by hand, with the two calls `_education` makes on a regex match."""

    def group(self, k):
        return self[k]

    def groupdict(self):
        return self


def _education(text: str) -> dict | None:
    """`Completed studies in Computer Science` -> education / degree / `Computer Science`."""
    # rules 0.4.7, batch 5: `Master's degree from a top-tier business school`,
    # `Diploma from engineering school`, `Bachelor's Degree or acceptable
    # combination of equivalent experience`
    text = re.sub(r"\s+from\s+(?:an?\s+|the\s+)?(?:[\w-]+\s+){0,4}?(?:school|university|college|institution|institute)s?"
                  r"(?:\s*,?\s*(?:or\s+)?(?:[\w-]+\s+){0,2}(?:school|university|college)s?)*\b", "", text, flags=re.I)
    text = re.sub(r"\s*,?\s+or\s+(?:an?\s+)?(?:acceptable\s+)?(?:combination\s+of\s+)?(?:equivalent|relevant|comparable)"
                  r"(?:\s+in)?\s+(?:(?:professional|work|practical|industry)\s+)?experience.*$", "", text, flags=re.I)
    st = re.match(r"^(?:an?\s+)?(?:(?:current|currently|enrolled|university|undergraduate|graduate|final[- ]year|"
                  r"last[- ]year|master['’]?s?|bachelor['’]?s?)\s+)*students?\s+(?:in|of)\s+(?:the\s+)?(?P<f>[^\W\d_].*)$",
                  text.strip(" ."), re.I)
    if st and not _DEGREE_START_RE.match(st.group("f")):
        f = re.sub(r"\s*,?\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:related|similar|equivalent|relevant)\s+"
                   r"(?:fields?|disciplines?|areas?|subjects?|studies)$", "", st.group("f"), flags=re.I)
        return {"head": "student", "head_group": "education", "degree": "student", "core": f"Student in {f}",
                "field": f}
    text = re.sub(r"^(?:an?\s+)?(?:\d|two|three|four|five)[- ]years?\s+(?=(?:university\s+|college\s+)?"
                  r"(?:degree|diploma|bachelor)\b)", "", text, flags=re.I)
    # [42] `Technical degree`: a degree in a technical field (the user's review of batch 7)
    text = re.sub(r"^technical\s+(degree|diploma|studies|education)\b(?!\s+in\b)", r"\1 in technical field",
                  text, flags=re.I)
    s = _SLASH_DEGREES_RE.match(text)
    if s and _degree(s.group("a"), "") != _degree(s.group("b"), "") and _degree(s.group("a"), "") == "degree":
        text = s.group("b") + text[s.end():]
        s = None
    if s and _degree(s.group("a"), "") == _degree(s.group("b"), ""):
        # `BA/BS degree`: one degree written two ways. Two levels stay unread,
        # for the splitter and the inspector (rules 0.4.2).
        text = s.group("a") + text[s.end():]
    m = _EDU_RE.match(text) or _EDU_BARE_RE.match(text) or _EDU_NOPREP_RE.match(text) or _EDU_HBO_RE.match(text) \
        or _EDU_CAPFIELD_RE.match(text)
    # Only degree and evidence words in front: `Experience in a degree ...` is not one.
    # Otherwise the words in front may be the field: `STEM degree` (rules 0.4.7).
    if not m or not _pre_ok(m.group("pre")):
        m = _field_first(text)
        if not m or not _pre_ok(m.group("pre")):
            return None
    pre = m.group("pre") or ""
    alt = m.groupdict().get("deg2")
    if alt and _degree(alt, pre) != _degree(m.group("deg"), pre):
        # two levels in one atom: the splitter's job, left unread for the inspector
        return None
    field = m.groupdict().get("field") or ""
    field = re.sub(r"^(?:a|an|the)\s+", "", field.strip(" ,.:-"), flags=re.I)
    field = re.sub(r"^(?:subject|discipline|field|area)s?\s+(?:of|in)\s+", "", field, flags=re.I)
    # `Data Science or a related field`: filler, as the splitter drops it (rules 0.4.2)
    field = re.sub(r"\s*,?\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:related|similar|equivalent|comparable|relevant)"
                   r"(?:\s+\w+)?\s+(?:fields?|disciplines?|areas?|subjects?|studies|degrees?|qualifications?|"
                   r"education|programs?|programmes?|directions?)$", "", field, flags=re.I)
    sp = re.match(r"^(?P<w>.+?)\s+with\s+(?:an?\s+)?(?:speciali[sz]ation|major|concentration)\s+(?:in|on)\s+(?P<f>.+)$",
                  field, re.I)
    if sp and re.search(r"\b(?:school|university|college|institute)s?\b", sp.group("w"), re.I):
        field = sp.group("f")
    field = re.sub(r"\s+with\s+an?\s+[\w\s-]+?\s+(?:focus|orientation|emphasis)$", "", field, flags=re.I)
    # `computer science with specialization in cybersecurity`: the field is the first (rules 0.4.3)
    field = re.sub(r"\s+with\s+(?:an?\s+)?(?:speciali[sz]ation|focus|major|concentration|emphasis)\s+(?:in|on)\s+.+$",
                   "", field, flags=re.I)
    # `an appropriate subject` names no field (rules 0.4.4)
    field = re.sub(r"^(?:an?\s+)?technical\s+(?:subject|field|discipline|area|direction|studies)s?$",
                   "technical field", field, flags=re.I)
    if re.fullmatch(r"(?:an?\s+)?(?:appropriate|relevant|related|suitable)\s+(?:subject|field|discipline|"
                    r"area|direction)s?", field, re.I):
        field = ""
    # `(economic) computer science`, `Computer Science (or equivalent)`: the field is outside the brackets
    field = re.sub(r"\s{2,}", " ", re.sub(r"\s*\([^()]*\)\s*", " ", field)).strip()
    field = _DEGREE_NAME_RE.sub("", field)
    if re.fullmatch(atom._SCHOOL, field, re.I):
        # `Bac+4/5 in Business School` says where, not what (rules 0.4.2)
        field = ""
    degree = _degree(m.group("deg"), pre)
    # `Master Data Management` is a field, not a master's degree; under a
    # master, `Master Informatique` is the field `Informatique` (rules 0.4.4)
    if degree == "master" and re.match(r"master(?:'s|’s)?\s+(?!data\b)\S", field, re.I):
        field = re.sub(r"^master(?:'s|’s)?\s+", "", field, flags=re.I)
    inner = _education(field) if _DEGREE_START_RE.match(field) and not re.match(r"master\s+data\b", field, re.I) \
        else None
    # A degree named inside the field (`Degree of Master of Science`, `Graduate
    # in Bachelor's`): the inner one is the requirement. Under a named outer
    # degree only its field is taken. Rules 0.4.1.
    if inner and inner["degree"] != "degree":       # `Degree in Education` keeps its field
        if degree == "degree":
            return inner
        field = inner["field"]
    # The degree is part of the requirement (rules 0.4.0, the user's call
    # 2026-11-11): `Master in Business` and `Bachelor in Business` are two, and
    # every spelling of one degree is that degree (`MSc`, `M.Sc.`, `Master's`).
    label = DEGREE_LABEL[degree]
    if degree == "school":
        # one school-leaving diploma, whatever its stream (rules 0.4.7)
        return {"head": m.group("deg").strip(), "head_group": "education", "degree": degree, "core": label,
                "field": ""}
    return {"head": m.group("deg").strip(), "head_group": "education", "degree": degree,
            "core": f"{label} in {field}" if field else f"{label} (any field)", "field": field}


# How each degree is written in a requirement's core and name.
DEGREE_LABEL = {"school": "High school diploma", "bachelor": "Bachelor", "master": "Master", "phd": "PhD", "mba": "MBA", "degree": "Degree",
                "student": "Student"}


_EDU_PRE = {"a", "an", "the", "any", "completed", "complete", "finished", "successfully", "successful", "relevant",
            "related", "university", "academic", "technical", "higher", "ongoing", "current", "currently",
            "enrolled", "pursuing", "final-year", "recognised", "recognized", "accredited", "formal",
            "first", "second", "good", "excellent", "strong", "solid", "appropriate", "suitable", "minimum",
            "at", "least", "of", "or", "equivalent", "advanced", "scientific", "engineering", "college",
            "graduated", "from", "diploma",
            # rules 0.4.4: `Final-year student Master's degree in X`
            "student", "following", "completing",
            # rules 0.4.7, batch 5: `Currently enrolled in a`, `Be a graduate of a`, `Hold a`,
            # `Possession of a`, `Students pursuing a`, `Currently a candidate for a`
            "in", "taking", "up", "candidate", "for", "be", "hold", "holds", "holding", "possession",
            "possess", "students", "year", "last", "final", "enrolment", "fresh", "freshly", "recent",
            "recently", "obtained", "educated", "to", "ideally", "preferably",
            "very", "two-year", "three-year", "four-year", "one-year", "full-time", "part-time", "majoring",
            # rules 0.4.8, batch 6
            "wo", "hbo", "entering", "studying", "process", "obtaining", "holder", "typically", "requires",
            "require", "such", "an"}
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
    # rules 0.4.4, batch 3: `Ample`, `Vast`, `Real`, `Genuine` were the core
    "ample": "strong", "vast": "strong", "real": "", "genuine": "", "highly": "strong", "high-level": "strong",
    # rules 0.4.7, batch 5: the word in front became the core and the object went to
    # `extra`, or the key was left empty (`High proficiency in Python`, `Perfect
    # command of French`, `Confirmed experience in`, `Foundational knowledge of`)
    "intermediate": "good", "upper-intermediate": "good", "high": "strong", "perfect": "expert",
    "full": "strong", "foundational": "basic", "confirmed": "", "specific": "", "direct": "",
    "showable": "", "actual": "", "additional": "", "recent": "", "recently": "",
    "meaningful": "good",
    # rules 0.4.9, batch 7
    "mid-level": "good", "entry-level": "basic", "senior-level": "strong", "likely": "", "active": "good", "discrete": "basic", "production-level": "strong",
    "production-grade": "strong", "native-level": "expert", "consolidated": "", "well-founded": "good", "expert-level": "expert", "advanced-level": "strong",
}
_LEVEL_RANK = {"": 0, "basic": 1, "good": 2, "strong": 3, "advanced": 3, "expert": 4}
_HEAD_RE2 = re.compile(
    r"^(?P<pre>(?:[\w'’-]+\s+){0,4}?)(?P<head>track record|know-how|"
    + "|".join(sorted((h for h in _HEAD_OF if " " not in h and h != "know-how"), key=len, reverse=True))
    + r")\b(?P<post>.*)$", re.I)


def _keep_terms(words: list[str]) -> list[str]:
    """`real estate`, `real time`, `high availability`: a level word that opens a
    term of its own is joined to it, so it is not read as a level (rules 0.4.7)."""
    out, i = [], 0
    while i < len(words):
        if i + 1 < len(words) and (words[i].lower(), words[i + 1].lower().strip(",.")) in _TERMS:
            out.append(f"{words[i]}\u00a0{words[i + 1]}")
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


_TERMS = {("real", "estate"), ("real", "time"), ("high", "availability"),
          ("high", "performance"), ("high", "frequency"), ("high", "voltage"), ("full", "stack"),
          ("direct", "sales"), ("direct", "marketing"), ("high", "complexity"), ("high", "volume"),
          ("high", "traffic"), ("high", "load"), ("high", "scale"), ("high", "quality"), ("high", "speed"),
          ("high", "throughput"), ("high", "precision"), ("high", "security"), ("high", "tech"),
          ("operating", "systems"), ("operating", "system"), ("operating", "model"), ("operating", "models"),
          ("discrete", "mathematics"), ("discrete", "event"), ("deep", "learning"), ("deep", "reinforcement"),
          ("deep", "neural"), ("deep", "tech"), ("in-depth", "learning"), ("active", "directory"),
          ("active", "listening"), ("active", "learning")}


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15}


def _num(x: str) -> int:
    """`3`, `3.5` (read as 3, the whole years asked), `three`."""
    x = x.lower().replace(",", ".")
    return _NUMBER_WORDS[x] if x in _NUMBER_WORDS else int(float(x))


def _years(text: str) -> tuple[str, int | None, int | None, str]:
    m = _YEARS_RE.search(text)
    if not m:
        return text, None, None, ""
    if m.group("vague") or m.group("multi"):
        lo = hi = None
        raw = (m.group("vague") or m.group("multi")).lower()
    elif m.group("mo"):
        n = int(m.group("mo"))
        lo, hi = (n // 12 if n >= 12 else None), None
        raw = m.group(0).strip()
    else:
        lo, b = _num(m.group("a")), m.group("b")
        if not b and re.match(r"\s*(?:max\.?|maximum)\b", m.group(0), re.I):
            return (re.sub(r"\s{2,}", " ", (text[: m.start()] + " " + text[m.end():])).strip(" ,.-"), None, lo,
                    m.group(0).strip())
        hi = _num(b) if b else (None if m.group("plus") or m.group("plus2") or "least" in m.group(0).lower()
                                                     or "minimum" in m.group(0).lower() else lo)
        raw = m.group(0).strip()
    rest = re.sub(r"\s{2,}", " ", (text[: m.start()] + " " + text[m.end():])).strip(" ,.-")
    rest = re.sub(r"\bof\s+(?=(?:in|with|as|on|within)\b)", "", rest)      # rules 0.4.8
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
         rf"(?:{_BE}\s+)?(?:(?:very|highly|strongly|much)\s+)?(?:preferred|preferable|desirable|advantageous)|"
         rf"{_BE}\s+(?:(?:very|highly|much)\s+)?(?:beneficial|appreciated|welcome|valued|desired)|"
         rf"(?:{_BE}\s+)?nice[- ]to[- ]have|"
         # Rules 0.4.3, from batch 2: how the translator writes the French
         # `apprécié(e)`, `valorisé`, `vítány` and the German `von Vorteil` —
         # no verb in front (`Green Belt appreciated`, `SAP Advantage`,
         # `programming advantage`, `languages of advantage`). Not after
         # `competitive` or `strategic`, where the advantage is the object.
         r"(?:(?:very|highly|much|also)\s+)?(?:appreciated|valued|welcome|desired|beneficial)|"
         # rules 0.4.4: `Prior Fintech experience is not a requirement, but an asset`
         rf"(?:{_BE}\s+)?not\s+a\s+(?:requirement|must),?\s*but\s+(?:an?\s+)?(?:{_ADJ}\s+)?(?:asset|plus|advantage|bonus)|"
         r"(?<!competitive\s)(?<!strategic\s)(?:of\s+)?advantage|"
         # rules 0.4.4: the translator's Chinese 优先 / 更好 (`... is given priority`, `is better`)
         r"(?:(?:is|are|will\s+be)\s+)?given\s+priority|(?:is|are|would\s+be)\s+(?:even\s+)?better|"
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


# Which words of a core are a named technology (rules 0.4.4, for the user's
# call that a name wins over the activity around it). Strong by their shape: an
# acronym (`AWS`, `CI/CD`), a capital inside (`DevOps`, `iOS`), a digit or a
# sign (`S3`, `C#`, `.NET`, `Node.js`), one capital letter (`C`, `R`). A word
# with a first capital only is a name inside the phrase, or first when a
# technical word follows (`Python backend`) and it is not a generic one
# (`Cloud engineering`). In a phrase written in Title Case only the strong
# ones count. A capitalised word next to a name joins it (`Power BI`).
_GENERIC_FIRST = {
    "cloud", "data", "software", "network", "networking", "security", "system", "systems", "web", "mobile",
    "business", "project", "product", "test", "testing", "quality", "digital", "technical", "enterprise",
    "application", "applications", "solution", "solutions", "process", "people", "team", "change", "risk", "sales",
    "customer", "financial", "finance", "marketing", "front", "back", "full", "full-stack", "platform",
    "infrastructure", "database", "embedded", "hardware", "electrical", "mechanical", "industrial", "machine", "deep",
    "computer", "information", "programming", "scripting", "agile", "service", "services", "backend", "frontend",
    "structured", "analytical", "communication", "leadership", "management", "operations", "research", "design",
    "development", "engineering", "architecture", "automation", "integration", "domain", "industry", "legal",
}
_TECH_TAIL = {
    "backend", "frontend", "back-end", "front-end", "development", "programming", "scripting", "coding", "skills",
    "fundamentals", "ecosystem", "stack", "environment", "environments", "infrastructure", "platform", "platforms",
    "services", "applications", "apps", "code", "codebase", "projects", "libraries", "library", "framework",
    "frameworks", "knowledge", "experience", "expertise", "proficiency", "administration", "engineering",
    "modelling", "modeling", "dashboards", "reporting", "queries", "databases", "database", "pipelines",
    "certification", "certifications", "patterns", "solutions", "tools", "tooling",
}


_NOT_NAMES = {"IT", "HR", "OR", "AND"}
# words in front of a frame noun that say what kind, not what (rules 0.4.4)
# A setting or the people worked with, and nothing else (rules 0.4.9, the review of batch 7)
_SETTING_ONLY_RE = re.compile(
    r"^(?:(?:an?|the|both)\s+)?(?:(?:multinational|international|global|large|corporate|matrix|fast[- ]paced|"
    r"dynamic|regulated|similar|multicultural|diverse)\s+)+(?:compan(?:y|ies)\s+)?(?:environments?|compan(?:y|ies)|"
    r"organi[sz]ations?|settings?|contexts?)$", re.I)
_PEOPLE_ONLY_RE = re.compile(
    r"^(?:both\s+)?(?:(?:in-house|external|internal|cross-functional|distributed|remote|international|global|"
    r"multicultural|diverse|senior|key|enterprise)\s+)*(?:teams?|agencies|customers|clients|stakeholders|partners|"
    r"vendors|suppliers)(?:\s+(?:and|or)\s+(?:(?:in-house|external|internal|international|key|enterprise)\s+)*"
    r"(?:teams?|agencies|customers|clients|stakeholders|partners|vendors|suppliers))?$", re.I)
# Title-Case words that ARE what is asked when they open an atom (rules 0.4.9)
_TECH_FIRST_RE = re.compile(r"(?:Python|Java|Scala|Ruby|Rust|Go|Swift|Kotlin|Perl|Excel|Word|Linux|Windows|Unix|"
                            r"Oracle|Kafka|Spark|Docker|Kubernetes|Terraform|Ansible|Jenkins|Azure|Salesforce|"
                            r"Tableau|Snowflake|Databricks|Workday|Jira|Confluence|Angular|React|Django|Flask|"
                            r"Spring|Hibernate|Pega|Murex|Calypso|Finance|Marketing|Sales|Security|Network(?:ing)?|"
                            r"Database|Cloud|Testing|Automation|Integration|Embedded|Frontend|Backend|Accounting|"
                            r"Procurement|Logistics|Payroll|Tax|Legal|Audit|Risk|Compliance|Design|Data)$")
# vendors whose name in front of a frame says whose products follow (rules 0.4.8)
_VENDORS = {"Microsoft", "SAP", "Oracle", "Google", "Amazon", "AWS", "IBM", "Atlassian", "Adobe", "Salesforce",
            "Siemens", "Cisco", "VMware", "Autodesk", "Apple"}
_WEAK_OBJECT = {"technical", "work", "working", "business", "professional", "practical", "industry", "field",
                "functional", "operational", "hands-on", "coding", "programming", "scripting", "user", "computer",
                "application",
                # rules 0.4.7, batch 5
                "implementation", "production", "academic", "commercial", "industrial", "project",
                "projects", "development"}
# names that are categories: the word in front of them is part of what is asked
# (`conversational AI`, `edge AI deployments` are not the AI skill)
_CATEGORY_NAMES = {"AI", "ML", "AI/ML", "BI", "UX", "UI", "API", "APIs", "IoT", "NLP", "LLM", "LLMs", "OT", "QA"}
# names with a small word inside, whole as written
_NAME_WITH_SMALL_WORD_RE = re.compile(r"Ruby on Rails|Infrastructure as Code|Software as a Service|"
                                      # rules 0.4.8: `Machine Learning` was read as `Learning`
                                      # (`Machine` opens generic phrases), written with capitals only
                                      r"(?-i:(?:Deep Reinforcement|Deep|Machine|Reinforcement) Learning)", re.I)


def _strong_name(tok: str) -> bool:
    t = tok.strip(",.;:()[]")
    if not any(c.isalpha() for c in t) or t in _NOT_NAMES:
        return False
    if any(c.isdigit() for c in t) or re.search(r"[+#]|\.\w", t):
        return True
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 2 and all(c.isupper() for c in letters):
        return True
    if any(c.isupper() for c in t[1:]) and any(c.islower() for c in t):
        return True
    return len(t) == 1 and t.isupper() and t not in ("A", "I")


def _name_runs(text: str) -> list[str]:
    """The named technologies in ``text``, each as written: `Azure`, `Power BI`, `ISO 14229`."""
    whole = _NAME_WITH_SMALL_WORD_RE.search(text)
    if whole:
        # `Ruby on Rails` reads as Title Case, and is a name
        after = re.sub(r"^\W*(?:(?:with|in|on|using|and|or|for|via)\s+)*", "", text[whole.end():])
        return [whole.group()] + _name_runs(text[: whole.start()]) + _name_runs(after)
    toks = text.split()
    words = [t.strip(",.;:()[]") for t in toks]
    rest = [w for w in words[1:] if w[:1].isalpha()]
    title = len(rest) >= 2 and sum(w[:1].isupper() for w in rest) * 2 >= len(rest)
    name = []
    for i, w in enumerate(words):
        cap = w[:1].isupper() and w.lower() not in LEVEL_WORDS and w not in _NOT_NAMES
        if _strong_name(w):
            name.append(True)
        elif cap and not title and i > 0:
            name.append(True)
        elif cap and not title and i == 0 and w.lower() not in _GENERIC_FIRST and (
                len(words) == 1 or words[1].lower() in _TECH_TAIL
                # a language before a comma (`English, both written and verbal`);
                # not any word: `Communicative, team-capable` is a trait list
                or (toks[0][-1:] in ",;:" and re.fullmatch(atom._LANGS, w, re.I))):
            name.append(True)
        else:
            name.append(False)
    # a capitalised word or a number next to a name joins it: `Power BI`, `ISO 14229`
    for _ in range(2):
        for i, w in enumerate(words):
            if name[i] or not w:
                continue
            # never across a comma: `CAN Protocol, Diagnosis` is one name and a word
            near = (i > 0 and name[i - 1] and toks[i - 1][-1:] not in ",;:") or \
                   (i + 1 < len(words) and name[i + 1] and toks[i][-1:] not in ",;:")
            if near and (w.isdigit() or (w[:1].isupper() and w.lower() not in _GENERIC_FIRST)):
                name[i] = True
    runs, cur = [], []
    for i, w in enumerate(words):
        if name[i]:
            cur.append(w)
            # a comma or a bracket ends a name
            if toks[i].rstrip()[-1:] in ",;:)" or toks[i][:1] == "(":
                runs.append(" ".join(cur))
                cur = []
        elif cur:
            runs.append(" ".join(cur))
            cur = []
    if cur:
        runs.append(" ".join(cur))
    return [r for r in runs if r]


_NAME_FOLLOWERS = _TECH_TAIL | {"software", "systems", "system", "workflows", "workflow", "architectures", "architecture",
                                 "apis", "api", "tests", "testing", "tech", "technologies", "technology", "suite",
                                 "integration", "integrations", "deployment", "deployments",
                                 "interfaces", "interface", "modules", "module",
                                 "datastores", "databases", "web", "services",
                                 "models", "concepts", "methodology", "methodologies", "language", "languages"}
_NAME_PREPS = {"as", "in", "for", "with", "on", "of", "to", "at", "from", "using", "and", "or", "within", "across"}


def _initials_of(acronym: str, words: str) -> bool:
    """`MDM` for `Master Data Management`, `HPC` for `high-performance computing`:
    the bracket only abbreviates, and the words written out are kept."""
    initials = "".join(w[0] for w in re.split(r"[\s-]+", words) if w[:1].isalpha()).upper()
    a = acronym.replace(".", "").upper()
    return len(a) >= 2 and a.isalpha() and initials.endswith(a)


def _name_is_modifier(run: str, core: str) -> bool:
    """A name at the start that a common noun completes: `IR drop analysis`,
    `AD product system development` are terms of their own, not IR or AD
    (the review of batch 2). `Python backend`, `GIS systems`, `AI as part of
    the workflow` keep the name: what follows is a known tail or a preposition."""
    if not core.startswith(run):
        return False
    rest = core[len(run):].split()
    if not rest or not rest[0][:1].islower():
        return False
    word = rest[0].lower().strip(",.;:")
    # a category name keeps any noun after it: `AI coding tools`, `API development`
    # (review of batch 3); only a preposition sets it free (`AI/ML in production`)
    if run in _CATEGORY_NAMES:
        return word not in _NAME_PREPS
    return word not in _NAME_FOLLOWERS | _NAME_PREPS


def _named(text: str) -> bool:
    """A capital or a digit anywhere, the first letter included: `Python` alone is a name here,
    where `names` reads a first capital as the start of a sentence."""
    return any(ch.isupper() or ch.isdigit() for ch in text)


def first_per_key(keys: list[str]) -> list[bool]:
    """True for the first atom of each value in one item (its normalised words); an empty one always stays."""
    seen: set[str] = set()
    out = []
    for k in keys:
        out.append(not k or k not in seen)
        if k:
            seen.add(k)
    return out


# Rules 0.4.5, from the user's review of batch 3 (2026-11-18): what is asked
# is the thing, not the frame around it. Each rule moves what it takes off to
# `extra`, so nothing is lost for the level and context analyses.
_INTEREST_RE = re.compile(r"^(?:(?:demonstrated|strong|genuine|keen|real)\s+)?interest\s+(?:in|for)\s+(?:the\s+)?(?=\S)",
                          re.I)
_THROUGH_RE = re.compile(r"^(?P<x>.+?)\s+(?P<y>through\s+.+)$", re.I)
_FOCUS_RE = re.compile(r"^(?P<y>.+?)\s+with\s+(?:an?\s+)?(?:(?:strong|clear|particular)\s+)?focus\s+on\s+(?P<x>.+)$",
                       re.I)
_PROG_FRAME_RE = re.compile(r"^(?P<y>programming|coding|scripting|development)\s+(?:with|in|using)\s+(?P<x>.+)$", re.I)
_GERUND_FRAME_RE = re.compile(r"^(?P<y>(?:(?:confidence|comfort)\s+)?(?:using|leveraging|applying|utili[sz]ing))\s+"
                              r"(?P<x>.+?)(?:\s+(?P<z>as\s+.+))?$", re.I)
_SHOW_RE = re.compile(r"^(?:exhibit|demonstrate|show|possess)\s+(?=\S)", re.I)
_EVALUATIVE_ADJ_RE = re.compile(
    r"^(?:scalable|highly\s+available|available|robust|modern|popular|reliable|secure|large-scale|cutting-edge|"
    r"state-of-the-art|latest|current|common|well-known|clear|accurate|actionable|prioriti[sz]ed|other|"
    r"(?-i:responsible)(?=\s+AI\s+[a-z])|impactful)\s*,?\s+"
    r"(?:and\s+)?(?=\S)", re.I)
_BASED_RE = re.compile(r"^(?P<x>[A-Z][\w.+#]*)-based\s+(?P<y>.+)$")
_CONCEPTS_RE = re.compile(r"^(?:the\s+)?(?:basic\s+|core\s+)?concepts?\s+of\s+(?=\S)", re.I)
_WRITE_RE = re.compile(r"^write\s+(?!and\b)(?P<y>.+)$", re.I)


def _review_045(core: str) -> tuple[str, str]:
    """The core with its frame taken off, and what was taken off (for `extra`)."""
    moved: list[str] = []
    c = re.sub(r"^including\s+(?=\S)", "", core, flags=re.I)
    c = re.sub(r"^(?:the\s+)?use\s+of\s+(?=\S)", "", c, flags=re.I)        # rules 0.4.9, batch 7
    # `Skilled in using project management tools`, `utilizing Power BI`
    c = re.sub(r"^(?:using|utili[sz]ing|applying|leveraging|employing)\s+(?!(?:and|or|to|in|of|with)\b)"
               r"(?!.*\bas\s+an?\s)(?!.*\bto\s)(?=\S)",
               "", c, flags=re.I)
    c = re.sub(r"^(?:an?\s+)?(?:(?:high|strong|great|good)\s+)?degree\s+of\s+(?=\S)", "", c, flags=re.I)
    c = re.sub(r"^(?:an?\s+)?(?:high|strong|great|good|very\s+good|excellent)\s+level\s+of\s+(?=\S)", "", c, flags=re.I)
    # An attitude in front of its object stays (the user, 2026-11-23, review of
    # batch 5): `Passion for development`, `Desire to learn` say something the
    # object alone does not.
    # `High degree of resilience` is resilience; `Proven record of shipping` is shipping
    c = re.sub(r"^(?:(?:proven|demonstrated|strong|solid)\s+)?(?:track\s+)?record\s+(?:of|in)\s+(?=\S)", "", c,
               flags=re.I)
    # `with a focus on application security`: what it is about, for `extra` (review of batch 5)
    m = re.match(r"^(?P<x>.+?)\s+with\s+(?:an?\s+)?(?:(?:strong|particular|special|clear)\s+)?focus\s+on\s+"
                 r"(?P<y>.+)$", c, re.I)
    # a name in focus is left to the rule that a name wins (`Cloud Architecture with
    # a strong focus on Microsoft Azure` is Azure, review of batch 3)
    if m and not _name_runs(m.group("y")):
        c, moved = m.group("x"), moved + [f"focus on {m.group('y')}"]
    # rules 0.4.8, the user's review of batch 6:
    # `Clear written and verbal communication skills`: communication, the modes set aside
    m = re.match(r"^(?:(?:clear|excellent|strong|good|effective)\s+)?(?P<m>(?:written|verbal|oral|spoken)"
                 r"(?:\s*(?:and|&|,|/)\s*(?:written|verbal|oral|spoken))*)\s+(?=communication\b)", c, re.I)
    if m:
        c, moved = c[m.end():], moved + [m.group("m")]
        # rules 0.4.9, batch 7: `communication skills` was a key of its own (32 times)
        c = re.sub(r"^communication\s+skills?$", "communication", c, flags=re.I)
    m = re.match(r"^(?P<x>.+?)\s+(?P<y>across\s+(?:the\s+)?(?:teams?|domains?|functions?|departments?|"
                 r"disciplines?|regions?|cultures?|time\s*zones?|business\s+units?|organi[sz]ations?)"
                 r"(?:\s*(?:,|and|or)\s*(?:teams?|domains?|functions?|departments?|disciplines?|regions?|cultures?|"
                 r"time\s*zones?|business\s+units?|organi[sz]ations?))*)$", c, re.I)
    if m and not re.fullmatch(r"work|working|collaborate|collaborating|operate|operating", m.group("x"), re.I):
        c, moved = m.group("x"), moved + [m.group("y")]
    m = re.match(r"^(?P<y>(?:in\s+)?(?:an?\s+)?(?:similar\s+|comparable\s+)?(?:role|position)s?\s+(?:within|in)\s+)"
                 r"(?P<x>(?-i:[A-Z]).+)$", c, re.I)
    # a field named in Title Case (`Identity & Access Management`), not a category (`IT / Data`, review of batch 4)
    if m and re.fullmatch(r"[A-Z][a-z][\w.-]*(?:\s+(?:&\s+|and\s+)?[A-Z][a-z][\w.-]*)+", m.group("x")):
        c, moved = m.group("x"), moved + [m.group("y").strip()]
    m = re.match(r"^(?P<x>.+?)\s+(?P<y>in\s+(?:close\s+)?collaboration\s+with\s+.+)$", c, re.I)
    if m and not _name_runs(m.group("y")):
        c, moved = m.group("x"), moved + [m.group("y")]
    m = re.match(r"^(?P<v>\w+ing\s+)(?P<s>large[- ]scope)\s+(?P<x>\S.*)$", c, re.I)
    if m:
        c, moved = m.group("v") + m.group("x"), moved + [m.group("s")]
    # `Technical and transverse leadership`: leadership, what kind set aside
    m = re.match(r"^(?P<m>[\w-]+\s+and\s+[\w-]+)\s+(?P<x>leadership)$", c, re.I)
    if m:
        c, moved = m.group("x"), moved + [m.group("m")]
    # `(consumer) electronics`
    c = re.sub(r"^\((\w+)\)\s+", r"\1 ", c)
    # `how data architecture influences data quality`: what is to be understood
    m = re.match(r"^how\s+(?P<x>.+?)\s+(?:influences?|affects?|impacts?|drives?|shapes?|interacts?\s+with)\s+(?P<y>.+)$",
                 c, re.I)
    if m:
        c, moved = m.group("x"), moved + [m.group("y")]
    # `Business Intelligence projects using BI tools`: what is used, when it names something
    m = re.match(r"^(?P<x>.+?)\s+using\s+(?P<y>.+)$", c, re.I)
    if m and _name_runs(m.group("y")) and not _name_runs(m.group("x").split()[-1]) \
            and re.search(r"\b(?:projects?|work|tasks?|activities)$", m.group("x"), re.I):
        c, moved = m.group("y"), moved + [m.group("x")]
    # an attitude in front goes when what follows stands alone and is not one generic
    # word (the user, 2026-11-23): `keen eye for spotting patterns` is spotting patterns,
    # `Passion for development` stays
    m = re.match(r"^(?:an?\s+)?(?:(?:keen|good|great|sharp|real|genuine|deep|strong)\s+)?"
                 r"(?:eye|passion|appetite|enthusiasm|love|appreciation|flair)\s+(?:for|towards?|of)\s+(?=\S)|"
                 r"^passionate\s+about\s+(?=\S)", c, re.I)
    if m and (len(c[m.end():].split()) >= 2 or _name_runs(c[m.end():])
              or soft_group(c[m.end():]) != c[m.end():]) \
            and not re.match(r"details?\b", c[m.end():], re.I):
        c, moved = c[m.end():], moved + [m.group().strip()]
    # [2] `data structuring for real-time business evaluation`: what it is for, aside
    m = re.match(r"^(?P<x>(?:[\w-]+\s+){0,2}[\w-]+(?:ing|ion|ment|sis))\s+(?P<y>for\s+.+)$", c, re.I)
    # not an attitude (`passion for sustainability` keeps its object)
    if m and not _name_runs(m.group("x")) and not _name_runs(m.group("y")) and not re.search(
            r"\b(?:passion|affection|ambition|motivation|dedication|commitment|attention|devotion|"
            r"inclination|predisposition|disposition|fascination|admiration|appreciation|training|education|"
            r"apprenticeship|qualification|preparation|certification)$", m.group("x"), re.I) \
            and not re.fullmatch(r"[\w-]+ing", m.group("x")):
        c, moved = m.group("x"), moved + [m.group("y")]
    # [30] `being the primary interface with technical or public-sector customers`
    m = re.match(r"^(?:being|act(?:ing)?\s+as|serv(?:e|ing)\s+as)\s+(?:the\s+|a\s+)?(?:(?:primary|main|first|single|key)\s+)?"
                 r"(?:interface|point\s+of\s+contact|contact\s+person)\s+(?:with|for)\s+(?P<y>.*?)\s*(?:customers|clients)$",
                 c, re.I)
    if m:
        c, moved = "interface with clients", moved + ([m.group("y").strip(" ,")] if m.group("y").strip(" ,") else [])
    # [95] `Certification for TOGAF`: the name is what is asked
    m = re.match(r"^(?:certifications?|certificates?|certified)\s+(?:for|in|of|on)\s+(?P<y>.+)$", c, re.I)
    if m and _name_runs(m.group("y")):
        c, moved = m.group("y"), moved + ["certification"]
    c = re.sub(r"^(?:across|within|with)\s+(?=\S)", "", c, flags=re.I)
    # `predictive modeling to support demand planning`: what it is for, aside (9 rows)
    m = re.match(r"^(?P<x>.+?)\s+(?P<y>to\s+(?:support|enable|drive|improve|inform|deliver|help|power)\s+.+)$", c, re.I)
    if m and len(m.group("x").split()) <= 4 and not _name_runs(m.group("y")):
        c, moved = m.group("x"), moved + [m.group("y")]
    # `Very good to good grades`
    c = re.sub(r"^(?:(?:very\s+)?good\s+)?to\s+(?=good\b)", "", c, flags=re.I)
    # `supporting production systems with high availability`: how, for `extra`
    m = re.match(r"^(?P<x>.+?)\s+(?P<y>(?:with|for)\s+(?:high|low|large|massive)\s+(?:availability|performance|"
                 r"scalability|load|traffic|volumes?|scale)|(?:on|across)\s+(?:multiple|various|different|several)\s+"
                 r"(?:platforms|systems|projects|environments|devices))$", c, re.I)
    if m:
        c, moved = m.group("x"), moved + [m.group("y")]
    # `Motivated by the quality of work`: the disposition, and what moves it
    m = re.match(r"^(?P<x>motivated|driven|inspired|energi[sz]ed)\s+by\s+(?P<y>.+)$", c, re.I)
    if m:
        c, moved = m.group("x"), moved + [f"by {m.group('y')}"]
    # `to negotiate as required`
    c = re.sub(r"\s+as\s+(?:required|needed|necessary)$", "", c, flags=re.I)
    # `Willingness to travel to the United States for business purposes`: the
    # availability is the requirement, where to is part of it (review of batch 5)
    c = re.sub(r"^((?:willing(?:ness)?|ready|readiness|able|availability)\s+to\s+(?:travel|relocate)\b.*?)\s+for\s+"
               r"(?:business|work)\s+(?:purposes|reasons|needs)$", r"\1", c, flags=re.I)
    # `Good foundations in Python` is Python (review of batch 2); `ITIL Foundations`
    # is a certificate, so only `foundations in/of`
    m = re.match(r"^foundations?\s+(?:in|of)\s+(?=\S)", c, re.I)
    if m:
        c, moved = c[m.end():], moved + ["foundations"]
    m = _INTEREST_RE.match(c)
    if m:
        c, moved = c[m.end():], moved + ["interest"]
        th = _THROUGH_RE.match(c)
        if th:
            c, moved = th.group("x"), moved + [th.group("y")]
        c = re.sub(r"\s+field$", "", c, flags=re.I)
    m = _FOCUS_RE.match(c)
    if m and _name_runs(m.group("x")):
        c, moved = m.group("x"), moved + [m.group("y")]
    m = _PROG_FRAME_RE.match(c)
    if m and _name_runs(m.group("x")):
        c, moved = m.group("x"), moved + [m.group("y")]
    m = _GERUND_FRAME_RE.match(c)
    if m and _name_runs(m.group("x")):
        c, moved = m.group("x"), moved + [m.group("y")] + ([m.group("z")] if m.group("z") else [])
    c = _SHOW_RE.sub("", c)
    while True:
        m = _EVALUATIVE_ADJ_RE.match(c)
        if not m or not c[m.end():].strip():
            break
        moved.append(m.group().strip(" ,"))
        c = c[m.end():]
    m = _BASED_RE.match(c)
    if m:
        c, moved = m.group("x"), moved + [f"{m.group('x')}-based {m.group('y')}"]
    c = _CONCEPTS_RE.sub("", c)
    m = _WRITE_RE.match(c)
    if m:
        c, moved = "writing", moved + [m.group("y")]
    # Rules 0.4.6, the user's review of batch 4: where and what for are context
    m = _CONTEXT_046_RE.match(c)
    if m and not _name_runs(m.group("x")) and len(_name_runs(m.group("y"))) == 1 \
            and m.group("y").lower().startswith("within") \
            and _name_runs(m.group("y"))[0] not in _CATEGORY_NAMES \
            and re.fullmatch(rf"within\s+(?:the\s+)?{re.escape(_name_runs(m.group('y'))[0])}", m.group("y").strip(), re.I):
        # the name wins (rules 0.4.7, batch 5): `dashboards within eFront Invest` is eFront Invest
        c, moved = _name_runs(m.group("y"))[0], moved + [m.group("x")]
    elif m and (len(m.group("x").split()) >= 2 or _name_runs(m.group("x")) == [m.group("x").strip()]):
        # `role within IT / Data` keeps it: `role` alone would name nothing
        c, moved = m.group("x"), moved + [m.group("y")]
    m = _GENERIC_046_RE.match(c)
    if m and re.match(r"(?:server\s+environments?|landscapes?|ecosystems?)$", m.group("y"), re.I) \
            and not _name_runs(m.group("x")):
        m = None
    # `a scientific domain`: an adjective alone names no field (the user's review of batch 7)
    if m and m.group("y").lower() == "domain" and re.fullmatch(r"(?:an?\s+|the\s+)?[a-z]+(?:ic|al)", m.group("x"),
                                                                re.I):
        m = None
        c = re.sub(r"^(?:an?|the)\s+", "", c, flags=re.I)
    if m:
        c, moved = m.group("x"), moved + [m.group("y")]
    m = _NAME_FOR_RE.match(c)
    if m:
        c, moved = m.group("x"), moved + [m.group("y")]
    c = re.sub(r"^(?:an?\s+)?spirit\s+of\s+(?=\S)", "", c, flags=re.I)
    m = re.match(r"^(?:wide|broad)\s+(?:range|spectrum)\s+of\s+(?:knowledge|experience)\s+(?:in|of)\s+"
                 r"(?:the\s+(?:field|area)\s+of\s+)?(?=\S)", c, re.I)
    if m:
        c, moved = c[m.end():], moved + ["broad knowledge"]
    m = re.match(r"^(?P<g>\w+ing)\s+(?:and|or|&)\s+\w+ing\s+(?:on|with|in|over|to|across)\s+(?P<o>.+)$", c, re.I)
    if m:
        obj = re.sub(r"^(?:impactful|successful|high-quality)\s+", "", m.group("o"), flags=re.I)
        c = f"{m.group('g')} {obj}"
    m = _GERUND_PAIR_RE.match(c)
    if m:
        c, moved = c[m.end():], moved + [m.group().strip()]
    return c.strip(" ,.;:"), " ".join(moved)


_CONTEXT_046_RE = re.compile(
    r"^(?P<x>.+?)\s+(?P<y>in\s+(?:(?:an?|the)\s+)?[\w\s/-]{0,40}?environments?|within\s+[\w\s,/-]+|"
    r"to\s+interact\s+with\s+.+|with\s+large\s+projects?)\s*$", re.I)
# a word after the thing that adds nothing: `SQL Domain`, `Data Analytics Methodologies`,
# `Python software development`, `testing domain`
_GENERIC_046_RE = re.compile(r"^(?P<x>.+?)\s+(?P<y>domain|methodolog(?:y|ies)|software\s+development|"
                             r"server\s+environments?|landscapes?|ecosystems?)$", re.I)
# `SonarQube for CI/CD and code quality`: the name, and what it is for
_NAME_FOR_RE = re.compile(r"^(?!(?:Eye|Bias|Appetite|Desire|Passion|Love|Flair|Talent|Feel|Nose|Knack|Hunger|Drive|"
                          r"Certifications?|Certificates?|Certified|Enthusiasm|Interest|Curiosity|Affinity|"
                          r"Appreciation|Motivation|Commitment|"
                          r"Taste)\b)(?P<x>[A-Z][\w./+#-]*(?:\s+[A-Z][\w./+#-]*)?)\s+(?P<y>for\s+.+)$")
# `training and evaluating machine learning models`: the activities say how (2026-10-29)
_GERUND_PAIR_RE = re.compile(r"^\w+ing\s+(?:and|or|&)\s+\w+ing\s+(?=\S)", re.I)


def _whole_language(text: str) -> bool:
    """One language, every other word saying how much or how."""
    words = re.findall(r"[ABCabc][12](?!\d)|[^\W\d_]+", re.sub(r"\s+to\s+(?:understand|discuss|communicate|work|read|"
                                                           r"write)\b.*$", "", text, flags=re.I))
    langs = {w.title() for w in words if _LANG_ONLY_RE.match(w)}
    return len(langs) == 1 and all(_LANG_ONLY_RE.match(w) or w.lower() in _LANG_FILLER | _LANG_HOW
                                   or re.fullmatch(r"[ABCabc][12]", w) for w in words)


_LANG_HOW = {"understanding", "sufficient", "adequate", "either", "fluency", "excellent", "minimum"}


_OWN_FRAME_RE = re.compile(
    r"^(?:an?\s+)?(?:(?:strong|solid|good|excellent|deep|proven|hands-on|working|practical|basic|advanced|"
    r"extensive|in-depth|sound|thorough|demonstrated|demonstrable|some|prior|previous|relevant|professional|"
    r"technical|very|great|broad)\s+)*"
    r"(?:experience|knowledge|understanding|proficiency|familiarity|expertise|exposure|background|command)\s+"
    r"(?:of|in|with|on|using|across)\s", re.I)


def inherit_years(item: str, parts: list[dict], atoms: list[str] | None = None) -> list[dict]:
    """The item's years on every part they apply to (rules 0.4.6).

    `5+ years of Enterprise software QA and test automation experience` is
    split in two, and only the first part read the years: the second lost
    them (36 of 989 parts with years in batch 4). When the item says ONE
    number of years and some parts carry it, the parts without years take
    it, except degrees and languages, which years do not qualify (`Any degree
    and 8+ years' relevant experience`). Two different numbers in an item
    (`4-6 years ..., with a minimum of 3 years in X`) are left as read.
    """
    found = {p["years_raw"] for p in parts if p.get("years_raw")}
    if len(found) != 1 or len(_YEARS_RE.findall(item)) != 1:
        return parts
    src = next(p for p in parts if p.get("years_raw"))
    for i, p in enumerate(parts):
        # a clause with its own frame in front has its own years, none here
        # (`3+ years of experience in Python, ... and experience with AWS`, rules 0.4.7)
        if atoms and i < len(atoms) and _OWN_FRAME_RE.match(atoms[i]):
            continue
        if not p.get("years_raw") and p.get("space") not in ("language", "education") and p.get("core"):
            p.update(years_min=src["years_min"], years_max=src["years_max"], years_raw=src["years_raw"])
    return parts


def keep_once(norms: list[str]) -> list[bool]:
    """Which atoms of ONE item stay (rules 0.4.4, from the user's review of batch 2).

    The same words twice go (`Systems thinking` three times). The same key
    twice goes too when what was set aside names nothing: `communication
    skills with clients, specialist teams and stakeholders` is one ask, its
    contexts implied (the call of 2026-11-17). A name in `extra` stays — the
    key lost it (`SW` for `SW development experience with INCA`), and the
    inspector shows that as `duplicate_key`; dropping it would hide the error.
    """
    parts = [decompose(n) for n in norms]
    same_words = first_per_key([n.lower() for n in norms])
    seen: set[str] = set()
    out = []
    for p, w in zip(parts, same_words):
        k = p["key"]
        out.append(w and not (k and k in seen and not _name_runs(p["extra"])))
        if k:
            seen.add(k)
    return out


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
    text = re.sub(r"\b([a-z]+)\s*\((\d{1,2}\+?)\)(?=\s+years?\b)", r"\2", text, flags=re.I)
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
    if not edu and years_raw:
        fr = re.match(r"^(?:(?:of|relevant|related|professional|work)\s+)*experience\s+(?:with|and)\s+(?:a\s+)?"
                      r"(?:minimum\s+of\s+(?:a\s+)?)?(?P<d>.+)$", rest, re.I)
        if fr and _DEGREE_START_RE.match(fr.group("d")):
            edu = _education(fr.group("d"))
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
    if _whole_language(rest) and re.search(r"\b(?:[ABC][12]|understanding|sufficient|adequate|minimum)\b", rest,
                                           re.I):
        # `Minimum English level C1`, `excellent English understanding`,
        # `sufficient mastery of Dutch to understand ...` (review of batch 4):
        # a language with words that say how much; the frame parse took `C1`,
        # `sufficient` or `English understanding` for the object
        out["core"], m = re.sub(r"\s+to\s+(?:understand|discuss|communicate|work|read|write)\b.*$", "", rest,
                                flags=re.I), None
    if m and m.group("head").lower() == "awareness" and re.match(
            r"\s*(?:campaigns?|programs?|programmes?|sessions?|trainings|initiatives?|"
                      r"workshops?|materials?)\b", m.group("post"), re.I):
        m = None
    if m and m.group("head").lower() in _LEAD_ONLY and (
            any(w.lower() not in LEVEL_WORDS for w in m.group("pre").split())
            or not re.match(r"\s+(?:of|in)\s", m.group("post"))):
        m = None
    if m:
        pre = m.group("pre").split()
        head = m.group("head").lower()
        post = m.group("post").strip()
        pre = _keep_terms(pre)
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
        # names read by `_name_runs` since rules 0.4.4: `Cloud engineering
        # experience on Azure` kept `Cloud engineering`, its capital C taken
        # for a name
        # `SW development experience using INCA`: what is used is asked, even
        # beside a name in front (batch 3: `SW` three times for three tools)
        weak = all(w.lower() in _WEAK_OBJECT for w in object_words)
        if object_words and post_obj and (post_obj != post.strip() or re.match(r"\w+ing\s+\w", post)) and weak:
            # `Deep technical mastery of high-density cooling`, `work experience
            # in robotics`: `technical` and `work` say what kind, the object
            # after the preposition is what is asked (rules 0.4.4, batch 3)
            core, extra = post_obj, " ".join(object_words)
        elif object_words and post_obj and post_obj == post.strip() and _name_runs(post) == [post.strip()] \
                and not _name_runs(" ".join(object_words)):
            # `Development skills Perl`: the head distributed over a list of names
            core, extra = post_obj, " ".join(object_words)
        elif object_words and post_obj != post.strip() and _name_runs(post_obj) \
                and not (len(object_words) == 1 and object_words[0] in _VENDORS
                         and re.search(r"\b(?:environments?|industr(?:y|ies)|sectors?|teams?|clients?|projects?|"
                                       r"markets?)\s*$", post_obj, re.I)) \
                and (not _name_runs(" ".join(object_words))
                     or (len(object_words) == 1 and pre and pre[0] == object_words[0]
                         and re.match(r"(?:of|in|with|on)\s", post, re.I)
                         and re.fullmatch(r"[A-Z][a-z]+(?:-[a-z]+)*", object_words[0])
                         and object_words[0] not in _VENDORS and not _TECH_FIRST_RE.match(object_words[0]))
                     or (len(object_words) == 1 and object_words[0] in _VENDORS
                         and not re.search(r"\b(?:environments?|industr(?:y|ies)|sectors?|teams?|clients?|"
                                           r"projects?|markets?)\s*$", post_obj, re.I))
                     or (re.match(r"(?:using|with)\s", post, re.I)
                         and object_words[-1].lower() in ("development", "engineering", "integration", "testing"))):
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
        core = re.sub(r"^(?:of|in|with|on|for|at|as|across|within)\s+(?!least\b)", "", rest, flags=re.I)
        nm = re.match(r"^(?:the\s+)?(?:management|administration|use|usage)\s+of\s+(?P<n>[A-Z].*)$", core)
        if nm and _name_runs(nm.group("n")) == [nm.group("n").strip()]:
            core = nm.group("n").strip()
        w = re.match(r"^(?:(?:within|in|at)\s+)?(?:an?|the)\s+(?P<x>.+?)\s+(?:company|companies|environment|organi[sz]ation|"
                     r"firm|business|setting|scale-?up|start-?up|agency)$", core, re.I)
        if w:
            # rules 0.4.7, batch 5: `within an ad-tech company` is ad-tech
            core = w.group("x")
        elif _SETTING_ONLY_RE.match(core):
            core = f"experience in {core}"
        if re.fullmatch(r"(?:an?\s+|the\s+)?(?:relevant|similar|comparable|related|equivalent)\s+"
                        r"(?:roles?|positions?|capacity|capacities|functions?)", core, re.I):
            core = ""
        out.update(head="(years)", head_group="experience", core=core)
    else:
        # No frame noun: degree words in front are still the level, not the
        # demand (`Excellent written and verbal communication`).
        words = _keep_terms(rest.split())
        k = 0
        while k < len(words) - 1 and words[k].lower() in LEVEL_WORDS:
            k += 1
        if k:
            lv = [LEVEL_WORDS[w.lower()] for w in words[:k]]
            out.update(level=max(lv, key=lambda l: _LEVEL_RANK[l]),
                       level_words=" ".join(w for w in words[:k] if LEVEL_WORDS[w.lower()]),
                       core=" ".join(words[k:]))
    # the terms `_keep_terms` held together are plain words again
    for f in ("core", "extra"):
        if isinstance(out.get(f), str):
            out[f] = out[f].replace("\u00a0", " ")
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
        words = re.findall(r"[ABCabc][12](?!\d)|[^\W\d_]+", out["core"])
        langs = {w.title() for w in words if _LANG_ONLY_RE.match(w)}
        if len(langs) == 1 and all(_LANG_ONLY_RE.match(w) or w.lower() in _LANG_FILLER | _LANG_HOW
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
            ex = re.sub(r"^(?:e\.?\s?g\.?,?|such\s+as|like|incl\.?|including)\s+", "", pm.group("p").strip(),
                        flags=re.I)
            cat_names = [r for r in _name_runs(pm.group("c")) if not _NAME_WITH_SMALL_WORD_RE.fullmatch(r)]
            if _name_runs(ex) == [ex] and not cat_names and not _initials_of(ex, pm.group("c")):
                # A NAMED example after a generic category is the requirement
                # (the user's call, 2026-11-17): `databases (SQL/NoSQL)` is
                # SQL/NoSQL, `tools (Sparx EA)` Sparx EA; the category goes to `extra`.
                out["core"], extra = ex, pm.group("c")
            else:
                out["core"], extra = pm.group("c"), pm.group("p")
            out["extra"] = " ".join(x for x in (out["extra"], extra) if x)
        out["core"] = re.sub(r"^(?:in|of|with|on|for)\s+(?=\S)", "", out["core"], flags=re.I)
        # Rules 0.4.4, from the user's review of batch 2: a preposition left at
        # either edge names nothing (`working on CPaaS`, `development for`), nor
        # do `sense of`, `strength`, `motivation for`
        out["core"] = re.sub(r"^(?:working|work)\s+(?:on|with|in)\s+", "", out["core"], flags=re.I)
        out["core"] = re.sub(r"\s+(?:for|with|in|of|on|at|as|to)$", "", out["core"], flags=re.I)
        out["core"] = re.sub(r"^(?:an?\s+)?sense\s+of\s+(?=\S)", "", out["core"], flags=re.I)
        out["core"] = re.sub(r"^(?:the\s+)?(?:field|area|domain)s?\s+of\s+(?=\S)", "", out["core"], flags=re.I)
        # batch 3, read by the inspector's `edge_preposition`: `Experience from
        # large organisations`, `working directly with customers`, `in at least
        # one public cloud`, `as an IT Support Officer`. Lower case only:
        # `AS 9100` is a standard.
        out["core"] = re.sub(r"^(?:working\s+|work\s+)?(?:directly\s+|closely\s+)?(?:with|from)\s+(?=\S)", "",
                             out["core"])
        out["core"] = re.sub(r"^at\s+least\s+(?:one|1|\d\s*[–-]\s*\d)\s+(?:of\s+(?:the\s+)?)?(?=\S)", "", out["core"])
        out["core"] = re.sub(r"^(?:working\s+|worked\s+)?as\s+(?:an?\s+)?(?=\S)", "", out["core"])
        # One role written several ways is that role (rules 0.4.6, 2026-11-18):
        # `Azure Cloud Architect, Lead Architect or Design Architect` is Cloud Architect
        role = atom.one_role(atom.role_alternatives(out["core"]))
        if role:
            out["core"] = role[0]
            out["extra"] = " ".join(x for x in (out["extra"], role[1]) if x)
        out["core"] = re.sub(r"(?<=\w)\s+strengths?$", "", out["core"], flags=re.I)
        out["core"] = re.sub(r"^(motivation)\s+(?:for|to)\s+.+$", r"\1", out["core"], flags=re.I)
        # `build and manage a sales pipeline`: verbs that share one object are
        # one ask (2026-10-29), and the object is what is asked
        out["core"] = re.sub(r"^[a-z]+\s+(?:and|&|or)\s+[a-z]+\s+(?:an?|the)\s+(?=\S)", "", out["core"])
        if out["core"].lower() in ("soft", "hard", "people"):
            out["core"] += " skills"      # `Soft skills (communication)`: `Soft` names nothing
        out["core"], moved = _review_045(out["core"])
        if moved:
            out["extra"] = " ".join(x for x in (out["extra"], moved) if x)
        held = _name_runs(out["extra"])
        if re.search(r"\b(?:affinity|literacy|savvy)\b", out["core"], re.I) and len(held) == 1:
            # `IT affinity (SQL knowledge)` is SQL (review of batch 4)
            out["extra"] = " ".join(x for x in (out["core"], out["extra"].replace(held[0], "").strip()) if x)
            out["core"] = held[0]
        m = re.match(r"^(?P<x>.+?\s+in\s+.+?)\s+(?P<y>or\s+(?:an?\s+|any\s+)?other\s+.+)$", out["core"], re.I)
        if m and out["head_group"] == "experience":
            out["core"] = m.group("x")
            out["extra"] = " ".join(x for x in (out["extra"], m.group("y")) if x)
        if out["head_group"] == "experience" and re.search(r"\b(?:sector|industry)$", out["core"], re.I) \
                and not re.search(r"\s(?:in|at)\s", out["core"]):
            out["core"] = f"{out['core']} experience"       # review of batch 5: `health sector experience`
        if out["core"].lower() in ("work", "relevant work", "professional work") and out["head_group"] == "experience":
            out["core"] = "work experience"     # `3 years of relevant work experience` (review of batch 3)
        # Degree words after the frame (`Safe handling of especially Excel`,
        # `use of in particular Excel`): the level, not the object.
        out["core"] = re.sub(r"^(?:in particular|expert-level)\s+(?=\S)", "", out["core"], flags=re.I)
        lead = _keep_terms(out["core"].split())
        k = 0
        while k < len(lead) - 1 and lead[k].lower() in LEVEL_WORDS:
            k += 1
        if k:
            if not out["level"]:
                lv = [LEVEL_WORDS[w.lower()] for w in lead[:k]]
                out["level"] = max(lv, key=lambda l: _LEVEL_RANK[l])
            out["core"] = " ".join(lead[k:]).replace("\u00a0", " ")
            # `a minimum of 3 years in test automation`: the `a` went, the `in` is next
            out["core"] = re.sub(r"^(?:in|of|with|on|for)\s+(?=\S)", "", out["core"], flags=re.I)
        # A named technology is the requirement, the activity or role around it
        # its context (the user's call, 2026-11-17): `Cloud engineering on
        # Azure` is Azure, `SAP as a technical consultant` SAP, `Python
        # backend` Python. Only one name in the core, and some words that are
        # not names beside it: two names are a split's business, and `Scrum
        # Master` is one name.
        runs = _name_runs(out["core"])
        # `Infrastructure as Code with Bicep` is Bicep (review of batch 3)
        named = [r for r in runs if not _NAME_WITH_SMALL_WORD_RE.fullmatch(r)]
        if len(runs) > 1 and len(named) == 1:
            runs = named
        bare = out["core"].strip(" ,.;:")
        if re.match(r"(?:passion|desire|love|appreciation|enthusiasm|eye|affinity)\s+(?:for|to|of)\b", bare, re.I):
            runs = []
        elif re.match(r"(?:willing(?:ness)?|ready|readiness|availability|able)\s+to\s+(?:travel|relocate)\b", bare, re.I):
            # `Willingness to travel to the United States` (the user's review of batch 5)
            out["core"] = re.sub(r"\s+for\s+(?:business|work)\s+(?:purposes|reasons|needs)$", "", out["core"],
                                 flags=re.I)
            runs = []
        if len(runs) == 1 and runs[0].replace(".", "") != bare.replace(".", "") \
                and not runs[0][:1].islower() \
                and re.search(r"(?<![\w/&.+#-])[a-z]", bare) \
                and not _NAME_WITH_SMALL_WORD_RE.fullmatch(bare) \
                and not re.search(r"\blicen[cs]e\s+[A-Z]\b", bare) \
                and not _name_is_modifier(runs[0], bare) \
                and not (runs[0] in _CATEGORY_NAMES
                         and re.search(rf"(?<![\w-])[a-z][\w-]*\s+{re.escape(runs[0])}(?!\w)", bare)
                         and not re.search(rf"\bwith\s+(?:[A-Z][\w./+#-]*\s+(?:and|or)\s+)?{re.escape(runs[0])}$",
                                           bare)) \
                and not re.fullmatch(rf"{re.escape(runs[0])}\s+(?:certifications?|certificates?|licen[cs]es?)",
                                     bare, re.I):
            rest = re.sub(rf"\s*{re.escape(runs[0])}\s*", " ", out["core"]).strip(" ,.:;-")
            out["core"] = runs[0]
            out["extra"] = " ".join(x for x in (out["extra"], rest) if x)
        # Product names written several ways (`Golang`, `PowerBI`, `MS Office`):
        # one spelling, from a closed list (`ALIASES`). Then what names nothing.
        out["core"] = soft_group(ALIASES.get(canon(out["core"]), out["core"]))
        if canon(out["core"]) in JUNK or all(w.lower() in LEVEL_WORDS and not (len(w) > 1 and w.isupper())
                                                             for w in out["core"].split()):
            out["core"] = ""
        # `Exceptional academic track record` was `academic` (7 rows, batch 8)
        if out["head"] == "track record" and out["core"].lower() == "academic":
            out["core"] = "academic track record"
        # a key never opens on a preposition (batch 8: `Comfortable working across IT` gave `across IT`)
        out["core"] = re.sub(r"^(?:across|within|with)\s+(?=\S)", "", out["core"], flags=re.I)
        # [55] the people worked with: `experience with in-house teams and external agencies`
        if out["head_group"] == "experience" and _SETTING_ONLY_RE.match(out["core"]) \
                and not _PEOPLE_ONLY_RE.match(out["core"]) and not out["core"].startswith("experience"):
            out["core"] = "experience in " + re.sub(r"^(?:an?|the)\s+", "", out["core"], flags=re.I)
        if out["head_group"] == "experience" and out["head"] != "(years)" and _PEOPLE_ONLY_RE.match(out["core"]) \
                and re.search(r"\bwith\s+(?:both\s+)?" + re.escape(out["core"].split()[0]), text, re.I):
            out["core"] = "experience with " + re.sub(r"^both\s+", "", out["core"], flags=re.I)
        if out["head"] == "comfortable" and re.fullmatch(r"(?:ambiguity|uncertainty|change|changing\s+priorities)",
                                                          out["core"], re.I):
            out["core"] = f"comfortable with {out['core'].lower()}"
        # [54] `Technological know-how`: the word alone names nothing
        if out["head"] == "know-how" and re.fullmatch(r"[A-Za-z]+(?:al|ic|ical)", out["core"]):
            out["core"] = f"{out['core']} know-how"
        # rules 0.4.9, batch 7: a word in front the lists do not hold took the
        # core, then went as a level (`A clear understanding of data structures`,
        # `Successful track record in Cloud`): the object after the preposition is
        # what is asked. Not `in a similar position`, which asks for nothing.
        ob = re.match(r"^(?:of|in|with|on|about|around|regarding|across)\s+(?:the\s+|an?\s+)?(?P<o>\S.*)$",
                      out["extra"] or "", re.I)
        if not out["core"] and ob and not re.match(
                r"(?:similar|related|same|comparable|relevant|equivalent|such|this|that|at\s+least|one|"
                r"multiple|various|several)\b|(?:\w+\s+){0,2}(?:roles?|positions?|capacity|functions?)$",
                ob.group("o"), re.I):
            sub = decompose(ob.group("o"))
            if sub["core"] and not sub.get("degree") and sub["head_group"] in ("", out["head_group"]):
                out["core"], out["extra"] = sub["core"], sub["extra"]
                if not out["level"]:
                    out["level"] = sub["level"]
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
    "i", "hear", "hearing", "listen", "listening",
    # rules 0.4.7, batch 5: `Control of Dutch at European CEFR level C2`, `French
    # language corresponding to a minimum C1 level`, `Intermediate English`
    "european", "cefr", "corresponding", "intermediate", "upper-intermediate", "lower-intermediate", "niveau",
    "nivel",
    # rules 0.4.8, batch 6: `English language familiarity at min. B2`, `German on B2 level`, `at a desired
    # B2 level`, `second national language`, `at communicative level`
    "familiarity", "on", "desired", "national", "second", "communicative", "min.", "conversation"}
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
    # rules 0.4.5, the user's review of batch 3: one word for one soft skill
    "work as a team": "teamwork", "work in a team": "teamwork", "working in a team": "teamwork",
    "team work": "teamwork", "work independently": "autonomy", "work autonomously": "autonomy",
    "work within a team": "teamwork", "work within a team environment": "teamwork",
    "work in a team environment": "teamwork", "working within a team environment": "teamwork",
    "working independently": "autonomy", "work collaboratively": "teamwork",
    "solve problem": "problem solving", "problem solving skill": "problem solving",
    # rules 0.4.6, the review of batch 4
    "easy contact with colleague": "teamwork", "desire to learn": "willingness to learn",
    "desire to grow": "willingness to grow", "analysi": "analysis",
    # rules 0.4.7, the review of batch 5
    "work independently and effectively": "autonomy", "work independently and autonomously": "autonomy",
    "negotiate": "negotiation", "prioritize": "prioritization", "prioritise": "prioritization",
    "multitask": "multitasking", "ability to negotiate": "negotiation",
    "learn": "learning ability", "learning": "learning ability", "ability to learn": "learning ability",
    "capacity to learn": "learning ability", "learning capacity": "learning ability",
    "learning ability": "learning ability", "willingness to learn": "willingness to learn",
    "in-depth learning": "deep learning",
    # rules 0.4.8, the review of batch 6
    "make independent decision": "autonomy", "independent decision-making": "autonomy",
    "independent decision making": "autonomy", "make decisions independently": "autonomy",
    "the ability to make independent decision": "autonomy", "identify analytical thinking": "analytical thinking",
    "problem-solving thinking": "problem-solving", "problem solving thinking": "problem-solving",
}
# One group per soft skill, however it is written (the user, 2026-11-24): working
# independently is autonomy; collaborative, team spirit, team player and working in a
# team are teamwork; an analytical spirit, mindset or way of thinking is analytical
# skills. Matched on the `canon` form (lower case, a hyphen as a space, the last word
# singular). Leading or managing a team is not teamwork, analytics is a field.
_SOFT_GROUPS = [
    (re.compile(
        r"(?:(?:a\s+)?high\s+(?:level\s+of\s+|degree\s+of\s+)?|thrive\s+on\s+a\s+high\s+level\s+of\s+)?autonomy|"
        r"autonomou(?:s|sly)|independen(?:t|ce|tly)|independent\s+(?:work|working|working\s+method|working\s+style)|"
        r"(?:(?:be\s+)?able\s+to\s+|ability\s+to\s+|comfortable\s+|capable\s+of\s+)?"
        r"work(?:ing)?\s+(?:independently|autonomously)(?:\s+and)?|self\s+directed|self\s+reliant|self\s+reliance"),
     "autonomy"),
    (re.compile(
        r"team\s*work|teamwork|team\s*player|teamlayer|collaborative\s+team\s+player|team\s+spirit|"
        r"team\s+collaboration|team\s+orient(?:ed|ation)|team\s+minded|"
        r"(?:effective\s+|good\s+|strong\s+)?(?:collaboration|teamwork|cooperation)(?:\s+skill)?|"
        r"collaborative(?:\s+(?:mindset|spirit|approach|attitude|work|nature|personality))?|cooperative|"
        r"spirit\s+of\s+(?:collaboration|cooperation|teamwork)|sense\s+of\s+teamwork|"
        r"cross\s+functional\s+collaboration|(?:attitude|predisposition|aptitude|willingness|inclination)\s+"
        r"(?:to|for|towards)\s+(?:teamwork|team\s+work|collaboration)|attitudine\s+al\s+lavoro\s+in\s+team|"
        r"taste\s+for\s+collaborative\s+work|joy\s+of\s+(?:interdisciplinary\s+)?cooperation|"
        r"collaborate(?:\s+effectively)?|work(?:ing)?\s+collaboratively(?:\s+in\s+a\s+team(?:\s+environment)?)?|"
        r"(?:(?:be\s+)?able\s+to\s+|ability\s+to\s+)?work(?:ing)?(?:\s+(?:well|effectively))?\s+(?:as|in|within)\s+"
        r"(?:a\s+|part\s+of\s+a\s+)?team(?:\s+(?:environment|setting))?|work\s+as\s+part\s+of\s+a\s+team|"
        r"(?:collaborat(?:e|ing)|work(?:ing)?)(?:\s+(?:effectively|closely|well))?\s+(?:with|across|in)\s+"
        r"(?:(?:cross\s+functional|multidisciplinary|interdisciplinary|remote|global|distributed|international)\s+)?team"),
     "teamwork"),
    (re.compile(
        r"analytical(?:\s+(?:thinking|mindset|mind|spirit|working\s+method|power|reasoning|judgment|judgement|skill|"
        r"capability|capabilitie|ability|abilitie|capacity|capacitie|approach|sense|aptitude|competence|competencie|"
        r"thinker|profile))?|analytic\s+thinking|(?:ability\s+to\s+)?think\s+analytically|analytical\s+and\s+logical"
        r"(?:\s+thinking)?|analytically\s+minded"),
     "analytical skills"),
    (re.compile(
        r"(?:(?:the\s+)?ability\s+to\s+)?adapt(?:ing)?(?:\s+(?:quickly|easily|well))?\s+to\s+(?:an?\s+|the\s+)?"
        r"(?:(?:rapidly|fast|constantly|quickly|continuously)\s+)?(?:chang(?:ing|e)|evolving|new|different)"
        r"(?:\s+(?:environment|priorit(?:y|ie)|requirement|context|situation|circumstance|technolog(?:y|ie)|need))?|"
        r"adaptab(?:ility|le)|adaptiveness|(?:the\s+)?ability\s+to\s+adapt|adapt\s+quickly"),
     "adaptability"),
    (re.compile(
        r"(?:(?:pleasure|joy|fun|enjoyment|passion|love|delight)\s+(?:to|in|of|for|at)\s+)?solv(?:e|ing)\s+problem|"
        r"problem\s+solving(?:\s+skill)?|problem\s+solver"),
     "problem solving"),
]


def soft_group(core: str) -> str:
    """The group's one name for a soft skill written another way, else the core."""
    c = canon(core)
    for rx, name in _SOFT_GROUPS:
        if rx.fullmatch(c):
            return name
    return core


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
