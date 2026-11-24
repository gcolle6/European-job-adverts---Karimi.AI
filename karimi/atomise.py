"""Splitting compound requirements into single, comparable units.

`must_have` arrives pipe-separated, but 40% of those segments still carry more
than one requirement. This module splits them deterministically.

The design favours precision over recall. Anything that does not match a
high-confidence list pattern is left intact and routed to the LLM stage, on the
principle that an unsplit requirement is recoverable later while a wrongly split
one silently corrupts everything downstream.

Revised 2026-09-03 against the labelled sample. Two things had been missed about
the convention the labeller was given, and both cost recall rather than
precision: a list's shared head is repeated on every item (`... under KPIs and
deadlines` is two requirements, not a requirement and a bare noun), and the
phrase introducing a list is usually a requirement in its own right. The
filler a list introducer governs is dropped instead — `relevant qualifications
such as` — so that atoms match the wording a reader would write.

What rules still cannot do, and what stops the gate being met, is *generative*
splitting: the labeller re-heads list items, turning `Experience applying AI to
complex financial domains, including credit` into `Experience with credit`. No
pattern produces a head that is not in the source text. That residue is the
LLM stage's job, and it is measured in `week 1/karimi-week1.md`.
"""

from __future__ import annotations

import re
import unicodedata

from . import config
from . import pos

# --- patterns ----------------------------------------------------------------

# `sowie` / `as well as` / `ainsi que` coordinate two full requirements as surely
# as `and` does, and their absence was silently costing recall on German and
# French segments — segment 48 (`Ausbildung ... und/ oder Berufserfahrung ...`)
# was left whole for want of tolerating the space inside `und/ oder`.
# Dutch `en` is deliberately absent. It is the ordinary Dutch conjunction, but
# it is also the French preposition in `travail en équipe` and `en` recurs
# inside French and Spanish phrases far more often than it coordinates two
# requirements. Splitting on it turned `Aime le travail en équipe` into two
# atoms and cost more precision than the Dutch coordination it recovered.
_CONJ = (
    r"and/or|and\s*/\s*or|und\s*/\s*oder|as well as|ainsi que|"
    r"and|or|et|ou|und|oder|sowie|oppure|nonch[eé]|oraz|lub|och|eller|ed|"
    r"evenals|alsook|as[ií] como|y|e|o"
)

SPLIT_RE = re.compile(rf"\s*,\s*|\s+(?:{_CONJ})\s+", re.I)

# A head ending in one of these governs the list that follows it.
TRIGGER_RE = re.compile(
    # `(?<![-\w])` for the same reason as PREP_RE below: a bare \b matched the
    # `on` inside `Hands-on` and made that the governing head, turning a
    # correctly split segment into `Hands-on UCaaS`.
    r"(?<![-\w])(?:such as|including|includes|include|ideally|preferably|e\.g\.|i\.e\.|"
    r"tra cui|ad esempio|tales como|zoals|tel que|telles que|tels que|"
    r"involving|covering|spanning|regarding|concerning|comprising|"
    r"with|in|of|on|using|con|di|su|met|avec|dans|de|wie|mit|auf|en|sobre)\s+",
    re.I,
)

# Explicit list introducers. Distinguished from the prepositions above because
# the human convention drops them and the generic noun they govern: the labeller
# turned `Possession of relevant qualifications such as CIPM` into
# `Possession of CIPM`, not `Possession of relevant qualifications such as CIPM`.
# The head is therefore cut back to the FIRST preposition and everything from
# there to the introducer is treated as filler.
INTRODUCER_RE = re.compile(
    r"\s*(?:,\s*)?\b(?:such as|including|includes|include|like|namely|"
    r"tra cui|ad esempio|tales como|zoals|tel que|telles que|tels que|wie z\.?b\.?|"
    r"z\.?b\.?|come|par exemple|entre autres)\s+|\s*:\s*",
    re.I,
)
# The repaired form (config.SPLIT_REPAIRS): `e.g.` and `i.e.` outside a bracket
# were not introducers at all, and `z\.?b\.?` admits no space, so `Know-how in
# Netzwerktechnik z. B. TCP/IP, Sockets` shipped `... Netzwerktechnik z. B.
# TCP/IP` as one requirement. Separately compiled so the published path is
# untouched.
INTRODUCER_RE_V2 = re.compile(
    r"\s*(?:,\s*)?\b(?:such as|including|includes|include|like|namely|"
    r"tra cui|ad esempio|tales como|zoals|tel que|telles que|tels que|"
    r"wie z\.?\s?b\.?|z\.\s?b\.|zb\.|e\.\s?g\.|i\.\s?e\.|bspw\.|bijv\.|par ex\.|"
    r"come|par exemple|entre autres|"
    # rules 0.4.8, batch 6
    r"especially(?:\s+(?:in|with))?|particularly(?:\s+(?:in|with))?|in\s+particular|notably|"
    r"for\s+example(?:\s*,)?(?:\s+(?:in|with))?|for\s+instance|beispielsweise(?:\s+in)?)[\s,:]+|\s*:\s*",
    re.I,
)

# The governing preposition the head is cut back to.
#
# The leading `(?<![-\w])` is load-bearing. A hyphen counts as a word boundary,
# so a bare `\b` matched the `on` inside `Hands-on` and trimmed `Hands-on
# experience delivering solutions involving UCaaS` back to `Hands-on UCaaS` —
# a structurally perfect split scored as a miss. Same family as the
# trailing-boundary trap in `classify`: the boundary was in the right place and
# still matched the wrong thing. Also protects `go-to-market`, `end-to-end`,
# `on-site` and `in-depth`.
PREP_RE = re.compile(
    r"(?<![-\w])(?:with|within|without|under|across|through|throughout|in|of|on|for|using|"
    r"about|at|to|into|con|di|su|per|nel|nella|sui|delle|della|dei|met|avec|dans|"
    r"de|des|du|mit|von|im|f[uü]r|auf|an|zur|zum|sobre|para|van|voor|over|bij|"
    r"au|aux|chez|der|die|das|den|dem|des|het|"
    # Participial governors. The head of `... delivering solutions involving X,
    # Y, Z` runs through `involving`, and no preposition in the set reached it,
    # so the distribution fell back to a fragment.
    r"involving|covering|spanning|regarding|concerning|comprising|"
    r"umfassend|betreffend|concernant|riguardante)\s+",
    re.I,
)

LEAD_CONJ_RE = re.compile(rf"^(?:{_CONJ})\s+", re.I)

# Items that name nothing and are dropped rather than kept as requirements. The
# guide is explicit that `or similar` is not a demand signal; the code kept it
# and produced `Strong programming skills in languages such as similar`.
STOP_RE = re.compile(
    r"^(?:and|or|etc\.?|ecc\.?|usw\.?|others?|altri|more|(?:the\s+)?like|"
    r"(?:a|an|the|another|any|other)?\s*(?:closely\s+)?(?:related|similar|equivalent|relevant|comparable)"
    # any one word before the field since rules 0.4.3: `a closely related life-sciences field`
    r"(?:\s+(?:technical|scientific|academic|professional|[\w-]+(?=\s+(?:field|fields|area|areas|discipline|"
    r"disciplines|subject|subjects)\b)))?"
    r"(?:\s+(?:field|fields|area|areas|discipline|disciplines|subject|subjects|"
    r"experience|qualification|qualifications|degree|role|roles|studies|course\s+of\s+study|courses\s+of\s+study|"
    r"professions?|majors?|programmes?|programs?))?|"
    r"similar|similaire|similaires|[eé]quivalent(?:e|es|s)?|simili|"
    r"vergleichbar(?:e|er|en|es)?(?:\s+\w+)?|[aä]hnlich(?:e|er|en|es)?|"
    r"gleichwertig(?:e|er|en|es)?|verwandt(?:e|er|en|es)?(?:\s+\w+)?|"
    r"soortgelijk(?:e)?|vergelijkbaar|weitere|anderen?|otros|autres|"
    r"connexe|connexes|affine|affini)$",
    re.I,
)

# German (and Dutch) compound elision: `Deutsch- und Englischkenntnisse` means
# `Deutschkenntnisse` and `Englischkenntnisse`. Splitting on the conjunction
# leaves a dangling `Deutsch-`, which is a fragment rather than a requirement.
# The elided part is the head noun of the final compound, so a short list of the
# heads that actually recur in this corpus recovers it. Anything not on the list
# is left unsplit rather than emitted as a fragment.
COMPOUND_HEADS = (
    "kenntnisse", "kenntnissen", "konzepte", "konzepten", "erfahrung", "erfahrungen",
    "f[aä]higkeiten", "systeme", "systemen", "prozesse", "prozessen", "management",
    "entwicklung", "analyse", "planung", "steuerung", "beratung", "betreuung",
    "l[oö]sungen", "anwendungen", "technologien", "umgebungen", "architekturen",
    "methoden", "werkzeuge", "sprachen", "vertrieb", "verst[aä]ndnis",
    "vaardigheden", "kennis", "ervaring", "systemen", "talen",
)
COMPOUND_HEAD_RE = re.compile(rf"({'|'.join(COMPOUND_HEADS)})$", re.I)
ELIDED_RE = re.compile(r"^(.+?)\s*[-–]$")

# Nouns that exist only to introduce the list that follows them. The phrase
# before an introducer is normally a requirement in its own right — the
# labeller kept `Strong understanding of large language models` alongside the
# five items it introduces — but not when that phrase ends in a placeholder:
# `programming skills in languages`, `relevant qualifications`, `at least one
# core data domain` name nothing and were dropped.
GENERIC_TAIL_RE = re.compile(
    r"\b(?:languages?|qualifications?|certifications?|degrees?|fields?|domains?|"
    r"tools?|technologies|technology|roles?|areas?|applications?|environments?|"
    r"disciplines?|subjects?|topics?|others?|sprachen|kenntnisse|bereiche?|"
    r"outils|domaines?|langages?|competences?)\s*$",
    re.I,
)

# Category nouns a list of names exemplifies, for the phrase BEFORE an
# introducer only (rules 0.3.0, from the 2026-11-09 trial): `Experience using
# frameworks like Spark, Tensorflow, ...` is the four names, and `Experience
# using frameworks` was a fifth requirement that names nothing. Kept apart from
# GENERIC_TAIL_RE for the reason recorded at PAREN_GENERIC_RE: widening that
# one moves head trimming on every path.
LEAD_CATEGORY_RE = re.compile(
    # Not `databases`, `methodologies`, `services`: `relational databases` and
    # `agile methodologies` are asked for in their own right.
    r"\b(?:frameworks?|libraries|library|standards?|platforms?|solutions?|products?|"
    r"packages?|stacks?|suites?|certifications?|certificates?|technologies)\s*$",
    re.I,
)

# Adjectives coordinated in front of the noun they all modify. `fast, reliable,
# real-time web-based applications` is one requirement described three ways, not
# three requirements, and splitting it emits `reliable` — the defect recorded as
# open in the Week 1 script's section 6.
#
# Distinguished from a genuine list of one-word requirements (`Autonomy and
# responsibility`, `Eloquence, high empathy, ...`) by suffix: the nouns in this
# corpus end in -ity, -ence, -ance, -ment, -tion, -ness and the like, while the
# modifiers end in -able, -ed, -ive, -ous, -ful or are adverbs in -ly. Crude,
# but it is the distinction the failure actually turns on, and it is checked
# against a control below.
ADJECTIVAL_RE = re.compile(
    r"^(?:[\w-]+ly|[\w-]+(?:able|ible|ive|ous|ful|less|ary|ic|al|ed|ing)|"
    r"fast|new|strong|good|great|high|low|deep|broad|solid|clear|clean|"
    r"real[- ]time|hands[- ]on|end[- ]to[- ]end|full[- ]stack|large[- ]scale|"
    r"schnell|neu|stark|gut|hoch|breit|klar|"
    r"rapide|nouveau|fort|bon|clair|"
    r"veloce|nuovo|forte|buono|chiaro)$",
    re.I,
)

# Suffixes that mark a one-word item as a noun, so a genuine short list is not
# suppressed by the rule above.
NOMINAL_RE = re.compile(
    r"(?:ity|ies|ence|ance|ment|tion|sion|ness|ship|ism|hood|ology|"
    r"keit|heit|ung|schaft|tat|"
    r"ite|ance|ence|isme|"
    r"ita|zione|mento)$",
    re.I,
)


def _adjectival(word: str) -> bool:
    if _use_pos():
        return _adjectival_pos(word)
    return bool(ADJECTIVAL_RE.match(word)) and not NOMINAL_RE.search(word)


def _adjectival_pos(word: str) -> bool:
    """The tagger's reading of `_adjectival`: an adjective, or a participle
    used as one (`structured`, `growing`). The suffix rule above takes
    `proposal`, `logic`, `speed` for adjectives and misses `fast-paced` (P2)."""
    # Adverbs count too, as `-ly` did in the suffix rule: `work independently
    # and collaboratively` qualifies one verb.
    p, fine = pos.tag(word)
    return p in ("ADJ", "ADV") or fine in ("VBN", "VBG")


def _nominal_ing(word: str) -> bool:
    """An `-ing` word that is a noun here, not a modifier (see `_is_modifier_run`)."""
    # Stays a word rule with the tagger on: tried 2026-10-30, the tagger reads
    # `solving`, `networking`, `prospecting` in these fragments as verbs and
    # was worse on 12 of the 13 items where the two disagreed.
    w = word.lower()
    if not w.endswith("ing") or w in _ADJECTIVAL_ING:
        return False
    # `fast-evolving`, `client-facing`, `forward-thinking` are adjectives;
    # `problem-solving` and `decision-making` are nouns. The part before the
    # hyphen tells them apart.
    return w.split("-")[0] not in _ADVERBIAL_PREFIXES if "-" in w else True


_ADVERBIAL_PREFIXES = {
    "fast", "forward", "ever", "rapidly", "quickly", "self", "hard", "high", "well",
    "client", "customer", "user", "outward", "future", "long", "far", "slow", "deep",
    "free", "open", "never", "people", "revenue", "market", "public", "growth",
}


_ADJECTIVAL_ING = {
    "leading", "growing", "outstanding", "emerging", "existing", "evolving", "interesting",
    "demanding", "challenging", "compelling", "engaging", "promising", "thriving",
    "rewarding", "working", "willing", "caring", "outgoing", "ongoing", "exciting",
    "hard-working", "hardworking", "forward-thinking", "fast-moving", "fast-growing",
    "self-starting", "far-reaching", "long-standing", "cutting-edge", "upcoming",
    "increasing", "underlying", "corresponding", "remaining", "following", "missing",
}


def _distribute_shared_tail(items: list[str]) -> list[str]:
    """Copy the final chunk's head noun onto the modifiers in front of it.

    The mirror image of head distribution, and the case path B was built for:
    `Eigenverantwortliches, engagiertes und kundenorientiertes Arbeiten` shares
    a *tail*, not a head, so there is nothing in front to repeat — but the noun
    at the end governs every modifier before it.

    Only called where `_is_modifier_run` already holds, i.e. the leading chunks
    are adjectival. A run of nouns (`... access control, and compliance
    requirements within regulated industries`) is a list whose last member
    happens to be long, and appending its tail to the others would be nonsense.
    """
    tail = items[-1].split()[-1]
    out = []
    for i in items[:-1]:
        whole = re.search(r"-(?:solving|making)$", i)       # rules 0.4.7, review of batch 5
        out.append(i if whole or i.lower().endswith(tail.lower()) else clean(f"{i} {tail}"))
    out.append(items[-1])
    return out


def _is_modifier_run(items: list[str]) -> bool:
    """True when the chunks after the first modify one noun rather than listing.

    The first chunk carries the head and its last word is the first of the
    coordinated modifiers, which is why the run cannot be recognised by looking
    at bare chunks alone. Two shapes qualify:

    * the run ends in a noun phrase all the modifiers describe —
      ``... building fast, reliable, real-time web-based applications``;
    * the run is modifiers all the way down, qualifying the first chunk —
      ``Ability to work independently, structured, and goal-oriented``.

    ``Autonomy and responsibility`` matches neither: its chunks are nouns, so
    it stays two requirements. ``Eloquence, high empathy, and ability to
    present ...`` also stays, because ``high empathy`` is a phrase, not a
    modifier.
    """
    if len(items) < 2:
        return False

    first_words = items[0].split()
    if not first_words or not _adjectival(first_words[-1]):
        return False

    mid, last = items[1:-1], items[-1]
    if config.SPLIT_REPAIRS and _nominal_ing(first_words[-1]) \
            and not last.split()[0].lower().endswith("ing") \
            and not any(_adjectival(i) and not _nominal_ing(i) for i in mid):
        # `-ing` in a requirement list is a noun far more often than a
        # modifier: `financial modeling, forecasting, and scenario analysis`,
        # `systems engineering or mission analysis`. Read as modifiers, those
        # lists were taken for one noun phrase and left whole — the main cause
        # of the unsplit `commas + conjunction` class (`New project/
        # unsplit_compounds.py`). When the LAST item also opens with a gerund
        # it is verbs sharing an object (`building and maintaining CI/CD
        # pipelines`), and that keeps its old reading — any `-ing` counts there,
        # `working` and `growing` included (decided 2026-10-29: coordinated
        # verbs sharing an object are ONE requirement). So does a run with a
        # real adjective in the middle: `analytical thinking and structured,
        # solution-oriented approach` left `structured` orphaned.
        return False
    if not all(len(i.split()) == 1 and _adjectival(i) for i in mid):
        return False

    # Either the run lands on the noun being described, or it never leaves the
    # modifiers at all.
    return len(last.split()) > 1 or _adjectival(last)


# "both A and B" / "either A or B" qualify one requirement; they are not lists.
CORREL_TAIL_RE = re.compile(r"\b(?:both|either|neither|sia|sowohl|tanto)\s*$", re.I)
CORREL_LEAD_RE = re.compile(r"^(?:both|either|neither|sia|sowohl|tanto)\s+", re.I)

# Coordinated modifiers of a single requirement — "written and verbal".
# Splitting these produces meaningless fragments such as a bare "verbal".
MODIFIER_RE = re.compile(
    r"^(?:both\s+)?(?:written|verbal|spoken|oral|orally|reading|writing|"
    r"scritto|parlato|orale|[ée]crit|parl[ée]|gesprochen|geschrieben|"
    r"m[uü]ndlich|schriftlich|mondeling|schriftelijk|escrito|hablado)$",
    re.I,
)

PAREN_RE = re.compile(r"\([^()]{0,120}\)")
# `between A, B and C`: from the preposition through its first conjunction and
# the conjunct after it. Commas inside are allowed only between short members.
BETWEEN_RE = re.compile(
    r"\bbetween\s+(?:[^,;]{1,40},\s*){0,4}?(?:[^,;]{1,60}?,?\s|)(?:and/or|and|or|&)\s[^,;]*", re.I)
WITHIN_RE = re.compile(BETWEEN_RE.pattern.replace("between", "within", 1), re.I)
NUM_COMMA_RE = re.compile(r"\d,\d{3}(?!\d)")

# A requirement the employer marks as optional: `Dutch is a strong plus`,
# `Kafka would be an advantage`. Decided 2026-10-30 on the human count: such a
# part stays in the text but is NOT counted (`nice_to_have`).
_OPTIONAL_WORDS = (r"ideally|preferably|idealerweise|vorzugsweise|bevorzugt|de pr[eé]f[eé]rence|"
                   r"id[eé]alement|preferibilmente|idealmente|bij voorkeur")
_IDEALLY_TAIL_RE = re.compile(rf",\s*(?P<word>{_OPTIONAL_WORDS})\s+(?P<tail>.+)$", re.I)
NICE_TO_HAVE_RE = re.compile(
    # An atom OPENING with `ideally` is optional (rules 0.3.0): `Ideally Excel`.
    rf"^(?:{_OPTIONAL_WORDS})\b|"
    # and with `Desirable`, `Advantageous`, `Optional` (rules 0.4.3): `Desirable
    # experience in design` was read as `Desirable`, and counted
    r"^(?:desirable|desired|advantageous|optional(?:ly)?|nice[- ]to[- ]have|an?\s+plus|bonus)\b|"
    r"^preferred\s+(?:experience|knowledge|skills?|qualifications?|background|familiarity|exposure)\b|"
    # a degree preferred in its fields (rules 0.4.3): `PhD strongly preferred in Biology`
    r"^\S+(?:\s+degree)?\s+(?:strongly\s+|highly\s+)?(?:preferred|desirable)\s+in\b|"
    r"\b(?:is|are|would be|will be|considered)\s+(?:an?\s+)?(?:(?:big|strong|real|huge|definite|"
    r"great|significant|distinct|nice|clear)\s+)?(?:plus|advantage|asset|bonus|benefit)\b|"
    r"\bnice[- ]to[- ]have\b|\b(?:is|are|would be)\s+(?:highly\s+)?(?:desirable|preferred|"
    r"beneficial|welcome|appreciated|valued)\b", re.I)
# Closing the atom with no verb (rules 0.4.2): `Master's preferred`, `PhD a
# plus`, `Python (preferred)`. The degree in `Bachelor's degree in X, Master's
# preferred` was counted as required. Read outside brackets, unless the
# bracket holds the marker alone: `cloud infrastructure (AWS preferred)` is
# required, AWS is what is preferred.
_MARK_BARE = (r"(?:(?:very|highly|strongly|much)\s+)?(?:preferred|desirable|advantageous)|"
              r"an?\s+(?:(?:big|strong|real|huge|great|nice|express|added|particular)\s+)?(?:plus|advantage|bonus)|"
              # the translator's `apprécié`, `von Vorteil` (rules 0.4.3), and `but not required`
              r"(?:(?:very|highly|much|also)\s+)?(?:appreciated|valued|welcome|desired|beneficial)|"
              r"(?<!competitive\s)(?<!strategic\s)"
              r"(?:of\s+)?advantage|(?:but|though)\s+not\s+(?:required|mandatory|essential)|"
              # rules 0.4.4: the translator's Chinese 优先 / 更好
              r"(?:(?:is|are|will\s+be)\s+)?given\s+priority|(?:is|are|would\s+be)\s+(?:even\s+)?better")
_BARE_OPTIONAL_RE = re.compile(rf"(?:^|[\s,])(?:\(\s*)?(?:{_MARK_BARE})(?:\s*\))?\W*$", re.I)
_MARK_ONLY_BRACKET_RE = re.compile(rf"\(\s*(?:{_MARK_BARE})\s*\)", re.I)


def nice_to_have(atom: str) -> bool:
    """True for an atom the employer marks as optional (`NICE_TO_HAVE_RE`).

    Only the atom carrying the phrase: `Background in IT support and
    maintenance experience is a plus` counts IT support and not maintenance, as
    the human count does. Applies whatever the flags, since it labels atoms
    rather than splitting them; callers decide whether to count them.

    `ideally` before a LANGUAGE adds one (`Fluent English, ideally German` is
    two, the user's call of 2026-11-11); before names it qualifies the
    requirement they exemplify (`ideally Excel, Qlik Sense`, not counted)."""
    m = NICE_TO_HAVE_RE.search(atom)
    if m and m.start() == 0 and re.fullmatch(rf"(?:{_OPTIONAL_WORDS})\s+(?:{_LANGS})", atom.strip(), re.I):
        return False
    if m:
        return True
    outside = re.sub(r"\([^()]*\)", lambda b: b.group(0) if _MARK_ONLY_BRACKET_RE.fullmatch(b.group(0)) else " ",
                     atom)
    return bool(_BARE_OPTIONAL_RE.search(outside))


def counted(atoms: list[str]) -> list[bool]:
    """Which atoms of ONE item count as requirements.

    An optional part does not add to a required one (`Fluent in English; Dutch
    is a strong plus` = 1). But an item that is optional as a whole is still
    the requirement the employer wrote (`Experience with Zendesk Apps Framework
    is a plus` = 1): when every atom is optional, they all count. Both read off
    the human count, 2026-10-30."""
    flags = [nice_to_have(a) for a in atoms]
    if all(flags):
        return [True] * len(atoms)
    return [not f for f in flags]
PLACEHOLDER_RE = re.compile(r"@@(\d+)##")


def _unmasked(s: str) -> str:
    """The text without the masks of its brackets: for reading its words, not for keeping."""
    return PLACEHOLDER_RE.sub(" ", s)

# a leading comma (`, and cybersecurity frameworks`) is a list cut on the wrong side
_LEAD_PUNCT = re.compile(r"^(?:[\s\-–—•*·]|[,;:]+(?:\s*and\s+)?)+")
_TRAIL_PUNCT = re.compile(r"[\s.,;:]+$")
_WS = re.compile(r"\s+")


def clean(s: str) -> str:
    s = _LEAD_PUNCT.sub("", s)
    s = _TRAIL_PUNCT.sub("", s)
    return _WS.sub(" ", s).strip()


def normalise(s: str) -> str:
    """Casefold, strip accents, collapse punctuation.

    Used for deduplication and as the input to the lexicon classifier. Note that
    apostrophes become spaces here, which any lexicon pattern must account for.
    """
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w+#.\s]", " ", s)
    return _WS.sub(" ", s).strip()


def _is_list(items: list[str]) -> bool:
    """A comma-separated run is a list only if its chunks look like terms.

    One over-long chunk no longer disqualifies the run. A genuine list often
    ends in a longer trailing item — `... access control, and compliance
    requirements within regulated industries` — and rejecting the whole run for
    it left seven requirements as one. The mean-length guard still catches runs
    of clauses, which is what this test is really for.
    """
    if len(items) < 2:
        return False
    over = sum(
        1 for i in items
        if len(i) > config.MAX_ITEM_CHARS or len(i.split()) > config.MAX_ITEM_WORDS
    )
    if over > config.MAX_LONG_ITEMS:
        return False
    if any(MODIFIER_RE.match(i) for i in items):
        return False
    if config.SPLIT_REPAIRS and any(
            MODIFIER_RE.match(a.split()[-1]) and MODIFIER_RE.match(b.split()[0])
            for a, b in zip(items, items[1:])):
        # The guide's own example of ONE requirement, `excellent written and
        # verbal communication`, was split into `Excellent written` | `verbal
        # communication`: the check above only sees a modifier standing alone,
        # not one closing a longer chunk.
        return False
    if _is_modifier_run(items) and not config.DISTRIBUTE_SHARED_TAIL:
        return False
    return sum(len(i) for i in items) / len(items) <= config.MAX_ITEM_MEAN_CHARS


def _quantity_prep(text: str, m) -> bool:
    """`at least`, `(a) minimum of`: a quantity, never the head of a list (rules 0.4.8, batch 6:
    `At fraud`, `minimum of Computer Vision`)."""
    w = m.group().strip().lower()
    return (w == "at" and bool(re.match(r"\s*least\b", text[m.end():], re.I))) or (
        w == "of" and bool(re.search(r"\b(?:minimum|maximum)\s*$", text[: m.start()], re.I)))


def _trim_head(head: str) -> str:
    """Cut a head back to its governing preposition.

    The labeller drops the generic noun a list introducer governs: `Possession
    of relevant qualifications such as CIPM` was labelled `Possession of CIPM`,
    and `Deep expertise in at least one core data domain, such as Data Strategy`
    became `Deep expertise in Data Strategy`. Keeping that filler put a constant
    twelve-token prefix on every atom, which is what made the token-overlap
    match fail on rows the splitter had otherwise got right.
    """
    m = PREP_RE.search(head)
    if config.SPLIT_REPAIRS:
        # The German `an` is also the English article: `Have an interest in
        # ...` cut at `an` and distributed `Have an WAF`. And `to` before a
        # verb is an infinitive, not the governing preposition: `Willingness to
        # acquire knowledge in web technologies such as Angular` was cut to
        # `Willingness to Angular` (rules 0.3.0).
        m = next((x for x in PREP_RE.finditer(head) if x.group().strip().lower() != "an"
                  and not (x.group().strip().lower() == "to" and _infinitive(head[x.end():]))
                  and not (x.group().strip().lower() == "at" and re.match(r"\s*least\b", head[x.end():], re.I))
                  and not (x.group().strip().lower() == "of"
                           and re.search(r"\bminimum\s*$", head[: x.start()], re.I))), None)
        if m is None and LEAD_CATEGORY_RE.search(head):
            # `Ideally certifications such as CKA, CKS`: no preposition, and
            # the category noun is what the names replace.
            return clean(head[: LEAD_CATEGORY_RE.search(head).start()]) or clean(head)
    return clean(head[: m.end()]) if m else clean(head)


def _infinitive(after: str) -> bool:
    w = after.split()[:1]
    if not w:
        return False
    if _use_pos():
        return pos.tag(w[0])[1] == "VB"
    return w[0].lower() in {"acquire", "learn", "work", "develop", "build", "use", "take", "travel",
                            "deepen", "expand", "grow", "lead", "manage", "support"}


def _head_alternatives(head: str) -> list[str]:
    """Expand a head that offers alternatives into one head per alternative.

    `Bachelor's or Master's Degree in` governs two requirements per field, not
    one, and the guide instructs the labeller to write out the cross-product.
    The elided noun is recovered from the second alternative, so `Bachelor's`
    becomes `Bachelor's Degree` rather than a bare possessive.

    Returns a single-element list when the head offers no alternatives, so the
    caller can treat both cases identically.
    """
    prep_m = None
    for m in PREP_RE.finditer(head):
        if m.end() >= len(head.rstrip()) - 1 or head[m.end():].strip() == "":
            prep_m = m
    prep = head[prep_m.start():].strip() if prep_m else ""
    core = clean(head[: prep_m.start()]) if prep_m else clean(head)

    degrees = _degree_parts(core) if config.SPLIT_REPAIRS else None
    if degrees:
        return [clean(f"{d} {prep}") for d in degrees]

    if "," in core or len(core.split()) > config.MAX_HEAD_ALT_WORDS:
        return [head]

    parts = re.split(rf"\s+(?:{_CONJ})\s+", core, flags=re.I)
    # Exactly one conjunction. Two or more means the head is itself a list of
    # alternatives with its own structure — `Pharmaberater/in oder
    # Pharmareferent/in oder abgeschlossenes Hochschulstudium der` — and the
    # cross-product of a misread head multiplies the error by the list length.
    if len(parts) != 2:
        return [head]

    left, right = clean(parts[0]), clean(re.sub(r"^(?:a|an|the|einer?|eines|einem)\s+", "", parts[1], flags=re.I))
    if not left or not right:
        return [head]

    # `Bachelor's or Master's Degree` — the noun sits only on the right, so the
    # left alternative inherits everything after the right's own qualifier.
    r_tokens = right.split()
    if len(left.split()) == 1 and len(r_tokens) > 1:
        left = f"{left} {' '.join(r_tokens[1:])}"

    return [clean(f"{left} {prep}"), clean(f"{right} {prep}")]


def _resolve_elision(items: list[str]) -> list[str] | None:
    """Complete a compound whose head was elided before a conjunction.

    `Gute Deutsch- und Englischkenntnisse` lists two requirements sharing the
    head noun `kenntnisse`. Splitting without completing it emits `Deutsch-`,
    a fragment that is worse than not splitting at all — so an elision this
    cannot resolve returns None and the caller leaves the segment whole.
    """
    if not any(ELIDED_RE.match(i) for i in items):
        return items
    tail = COMPOUND_HEAD_RE.search(items[-1])
    if not tail:
        return None
    suffix = tail.group(1)

    # Whatever qualifies the elided compound qualifies the others too: `Gute
    # Deutsch- und Englischkenntnisse` is two *good* language skills, so the
    # `Gute` is carried across rather than left on the first atom only.
    prefix = ""
    first = ELIDED_RE.match(items[0])
    if first:
        words = first.group(1).split()
        if len(words) > 1:
            prefix = " ".join(words[:-1])

    out = []
    for i in items:
        m = ELIDED_RE.match(i)
        if m:
            out.append(f"{m.group(1)}{suffix}")
        elif prefix and not i.lower().startswith(prefix.lower()):
            out.append(f"{prefix} {i}")
        else:
            out.append(i)
    return out


def _distribute_shared_head(items: list[str]) -> list[str]:
    """Repeat the first item's governing head across the bare items after it.

    `Previous work experience under KPIs and deadlines` lists two requirements
    that share everything up to `under`, and the labeller writes both out in
    full — a bare `deadlines` is not a requirement anyone could interpret later.
    Only applied when the trailing items are bare terms, since a run of full
    clauses (`Sales experience and comfort with targeting new business`) shares
    no head and must be left as it is.
    """
    if len(items) < 2:
        return items
    # Each bare item takes its head from the NEAREST PRECEDING item that has
    # one, not from the first item. `Ausbildung im Einzelhandel und/oder
    # Berufserfahrung im Verkauf von Produkten und Dienstleistungen` is two
    # clauses, and `Dienstleistungen` belongs to the second — distributing the
    # first clause's head onto it produces a requirement nobody asked for.
    out = [items[0]]
    for item in items[1:]:
        if len(item.split()) > config.MAX_BARE_TAIL_WORDS:
            out.append(item)
            continue
        if _use_pos() and SALES_PATTERNS and _owns_head(item):
            out.append(item)
            continue
        head = ""
        for prior in reversed(out):
            preps = [x for x in PREP_RE.finditer(prior) if not _quantity_prep(prior, x)]
            if not preps:
                continue
            cand = clean(prior[: preps[-1].end()])
            if cand and len(cand) <= config.MAX_HEAD_CHARS \
                    and prior[preps[-1].end():].strip():
                if _use_pos() and SALES_PATTERNS:
                    cand = _fit_head(prior, preps[-1], item)
                head = cand
                break
        if _use_pos() and SALES_PATTERNS and not head:
            head = _gerund_head(items[0], item)
        out.append(clean(f"{head} {item}") if head else item)
    return out


# PATTERNS.md P10-P12 (2026-11-02), found on the first sales sample and stated
# as grammar so they hold on any job family. A switch only so they can be
# measured on their own.
SALES_PATTERNS = True

# Nouns that frame a requirement: an item ending in one already has its own
# head (`CRM system experience`, `communication skills`) and takes no other.
# A closed class, the frame nouns of `normalise_req.HEAD_GROUPS`.
_FRAME_NOUNS = {"experience", "skills", "skill", "knowledge", "expertise", "proficiency",
                "background", "understanding", "familiarity", "abilities", "capabilities",
                "competencies", "competences", "fluency", "exposure"}


def _owns_head(item: str) -> bool:
    """P12: `Analytical skills with data-driven approach and CRM system
    experience` — the second item names its own frame noun, so the first
    item's head (`Analytical skills with`) is not repeated onto it."""
    words = item.split()
    return len(words) > 1 and re.sub(r"[^\w-]", "", words[-1]).lower() in _FRAME_NOUNS


# Fixed phrases that open with a preposition and are adverbs, not a new
# complement: `..., in particular Git` keeps the head's own preposition.
_FIXED_ADVERBIAL_RE = re.compile(
    r"^(?:in particular|in addition|in general|in short|for example|for instance|at least|"
    r"at most|in fact|of course|on top)\b", re.I)


def _fit_head(prior: str, prep: re.Match, item: str) -> str:
    """The head a bare item takes from ``prior``, fitted to how the item opens.

    P10: an item that opens with its own preposition replaces the head's:
    `Willingness to work in the afternoon, in the evening and on Saturdays` is
    `... work on Saturdays`, never `... work in in on Saturdays`.
    P11: after an infinitive (`to` + verb) a bare noun is another object of
    that verb, so the verb goes with the head: `Proven ability to manage
    cross-functional teams and supplier networks` is `... to manage supplier
    networks`, never `Proven ability to supplier networks`. A bare verb takes
    the head up to `to` as before (`Ability to document incidents and write
    reports`). `to` as a preposition (`Commitment to business alignment and
    continuous improvement`) is untouched.
    """
    first = item.split()[0]
    if PREP_RE.match(item + " ") and not first.lower() == "to" and not _FIXED_ADVERBIAL_RE.match(item):
        return clean(prior[: prep.start()])
    after = prior[prep.end():].split()
    if prep.group().strip().lower() == "to" and after and pos.tag(after[0])[1] in ("VB", "VBP") \
            and not _verb(first):
        return clean(f"{prior[: prep.end()]} {after[0]}")
    return clean(prior[: prep.end()])


def _gerund_head(first: str, item: str) -> str:
    """P11b: `Comfortable discussing APIs, webhooks, idempotency` — no
    preposition governs the list, a gerund does, so each bare object takes the
    first item up to that gerund. Only a gerund followed by its object (a noun,
    not an adverb: `Ability to work independently, teamwork` lists two
    requirements), and only onto an item that is not itself a verb phrase. A
    hyphenated `-ing` is a modifier (`problem-solving skills`), never the verb."""
    words = first.split()
    if pos.tag(item.split()[0])[1] in ("VB", "VBG", "VBP"):
        return ""
    for k, w in enumerate(words[:-1]):
        if k and "-" not in w and pos.tag(w)[1] == "VBG" \
                and pos.tag(words[k + 1])[0] in ("NOUN", "PROPN", "ADJ", "DET"):
            return clean(" ".join(words[: k + 1]))
    return ""


_RUN_VERBS = {
    "run", "recruit", "retain", "hire", "train", "optimize", "optimise", "automate",
    "configure", "install", "administer", "secure", "migrate", "refactor", "architect",
    "validate", "verify", "measure", "track", "manage", "improve", "enhance", "extend",
    "launch", "ship", "scope", "prototype", "iterate", "operationalize", "operationalise",
    "productionize", "productionise", "interpret", "visualize", "visualise", "query",
    "clean", "transform", "load", "ingest", "process", "store", "protect", "audit",
    "upgrade", "patch", "repair", "diagnose", "estimate", "forecast", "budget", "price",
    "source", "procure", "onboard", "nurture", "qualify", "prospect", "pitch", "demo",
    "promote", "market", "advise", "consult", "guide", "teach", "lead", "drive", "oversee",
    "collect", "gather", "elicit", "capture", "dig", "investigate", "explore", "experiment",
    "analyse", "model", "simulate", "benchmark", "tune", "refine", "streamline", "standardize",
    "standardise", "orchestrate", "schedule", "coordinate", "negotiate", "close", "sign",
    # rules 0.4.3: `Experience gathering, structuring, and documenting functional requirements`
    "structure", "document", "specify", "define", "prioritize", "prioritise", "facilitate",
}
# Nouns of activity before ONE object (rules 0.4.3, from the explorer on batch
# 2): `Experience in design, deployment and support of network solutions` is
# one demand, as coordinated verbs are (2026-10-29); split, it left `design`
# and `deployment` with no object.
_ACTIVITY_NOUNS = {
    "design", "development", "deployment", "implementation", "integration", "maintenance", "support", "operation",
    "operations", "testing", "configuration", "installation", "administration", "monitoring", "management",
    "optimization", "optimisation", "analysis", "documentation", "delivery", "migration", "planning", "execution",
    "evaluation", "review", "troubleshooting", "build", "creation", "setup", "set-up", "rollout", "maintaining",
}


def _activity_run(items: list[str]) -> bool:
    """Activities in a row, the last carrying the one object they share: `design,
    deployment and support of network solutions`."""
    if len(items) < 2:
        return False
    last = re.match(r"^(?P<act>[\w-]+)\s+(?:of|for)\s+\S", items[-1].strip(), re.I)
    if not last or last.group("act").lower() not in _ACTIVITY_NOUNS:
        return False
    return all(i.strip().split() and i.strip().split()[-1].lower() in _ACTIVITY_NOUNS
               and (k == 0 or len(i.split()) == 1) for k, i in enumerate(items[:-1]))


def _verb(word: str) -> bool:
    """A bare verb or its gerund: `retain`, `designing`, `running`, `debugging`."""
    # With the tagger: a base verb or gerund by its tag, so verbs no list
    # contains (`federate`, `re-seat`, `systematize`) are recognised. The list
    # still counts, as a safety net for the tagger's own errors on fragments:
    # it reads `building` in `experience building X` as the noun.
    if _use_pos() and pos.tag(word)[1] in ("VB", "VBG"):
        return True
    w = re.sub(r"[^\w-]", "", word).lower()
    verbs = _VERBS | _RUN_VERBS
    if w in verbs:
        return True
    if not w.endswith("ing") or len(w) < 6:
        return False
    stem = w[:-3]
    return stem in verbs or stem + "e" in verbs or (stem[-1] == stem[-2] and stem[:-1] in verbs)


def _merge_verb_runs(items: list[str]) -> list[str]:
    """Rejoin coordinated verbs that share one object.

    `Ability to recruit, grow, and retain top talent` and `Communicate and align
    with stakeholders` name ONE demand each (decided 2026-10-29: coordinated
    verbs sharing an object are one requirement; normalisation later reduces
    them to `Experience with <object>`). The `-ing` guard in `_is_modifier_run`
    only caught gerunds in front of a gerund, so bare verbs were split into a
    stranded `Ability to recruit` and a bare `Communicate`.

    A run is: an item ending in a verb, then single-word verbs, then an item
    that OPENS with a verb and carries the object. The run becomes one item.
    Objects listed after it share the verbs, so they take the run's verbs as
    their head: `designing, building, and maintaining data models, pipelines`
    is two requirements, `... maintaining pipelines` among them.
    `Ability to document defects and communicate with project teams` has its
    own object on each side and is untouched.
    """
    # Every verb in a run has the same form, all bare or all gerunds. Many nouns
    # look like verbs (`lead generation`, `process improvement`, `market
    # analysis`), and the form test is what keeps `prospecting, lead
    # generation and closing` a list. A bare verb must also open its item or
    # follow `to`, so `Software design, process improvement` is not a run.
    def form(w: str) -> str:
        return "ing" if w.lower().endswith("ing") else "bare"

    def opens_run(item: str) -> bool:
        words = item.split()
        if not _verb(words[-1]):
            return False
        return form(words[-1]) == "ing" or len(words) == 1 or words[-2].lower() == "to"

    out: list[str] = []
    i = 0
    while i < len(items):
        j = i
        if (i == 0 or len(items[i].split()) == 1) and opens_run(items[i]):
            f = form(items[i].split()[-1])
            while j + 1 < len(items) and len(items[j + 1].split()) == 1 \
                    and _verb(items[j + 1]) and form(items[j + 1]) == f:
                j += 1
            nxt = items[j + 1].split() if j + 1 < len(items) else []
            if len(nxt) >= 2 and _verb(nxt[0]) and form(nxt[0]) == f:
                run = items[i: j + 2]
                merged = ", ".join(run[:-1]) + " and " + run[-1]
                prefix = merged[: len(merged) - len(run[-1])] + nxt[0]
                # `deploying services across Linux` + `Windows`: the object
                # list sits after the last preposition, not after the verb.
                preps = list(PREP_RE.finditer(run[-1]))
                if preps and run[-1][preps[-1].end():].strip():
                    prefix = merged[: len(merged) - len(run[-1])] + run[-1][: preps[-1].end()].strip()
                out.append(merged)
                k = j + 2
                while k < len(items) and len(items[k].split()) <= config.MAX_BARE_TAIL_WORDS \
                        and not _verb(items[k].split()[0]):
                    out.append(clean(f"{prefix} {items[k]}"))
                    k += 1
                i = k
                continue
        out.append(items[i])
        i += 1
    return out


def _pos_class(word: str) -> str:
    """Coarse class of a conjunct for the parallelism test of `_shared_tail`."""
    if SALES_PATTERNS:
        # The non-breaking hyphen of `fast‑paced` is a hyphen.
        word = re.sub(r"[‐‑]", "-", word)
    if "-" in word.strip("-"):
        return "HYPH"            # `problem-solving`, `open-source`: either use
    p, fine = pos.tag(word)
    if p == "NOUN" and fine == "NNS":
        return "PLURAL"          # a head in its own right, never a modifier
    return p


# Hyphenated modifiers (`open-source`, `solution-oriented`) are adjectival.
_PARALLEL = {"ADJ": {"ADJ", "HYPH"}, "HYPH": {"ADJ", "HYPH"}, "NOUN": {"NOUN"}, "PROPN": {"PROPN"}}


def _shared_tail(head: str, items: list[str], alternatives: bool = False) -> list[str] | None:
    """PATTERNS.md P2: `X, Y and Z <noun>` -> one requirement per modifier.

    `Linux and Windows operating systems`, `open-source and commercial
    deception platforms`, `a senior or lead role`: the modifiers name different
    things and share the noun at the end, so each gets it. Decided by grammar
    alone (`config.SPLIT_POS`), every test a shape rather than a word:

    * every conjunct but the last is ONE word: `gap analysis and remediation
      planning` has its own noun on each side and is a list, not a tail;
    * the modifiers are parallel — adjectives with adjectives, proper nouns with
      proper nouns — and none is a plural noun, which heads its own phrase:
      `Git and collaborative development workflows`, `customers and
      non-technical stakeholders` stay lists;
    * the tail is common nouns only, so product names (`Windows Server
      administration`) are never cut;
    * nothing in front is a verb: `ability to write maintainable, well-tested
      and scalable codebases` rates one object, it does not list three;
    * modes of one skill stay one (`written and verbal communication`, guide).
    """
    if len(items) < 2 or any(len(i.split()) != 1 for i in items[1:-1]):
        return None
    last, first = items[-1].split(), items[0].split()
    if not 2 <= len(last) <= 3 or "(" in items[-1] or "(" in items[0]:
        return None
    tail = last[1:]
    if any(pos.tag(w)[0] != "NOUN" for w in tail) or pos.tag(tail[-1])[1] == "NNS" and len(tail) > 1 \
            and pos.tag(tail[0])[1] == "NNS":
        return None
    mods = [first[-1]] + items[1:-1] + [last[0]]
    if any(MODIFIER_RE.match(m) for m in mods):
        return None
    classes = [_pos_class(m) for m in mods]
    prefix = (head.split() if head else []) + first[:-1]
    if SALES_PATTERNS and alternatives and len(mods) == 2 and not prefix \
            and classes[0] in ("NOUN", "PROPN") and classes[1] == "HYPH":
        # P14: `Business or customer-related experience`, `IT or
        # client-facing roles`. Alternatives of one kind: with `or`, the bare
        # noun is the other modifier of the same tail, not a requirement by
        # itself. Only before a hyphenated modifier, which cannot head a phrase.
        return [clean(f"{m} {' '.join(tail)}") for m in mods]
    if any(c not in _PARALLEL for c in classes) \
            or any(b not in _PARALLEL[a] for a in classes for b in classes):
        return None
    tags = [pos.tag(w) for w in prefix]
    if any(fine in ("VB", "VBG", "VBP", "VBZ", "VBD") for _, fine in tags):
        if SALES_PATTERNS and all(c in ("ADJ", "HYPH") for c in classes) \
                and not _OR_RE.search(f" {' '.join(prefix)} ") \
                and not re.search(r"\band\b", " ".join(prefix), re.I):
            # Only when the adjectives are the one coordination: in `Ability
            # to manage ambiguity and operate in fast-evolving, early-stage
            # environments` the `and` before them still separates two.
            # P13: adjectives on the object of a verb describe that one
            # object, as the line above already holds: `ability to operate
            # across a complex, fast-paced and multidisciplinary environment`,
            # `create a welcoming and inclusive customer experience`. Returning
            # None let the plain list split cut them apart.
            return ONE_REQUIREMENT
        return None
    if classes[0] == "NOUN" and not (prefix and len(last) == 2):
        # A common noun is often a requirement by itself (`Rigor and team
        # spirit`, `compliance, audit, and system accreditation processes`), so
        # it takes the tail only after a governing head and before a plain
        # two-word compound: `knowledge of networking and security protocols`.
        return None
    if prefix:
        # X must stand alone in its conjunct: what precedes it is a governing
        # word (`knowledge of`, `in a`) or a bare intensifier on an adjective
        # (`Strong analytical and ...`), never a modifier of its own.
        coarse = tags[-1][0]
        governed = coarse in ("ADP", "DET") or prefix[-1].lower() in ("to",)
        rated = all(c in ("ADJ", "ADV", "DET") for c, _ in tags) and classes[0] in ("ADJ", "HYPH")
        if not (governed or rated):
            return None
    if SINGULAR_IS_ONE and classes[0] in ("ADJ", "HYPH") and pos.tag(tail[-1])[1] not in ("NNS", "NNPS"):
        # Qualities of ONE thing, not kinds of things: `Structured and
        # project-based work`, `a calm, methodical and pragmatic approach`. A
        # singular noun after coordinated adjectives names one entity; a plural
        # one names several (`analytical and problem-solving skills` = 2).
        # Decided 2026-10-30 on the human count.
        return ONE_REQUIREMENT
    return [clean(" ".join(prefix + [m] + tail)) for m in mods]


# Returned by a rule that has recognised its pattern and decided the segment
# is ONE requirement, so no later rule may split it.
ONE_REQUIREMENT: list[str] = ["<one requirement>"]
SINGULAR_IS_ONE = True   # a switch only so the rule can be measured on its own


def _cut(s: str) -> list[str]:
    parts = (clean(p) for p in SPLIT_RE.split(s))
    parts = (clean(LEAD_CONJ_RE.sub("", p)) for p in parts if p)
    out = [p for p in parts if p and not STOP_RE.match(p)]
    if config.SPLIT_REPAIRS:
        # `... or similar tools`: an alternative that names nothing. Only after
        # the first item — a requirement may open with `Comparable experience`.
        out = out[:1] + [p for p in out[1:] if not _is_filler_item(p)]
    if _use_pos() and len(out) > 1 and _is_tail_filler(out[-1]):
        out = out[:-1]
    return out


def _is_tail_filler(p: str) -> bool:
    """The closing item of a list that points back at the list itself.

    `... and related reference architectures`, `... or a national equivalent`:
    in last position a `related/similar/comparable` item, or one ending in
    `equivalent`, means "and things like the above", whatever its noun. Kept
    when it names an alternative path (`or equivalent experience`), carries a
    bracket, or holds a capitalised name (`related Procurement solutions`).
    """
    if "(" in p or "@@" in p or _ALT_PATH_RE.search(p):
        return False
    words = re.sub(r"^(?:an?|the)\s+", "", p, flags=re.I).split()
    if any(w[:1].isupper() for w in words[1:]):
        return False
    return bool(_FILLER_LEAD_RE.match(p)) or words[-1].lower() == "equivalent"


def _is_filler_item(p: str) -> bool:
    """True for an alternative that only says "something like the above".

    The guide drops `or similar`, `or a related field`. But an alternative
    PATH is a requirement, and dropping it makes the ask stricter than the
    employer wrote: `Bachelor's degree or equivalent experience` is not
    `Bachelor's degree`, and the labels keep it. So the item is filler only
    when its last word is a generic category (`tools`, `Fachrichtung`) or it
    has none, and it names no experience or qualification. A bracket inside
    it is content — `related web technologies (React/Angular)` — and a
    proper noun is too: `related Procurement or Supply Chain solutions`.
    """
    if not _FILLER_LEAD_RE.match(p) or "(" in p or "@@" in p or _ALT_PATH_RE.search(p):
        return False
    words = re.sub(r"^(?:an?|the|eine?[nmrs]?|une?)\s+", "", p, flags=re.I).split()
    return len(words) == 1 or bool(_GENERIC_CATEGORY_RE.search(words[-1]))


_CANDIDATE_RE = re.compile(r"^(?:are|be|you are|you're)\s+an?\s+", re.I)

# Segments a rule decided are ONE requirement on purpose, so `route` labels
# them `single` and not `llm` (looks compound, could not be separated).
_DECIDED_ONE: set[str] = set()


def _one(s: str) -> list[str]:
    _DECIDED_ONE.add(clean(s))
    return [s]


_EAGER_RE = re.compile(r"(?:eager|keen|willing|motivated|able|happy|ready)\s+to\s+(?:learn|grow|travel|adapt|develop)",
                       re.I)


def _trait(word: str) -> bool:
    """A one-word adjective that is a trait on its own (`Reliable`, `self-motivated`).
    Not an adverb: `independently and collaboratively` qualify one verb.
    `eager to learn` is one too (rules 0.4.4, from the review of batch 2)."""
    if _EAGER_RE.fullmatch(word.strip()):
        return True
    if " " in word or word.lower().endswith("ly"):
        return False
    if _use_pos():
        p, fine = pos.tag(word)
        return p == "ADJ" or fine == "VBN"
    return bool(ADJECTIVAL_RE.match(word)) and not NOMINAL_RE.search(word)


_AS_ROLE_RE = re.compile(r"\b(?:experience|background|years?|work(?:ed|ing)?)\s+as\s+(?:an?\s+)?", re.I)
_ROLE_END_RE = re.compile(
    r"\b(?:engineers?|developers?|scientists?|analysts?|architects?|managers?|consultants?|"
    r"specialists?|administrators?|designers?|testers?|leads?|owners?|officers?|"
    r"similar|equivalent|comparable|role|roles|position|positions)\s*$", re.I)
_FOR_NAME_RE = re.compile(r"^(?P<name>.*?[A-Z0-9#+].*?)\s+for\s+\S", re.S)

# Roles in alternative (rules 0.4.6, the user's call of 2026-11-18 on the review
# of batch 4): `as an Azure Cloud Architect, Lead Architect or Design Architect`
# names one role written three ways — one requirement, `Cloud Architect`;
# `as a Data Engineer or Data Scientist` names two roles — two requirements.
# Same role = same job noun (the last word, Developer = Engineer as titles read
# it); a seniority word does not make another role.
_ROLE_FILLER_RE = re.compile(r"^(?:an?\s+)?(?:similar|equivalent|comparable|related)"
                             r"(?:\s+(?:roles?|positions?|capacity|function))?$|^(?:roles?|positions?)$", re.I)
_ROLE_SENIORITY = {"senior", "sr", "junior", "jr", "lead", "principal", "staff", "chief", "head", "expert",
                   "mid-level", "medior", "experienced"}
def _role_noun(alt: str) -> str:
    """The job noun an alternative ends on, singular, Developer read as Engineer.
    The nouns are the job-title ones (`normalise_title._ROLE_NOUNS`), so `EMVI
    writer or tender specialist` is two roles, not `EMVI writer specialist`."""
    from . import normalise_title
    words = re.findall(r"[\w+#.-]+", alt)
    if not words:
        return ""
    w = words[-1].lower()
    if w not in normalise_title._ROLE_NOUNS and w.endswith("s") and w[:-1] in normalise_title._ROLE_NOUNS:
        w = w[:-1]
    # `ML engineering`, `software support`: a field or a service, not a job
    if w not in normalise_title._ROLE_NOUNS or w in ("engineering", "support", "thesis"):
        return ""
    if w == "developer" and not re.search(r"\b(?:business|sales)\b", alt, re.I):
        w = "engineer"
    return w


def role_alternatives(text: str) -> list[str]:
    """`Machine Learning or Software engineer` -> `Machine Learning engineer`,
    `Software engineer`: each role whole, the job noun given to those that
    share it. Filler (`or similar role`) is not a role. [] when a part is not
    a role at all."""
    parts = [p.strip(" ,.;") for p in re.split(r"\s*,\s*(?:or\s+|and/or\s+)?|\s+(?:or|and/or)\s+|\s+/\s+", text)]
    parts = [re.sub(r"^(?:an?|the)\s+", "", p, flags=re.I) for p in parts if p.strip(" ,.;")]
    parts = [p for p in parts if not _ROLE_FILLER_RE.match(p)]
    if not parts or not _role_noun(parts[-1]):
        return []
    # `leading, coaching and mentoring software developers`: activities, not roles
    if any(re.fullmatch(r"[a-z]+ing", p) or re.match(r"[a-z]+ing\s+(?:and|&)\s", p) for p in parts):
        return []
    noun = re.findall(r"[\w+#.-]+", parts[-1])[-1]
    out = [p if _role_noun(p) else f"{p} {noun}" for p in parts]
    return out if all(len(p.split()) <= 5 for p in out) else []


def one_role(alts: list[str]) -> tuple[str, str] | None:
    """The one role several alternatives name, and what was set aside for
    `extra`; None when they name different roles. The first alternative wins,
    without seniority and without a platform in front (`Azure Cloud Architect`
    -> `Cloud Architect`, Azure in `extra`): the role is the requirement."""
    if len(alts) < 2 or len({_role_noun(a) for a in alts}) != 1:
        return None
    words = alts[0].split()
    moved = []
    while len(words) > 1 and words[0].lower() in _ROLE_SENIORITY:
        moved.append(words.pop(0))
    rest = " ".join(words)
    m = re.match(r"(AWS|Azure|GCP|Google\s+Cloud|Salesforce)\s+(?=\S+\s+\S)", rest)
    if m:
        moved.append(m.group(1))
        rest = rest[m.end():]
    moved.append("or " + ", ".join(alts[1:]))
    return rest, "; ".join(moved)


def _merge_purposes(items: list[str]) -> list[str]:
    """`Python for modelling, data analysis and automation` is one requirement.

    After an item `<name> for <purpose>`, the lower-case items that follow are
    more purposes of that name, not new requirements: `Proficiency in data
    analysis` was not asked, Python for data analysis was. An item opening
    with a capital is a name and starts a new requirement (`C/C++ for embedded
    systems, Git version control and Python for ...` stays three). Only when
    the part before `for` holds a name: `tools for monitoring, logging` is a
    list of tools by purpose and is left to the other rules. Rules 0.3.0.
    """
    out: list[str] = []
    purposes: list[str] = []

    def close():
        if purposes:
            *first, last = purposes
            out[-1] = f"{out[-1]}, {', '.join(first)} and {last}" if first else f"{out[-1]} and {last}"
            purposes.clear()

    for it in items:
        if out and _FOR_NAME_RE.match(out[-1]) and it[:1].islower():
            purposes.append(it)
            continue
        close()
        out.append(it)
    close()
    return out


_FRAME_PAIR_RE = re.compile(
    r"^(?P<pre>.*?)\b(?P<h1>knowledge|understanding|experience|expertise|proficiency|command|use)"
    r"\s+(?:and|&|as well as)\s+(?:(?:practical|hands-on|working|good|solid|strong)\s+)?"
    r"(?:use|usage|application|experience|knowledge|understanding|practice|handling|expertise)"
    r"\s+(?:of|in|with)\s+(?P<obj>.+)$", re.I)
_FRAME_PREP = {"experience": "with", "expertise": "in", "proficiency": "in"}
_FRAME_PAIR_PRE = {"a", "an", "the", "solid", "strong", "good", "excellent", "deep", "sound", "basic", "proven",
                   "practical", "hands-on", "working", "very", "extensive", "thorough", "in-depth", "advanced",
                   "demonstrated", "previous", "prior", "relevant", "first", "some"}


# `BS`, `MS` and `WO` only in capitals: `ms` and `wo` are words, and `MS
# Office` is not a degree because nothing degree-shaped follows it. Rules 0.4.2,
# with the same names in `normalise_req.DEGREES`.
_DEG_WORD = (r"(?:bachelor(?:'s|’s|s)?|master\s*2(?!\d)|master(?:'s|’s|s)?|b\.?\s?sc\.?|m\.?\s?sc\.?|b\.?\s?a\.?|"
             r"m\.?\s?a\.?|(?-i:B\.?S\.?|M\.?S\.?|WO|MBO\+?|L3)|b\.\s?e\.|[bm]\.?\s?tech\.?|bba|mca|associate(?:'s|’s)?|"
             r"hbo\+?|"
             r"undergraduate|postgraduate|bse|baccalaureate|triennial(?=\s+degree)|bac\s*\+\s*\d|"
             r"b\.?\s?eng\.?|m\.?\s?eng\.?|ph\.?\s?d\.?|doctorate|mba|diploma|licen[cs]e)")
# Between two degrees: `,`, `, or`, `/`, `or`, `and/or`, and the Dutch `of`
# (`Bachelor of Master in Informatica`), which cannot mean the English `of`
# between two degree words. Rules 0.4.1.
_DEG_SEP = r"\s*,\s*(?:(?:or|and/or)\s+)?|\s*/\s*|\s+(?:or|and/or|of)\s+"
# Words before a list of degrees that leave it a list of degrees: `Relevant
# bachelor's or master's degree in X` (rules 0.4.2; only an article was
# allowed, and the split wrote `Relevant bachelor's Machine Learning`).
_DEG_LEAD = (r"(?:(?:a|an|the|relevant|related|completed|finished|university|academic|technical|recognised|"
             r"recognized|accredited|formal|appropriate|suitable|advanced|higher|"
             # rules 0.4.4: `Good Bachelor's or Master's degree`, students
             r"good|excellent|strong|current|currently|ongoing)\s+)*")
_DEG_PART_RE = re.compile(rf"^{_DEG_LEAD}(?P<deg>{_DEG_WORD})(?P<noun>\s+(?:degree|diploma)s?)?$", re.I)


def _degree_parts(core: str) -> list[str] | None:
    """`A Bachelor's, Master's or PhD degree` -> one head per degree, the noun carried.

    `_head_alternatives` took exactly two alternatives with no article, so `A
    Bachelor's or Master's degree in X, Y` kept the article on the left one,
    could not hand it the noun, and wrote `A Bachelor's X`, which no rule then
    read as a degree (318 atoms in the batch). Found reading the API test of
    2026-11-13; rules 0.4.1."""
    prep = re.search(r"\s+(?:in|of|on)$", core, re.I)
    if prep:
        core, prep = core[: prep.start()], prep.group(0)
    parts = [p.strip() for p in re.split(_DEG_SEP, core, flags=re.I) if p and p.strip()]
    if len(parts) < 2:
        return None
    found = [_DEG_PART_RE.match(p) for p in parts]
    if not all(found):
        return None
    noun = next((m.group("noun") for m in reversed(found) if m.group("noun")), "")
    return [f"{m.group('deg')}{m.group('noun') or noun}{prep or ''}" for m in found]


_DEG_UNIT = rf"{_DEG_WORD}(?:\s+degree)?"
_DEG_ALT_RE = re.compile(
    rf"^{_DEG_LEAD}(?P<degs>{_DEG_UNIT}(?:(?:{_DEG_SEP}){_DEG_UNIT})+)"
    # a bracket reaches here masked (`@@0##`, `_atomise_once`)
    # `level`, `training` and `within` since 0.4.4: `HBO+ or WO level within IT`
    r"(?P<tail>(?:\s+(?:degree|diploma|programme|program|level|training|studies))?(?:\s*(?:\([^()]*\)|@@\d+##))?"
    r"\s+(?:in|of|within)\s+"
    r"(?P<field>.+))$", re.I)


_DEG_ANY_RE = re.compile(rf"(?<!\w)(?:{_DEG_WORD}|degree)(?!\w)", re.I)

# `Maîtrise de X` is command of X; the translator writes `Master's degree in
# X` (`Maîtrise de l'anglais` -> `Master in English`, 119 atoms in the
# batch). Only where the French opens on it and the English opens on a degree.
_MAITRISE_RE = re.compile(r"^\W*(?:(?:une?|la|bonne|excellente|parfaite|tr[eè]s\s+bonne)\s+)?"
                          r"ma[iî]trise\s+(?:de|du|des|d['’])", re.I)
_MASTER_EN_RE = re.compile(r"^(?:(?:a|an|the)\s+)?(?:(?:good|excellent|perfect|very\s+good)\s+)?"
                           r"master(?:'s|’s|s)?(?:\s+degree)?(?:\s+(?:in|of))?\s+", re.I)


# `Maîtrise Pack office` with no `de` (rules 0.4.3): command of a product, written
# with its capital, translated `Master's Pack Office`.
_MAITRISE_NAME_RE = re.compile(r"^\W*ma[iî]trise\s+(?=(?-i:[A-Z]))", re.I)
# `maîtrise d'œuvre` is construction project management, translated `Master of
# Works` and read as a degree (rules 0.4.3)
_MOE_RE = re.compile(r"ma[iî]trise\s+d['’]\s*(?:œ|oe)uvre", re.I)


def repair_translation(item: str, english: str) -> str:
    """The translation, with the mistranslations that change a requirement's kind put right.

    Both the batch and the library call it between translating and splitting,
    so they read the same English. Rules 0.4.1; 0.4.3 added the two below."""
    if english != item and (_MAITRISE_RE.match(item) or _MAITRISE_NAME_RE.match(item)) and _MASTER_EN_RE.match(english):
        return _MASTER_EN_RE.sub("Strong knowledge of ", english, count=1)
    if english != item and _MOE_RE.search(item):
        return re.sub(r"\bmaster\s+of\s+works?\b", "construction project management", english, flags=re.I)
    # the Spanish `Bachillerato` is the school-leaving certificate, translated
    # `Bachelor's degree` (rules 0.4.4)
    if english != item and re.search(r"\bbachillerato\b", item, re.I):
        return re.sub(r"\bbachelor(?:'s|’s)?(?:\s+degree)?", "High school diploma", english, count=1, flags=re.I)
    # Dutch left in the English by the translator (review of batch 2)
    english = re.sub(r"\bbedrijfsprocessen\b", "business processes", english, flags=re.I)
    return english


# The years an experience is asked in, opening it: `2–3 years of`, `10+ years`.
_YEARS_LEAD = r"\d{1,2}\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b"
_DEG_WITH_EXP_RE = re.compile(
    rf"^(?P<deg>(?:(?:a|an|the|university|academic|completed)\s+)?(?:{_DEG_WORD}|degree)(?!\w).*?)"
    # `with`, `+`, and since rules 0.4.2 `and` and nothing at all before years
    # (`Master's degree and 4 years of ...`, `Master's degree 2–3 years of
    # ...`): the experience was read as the degree's field.
    rf"(?:\s*,?\s+(?:combined\s+|together\s+)?with\s+|\s+(?:\+|plus|and)\s+|\s+(?={_YEARS_LEAD}))"
    # knowledge, understanding, expertise too since 0.4.3: `Master's degree
    # with deep technical knowledge on AI ML products`
    rf"(?P<exp>(?:(?!\bwith\b).)*?\b(?:experiences?|knowledge|understanding|expertise)\b.*?|"
    rf"{_YEARS_LEAD}(?:(?!\bwith\b).)*?)"
    r"(?:\s+(?:is\s+)?required)?$", re.I)


def _degree_alternatives(s: str) -> list[str] | None:
    """`MSc or PhD in Physics` -> `MSc in Physics`, `PhD in Physics`.

    With a list of fields the head-and-list path makes the cross product
    (`MSc or PhD in Physics, Mathematics` = 4, convention of 2026-10-30); with
    ONE field it split on `or` and left the first degree bare (`MSc`,
    `Bachelor's`), in rules 0.2.0 already. Found in the first API test of
    0.3.0, 2026-11-11; rules 0.3.1.

    Since rules 0.4.1 a list of fields is crossed here too, one degree at a
    time through the ordinary path: the head-and-list path cannot read three
    degrees (`Bachelor's Degree, Master's Degree or PhD in X, Y`) because the
    commas between them look like the list."""
    m = _DEG_ALT_RE.match(s)
    if not m:
        return None
    degs = [d for d in re.split(_DEG_SEP, m.group("degs"), flags=re.I) if d and d.strip()]
    if len(degs) < 2:
        return None
    # `Bachelor's or Master's degree`: the noun written once is every degree's
    noun = next((n.group(0) for n in (re.search(r"\s+degree$", d, re.I) for d in reversed(degs)) if n), "")
    degs = [d if re.search(r"\s+degree$", d, re.I) else f"{d}{noun}" for d in degs]
    degs = _one_per_level(degs)
    if len(degs) < 2:
        return [clean(f"{degs[0]}{m.group('tail')}")] if not SPLIT_RE.search(m.group("field")) \
            else _split_list(clean(f"{degs[0]}{m.group('tail')}"))
    if SPLIT_RE.search(m.group("field")):
        return [a for d in degs for a in _split_list(clean(f"{d}{m.group('tail')}"))]
    return [clean(f"{d}{m.group('tail')}") for d in degs]


# Four ways a degree item closes that the rules read as part of the degree.
# All found in the first batch of new postings (2026-11-15) and fixed in rules
# 0.4.2; `_degree_routes` applies them.
_PREF = (r"(?:(?:is|are)\s+)?(?:(?:strongly|highly)\s+)?(?:preferred|desirable|advantageous)|"
         r"(?:is\s+)?an?\s+(?:(?:big|strong)\s+)?(?:plus|advantage|asset)")
# `Bachelor's degree or relevant experience`: a second route into the job, as
# `or equivalent experience` already was (`_ALT_TAIL_RE`). It was glued into
# the degree: `Bachelor in or relevant experience`.
_DEG_OR_EXP_RE = re.compile(
    r"\s*,?\s+(?:or|and/or)\s+(?P<alt>(?:an?\s+)?(?:\d{1,2}\s*\+?\s*years?\s+of\s+)?"
    # `equivalent related work`, `directly related professional` and the years
    # in front since rules 0.4.3; and `a suitable combination of education,
    # experience and training`, which is the same second route
    r"(?:(?:relevant|related|practical|professional|industry|work|hands-on|equivalent|directly|comparable|research|"
    # `or significant experience in a Software Engineering environment` (0.4.4)
    r"significant|substantial|extensive|proven)\s+)*"
    r"(?:years\s+of\s+)?(?:work\s+)?experiences?\b[^,;()]*|"
    r"(?:an?\s+)?(?:suitable|equivalent|relevant|appropriate)\s+combination\s+of\s+[^;()]*)[.]?$", re.I)
# `MBA or other relevant advanced degree preferred`: any other degree would do,
# so the alternatives count once (convention of 2026-10-30), as `or equivalent
# qualification` (`_EQUIV_DEGREE_RE`). Its own atom was `other relevant
# advanced degree preferred`.
_OTHER_DEGREE_RE = re.compile(
    rf"\s*,?\s+(?:or|and/or)\s+(?:an?\s+|any\s+)?other\s+(?:[\w-]+\s+){{0,3}}?"
    rf"(?:degrees?|qualifications?|diplomas?)(?P<mark>\s+(?:{_PREF}))?\s*[.]?$", re.I)
# `Bachelor's degree or equivalent experience, Master's Degree Preferred`: the
# preferred degree is an atom of its own, and the rest is split as usual.
_PREF_DEGREE_TAIL_RE = re.compile(
    rf",\s*(?P<pref>{_DEG_LEAD}{_DEG_UNIT}(?:\s+(?:in|of)\s+[^,;()]+?)?\s+(?:{_PREF}))\s*[.]?$", re.I)
# `Bachelor's degree preferred (Engineering, Computer Science, Analytics)`:
# the bracket holds the fields, crossed with the degree as `in X, Y` is.
_DEG_BRACKET_RE = re.compile(
    rf"^(?P<deg>{_DEG_LEAD}{_DEG_UNIT}(?:(?:{_DEG_SEP}){_DEG_LEAD}{_DEG_UNIT})*)"
    # `required` after the bracket since rules 0.4.3: `BSE (EE, ECE, CS, or similar) required`
    rf"(?P<mark>\s+(?:{_PREF}))?\s*\((?P<fields>[^()]+)\)(?P<mark2>\s*(?:{_PREF}))?(?:\s+(?:is\s+)?required)?\s*[.]?$",
    re.I)


# `BS / BA degree`, `HBO/WO`: degrees with no field, one atom each.
_DEG_BARE_LIST_RE = re.compile(
    rf"^{_DEG_LEAD}{_DEG_UNIT}(?:(?:{_DEG_SEP}){_DEG_LEAD}{_DEG_UNIT})+(?:\s+(?:degree|diploma)s?)?"
    rf"(?P<mark>\s+(?:{_PREF}))?\s*[.]?$", re.I)


def _one_per_level(degs: list[str]) -> list[str]:
    """One degree per level: `Bachelor's / Undergraduate Degree` and `BS / BA` are one each.

    Read with `normalise_req`, so two spellings the columns cannot tell apart
    are not two requirements. Rules 0.4.2."""
    from . import normalise_req     # it imports this module
    seen: set[str] = set()
    out = []
    for d in degs:
        level = normalise_req._degree(re.sub(rf"^{_DEG_LEAD}", "", d.strip(), flags=re.I), "")
        if level not in seen:
            seen.add(level)
            out.append(d)
    return out


# Rules 0.4.3, from batch 2. `Bachelor's degree required, Master's preferred,
# in X, Y`: the first degree counts, the second is preferred, both in the fields.
_REQ_PREF_DEGREES_RE = re.compile(
    rf"^(?P<a>{_DEG_LEAD}{_DEG_UNIT})\s+(?:is\s+)?required\s*[,;]\s*(?P<b>{_DEG_UNIT})\s+"
    rf"(?:(?:strongly|highly)\s+)?preferred\s*,\s+(?P<tail>in\s+.+)$", re.I)
# `Master's degree required; PhD strongly preferred in Biology`: with no comma
# before `in`, the fields are the second degree's only.
_REQ_THEN_RE = re.compile(rf"^(?P<a>{_DEG_LEAD}{_DEG_UNIT})\s+(?:is\s+)?required\s*[,;]\s*(?P<rest>.+)$", re.I)
# `PhD strongly preferred in Biology, Genetics`: a preferred degree in its fields.
_PREF_IN_RE = re.compile(rf"^(?P<deg>{_DEG_LEAD}{_DEG_UNIT})\s+(?:(?:strongly|highly)\s+)?(?:preferred|desirable)"
                         rf"\s+(?P<tail>in\s+.+)$", re.I)
# `Bachelor degree preferably with medical background`: the degree in any
# field counts, the background is preferred.
_PREF_BACKGROUND_RE = re.compile(rf"^(?P<deg>{_DEG_LEAD}{_DEG_UNIT}(?:(?:{_DEG_SEP}){_DEG_LEAD}{_DEG_UNIT})*)\s*,?\s+"
                                 r"(?P<pref>(?:preferably|ideally)\s+(?:with|in)\s+(?:an?\s+)?[^,;()]+?\s+"
                                 # `ideally with economic relevance` (0.4.4)
                                 r"(?:background|relevance|focus|orientation|reference))\s*[.]?$", re.I)
# `A PhD or equivalent research experience in ML, AI, CS`: the degree in each
# field, and the experience once (a second route, convention of 2026-10-30).
_DEG_OR_EXP_IN_RE = re.compile(
    rf"^(?P<deg>{_DEG_LEAD}{_DEG_UNIT})\s+or\s+(?P<exp>(?:equivalent\s+|relevant\s+|comparable\s+)?"
    r"(?:research\s+|professional\s+|work\s+|industry\s+)?experience)\s+(?P<tail>in\s+.+)$", re.I)


def _prepare_degrees(segment: str) -> str:
    """What around a degree is not a requirement, taken off before the split (rules 0.4.3).

    `B.E. / B.Tech or equivalent in X`, `Master's degree (or equivalent) with
    ...`: `or equivalent` after a degree adds nothing (`equivalent alternatives
    = 1`, 2026-10-30); `or engineering school`, `from an accredited institution`
    say where, not what; the translator's `WW` is the Dutch `WO`; `towards` is
    `richting`; two degrees of different levels joined by `/` are alternatives
    (`Master's degree/triennial degree in X`)."""
    if not _DEG_ANY_RE.search(segment) and not re.search(r"\b(?:studies|higher\s+professional\s+education)\b",
                                                          segment, re.I):
        return segment
    from . import normalise_req     # it imports this module
    # Rules 0.4.4, from batch 3, first: the translator's Dutch `hoger
    # beroepsonderwijs` is HBO, a bachelor (`MSc or higher professional
    # education degree`), and `HBO or WE` its `WO`
    s = re.sub(r"\bhigher\s+professional\s+education\b", "HBO", segment, flags=re.I)
    s = re.sub(r"\b(HBO\+?\s+or\s+)(?-i:WE)\b", r"\1WO", s, flags=re.I)
    # `Bac+5 in engineering school or university master's degree`: where, not
    # what — a master either way
    s = re.sub(r"\bBac\s*\+\s*5\s+(?:in|from|at)\s+(?:an?\s+)?engineering\s+school\s+or\s+(?:a\s+)?university\s+"
               r"(?=master)", "", s, flags=re.I)
    s = re.sub(rf"(\b{_DEG_WORD}(?:\s+degree)?)\s*(?:\(\s*or\s+equivalent\s*\)|,?\s+or\s+equivalent"
               # `or equivalent higher education qualification in X` (0.4.4)
               r"(?:\s+(?:higher\s+education\s+)?(?:qualification|degree|diploma|education))?)(?=\s+(?:in|with)\b)",
               r"\1", s, flags=re.I)
    # `Bac+2 training at baccalaureate+5`: the translator's `bac+2 à bac+5`, a range (0.4.4)
    s = re.sub(r"\b(bac\s*\+\s*\d)\s+(training\s+)?(?:at|to|à)\s+(?:bac(?:calaureate)?\s*\+\s*)(\d)\b", r"\1 to \3 \2",
               s, flags=re.I)
    # `with preference for X or Y`: the preferred field is the field (0.4.4)
    s = re.sub(rf"(\b{_DEG_WORD}(?:\s+degree)?)\s+with\s+(?:a\s+)?preference\s+for\s+", r"\1 in ", s, flags=re.I)
    # `Master's degree as a statistician, physicist, ...`: the roles say no field (0.4.4)
    s = re.sub(rf"(\b{_DEG_WORD}(?:\s+degree)?)\s+as\s+(?:an?\s+)?[\w-]+(?:\s*,\s*[\w-]+)*(?:,?\s+(?:or|and)\s+[\w-]+)?\s*[.]?$",
               r"\1", s, flags=re.I)
    # students (0.4.4): `You will follow an HBO or WO programme, for example in
    # the direction of X`, `Currently completing the final stage of a bachelor's
    # degree or have recently started a master's degree in X`, `Current studies
    # at <a university> in the fields of X`, `Final-year student from an
    # Engineering School or equivalent Master's degree in X`
    s = re.sub(r"^you\s+(?:will\s+)?(?:follow|are\s+following|are\s+completing)\s+(?:an?\s+)?", "current ", s, flags=re.I)
    s = re.sub(r"^currently\s+completing\s+(?:the\s+)?(?:final|last)\s+(?:stage|year)\s+of\s+(?:an?\s+)?", "current ",
               s, flags=re.I)
    s = re.sub(r"\s+or\s+have\s+recently\s+started\s+(?:an?\s+)?", " or ", s, flags=re.I)
    s = re.sub(r",?\s+for\s+example\s+in\s+the\s+direction\s+of\s+", " in ", s, flags=re.I)
    s = re.sub(r"\s+at\s+(?:the\s+)?(?-i:[A-Z])[^,;]*?(?=\s+in\s+(?:the\s+)?fields?\s+of\b)", "", s)
    s = re.sub(r"\s+in\s+the\s+fields?\s+of\s+", " in ", s, flags=re.I)
    s = re.sub(r"\s+from\s+an?\s+(?:engineering|business)\s+school\s+or\s+equivalent\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+or\s+(?:an?\s+)?(?:engineering|business)\s+schools?(?=\s+in\b)", "", s, flags=re.I)
    # `Bachelor's Degree or higher in X`, `Bachelor's, Master's, or higher degree in X`: at least that degree
    s = re.sub(rf"(\b{_DEG_WORD})(\s+degree)?,?\s+or\s+(?:higher|above)(?P<n>\s+degrees?)?\b",
               lambda m: f"{m.group(1)}{m.group('n') or m.group(2) or ''}", s, flags=re.I)
    s = re.sub(r"\s+from\s+(?:an?\s+)?(?:accredited|recognised|recognized)\s+(?:institution|university|school|college)\b",
               "", s, flags=re.I)
    s = re.sub(r"\b(?-i:WW)(?=\s+(?:training|degree|education)\b)", "WO", s)
    s = re.sub(r"\b(training|education|level)\s+towards\s+", r"\1 in ", s, flags=re.I)
    # `Master's degree with engineering, scientific or economic direction`: the
    # translator's `mit ... Ausrichtung` names the fields
    s = re.sub(rf"(\b{_DEG_WORD}(?:\s+degree)?)\s+with\s+(?:an?\s+)?(?P<f>[\w ,/-]+?)\s+(?:direction|orientation)\b",
               r"\1 in \g<f>", s, flags=re.I)
    m = re.match(rf"^(?P<a>{_DEG_WORD}(?:\s+degree)?)\s*/\s*(?P<b>{_DEG_WORD}(?:\s+degree)?)(?=\s)", s, flags=re.I)
    if m and normalise_req._degree(m.group("a"), "") != normalise_req._degree(m.group("b"), ""):
        s = f"{m.group('a')} or {m.group('b')}{s[m.end():]}"
    return s


def _degree_routes(segment: str) -> list[str] | None:
    """The closings of `_DEG_OR_EXP_RE` to `_DEG_BARE_LIST_RE`, or None."""
    if not _DEG_ANY_RE.search(segment):
        return None
    m = _REQ_PREF_DEGREES_RE.match(segment)
    if m:
        req = _split_list(clean(f"{m.group('a')} {m.group('tail')}"))
        pref = _split_list(clean(f"{m.group('b')} {m.group('tail')}"))
        return req + [f"{p} preferred" for p in pref]
    m = _REQ_THEN_RE.match(segment)
    if m and _DEG_ANY_RE.search(m.group("rest")):
        rest = clean(m.group("rest"))
        return [clean(m.group("a"))] + (_degree_routes(rest) or _atomise_once(rest) or [rest])
    m = _PREF_IN_RE.match(segment)
    if m:
        return [f"{p} preferred" for p in _split_list(clean(f"{m.group('deg')} {m.group('tail')}"))]
    m = _PREF_BACKGROUND_RE.match(segment)
    if m:
        degs = _degree_parts(clean(m.group("deg"))) or [clean(m.group("deg"))]
        return _one_per_level(degs) + [clean(m.group("pref"))]
    m = _DEG_OR_EXP_IN_RE.match(segment)
    if m:
        return _split_list(clean(f"{m.group('deg')} {m.group('tail')}")) + [clean(m.group("exp"))]
    m = _DEG_BARE_LIST_RE.match(segment)
    if m:
        core = segment[: m.start("mark")] if m.group("mark") else segment
        parts = _degree_parts(clean(core))
        if parts:
            return [f"{p}{m.group('mark') or ''}" for p in _one_per_level(parts)]
    m = _DEG_OR_EXP_RE.search(segment)
    if m and _DEG_ANY_RE.search(segment[: m.start()]):
        main = clean(segment[: m.start()])
        return (_atomise_once(main) or [main]) + [clean(m.group("alt"))]
    m = _OTHER_DEGREE_RE.search(segment)
    if m and _DEG_ANY_RE.search(segment[: m.start()]):
        main = clean(f"{segment[: m.start()]}{m.group('mark') or ''}")
        return _atomise_once(main) or [main]
    m = _PREF_DEGREE_TAIL_RE.search(segment)
    if m and _DEG_ANY_RE.search(segment[: m.start()]):
        main = clean(segment[: m.start()])
        return (_atomise_once(main) or [main]) + [clean(m.group("pref"))]
    m = _DEG_BRACKET_RE.match(segment)
    if m:
        inner = _PAREN_LEAD_RE_V2.sub("", m.group("fields")).strip()
        fields = [f for f in _cut(inner) if not _FILLER_LEAD_RE.match(f) and not STOP_RE.match(f)]
        if len(fields) < 2 or any(re.search(r"\d", f) or len(f.split()) > config.MAX_ITEM_WORDS for f in fields):
            return None
        mark = clean(m.group("mark") or m.group("mark2") or "")
        mark = f" {mark}" if mark else ""
        deg = clean(m.group("deg"))
        out = []
        for f in fields:
            one = f"{deg} in {f}"
            out.extend(f"{d}{mark}" for d in (_degree_alternatives(one) or [one]))
        return out
    return None


_CONTEXT_NOUNS_RE = re.compile(r"\b(?:environments?|industr(?:y|ies)|sectors?|teams?|functions?|departments?|"
                               r"clients?|customers?|stakeholders?|markets?|regions?|countries|settings?)\s*[.;]?$",
                               re.I)


_NAME_NOUN_PAIR_RE = re.compile(
    r"(?-i:\b(?:[A-Z]{2,}[\w.+#/-]*|[A-Z][a-z]+[A-Z][\w]*))\s+(?P<a>[a-z]+s)\s+(?:and|&)\s+(?P<b>[a-z]+s)\s*\.?$")


def _context_list(before: str, trigger: str, rest: str) -> bool:
    """A list after the object is already said is where or with whom, one requirement (rules 0.4.8,
    batch 6): `stakeholder management skills across IT, Finance, Legal` was four requirements,
    `Salesforce experience in B2B and/or B2C environments` two. Only after `across` or `within`,
    or a list of places, teams or sectors; and only when the part before names its object: a name,
    or `... skills` / `... management` after a word of its own (`Experience in Python, Java` is a
    list of requirements)."""
    from . import normalise_req as _nr     # it imports this module
    t = trigger.strip().lower()
    if _DEG_ANY_RE.search(before):          # a degree with an experience is two asks
        return False
    if not (t in ("across", "within") or (t in ("in", "with", "for") and _CONTEXT_NOUNS_RE.search(rest))):
        return False
    words = before.split()
    has_object = bool(_nr._name_runs(_unmasked(before))) and not re.match(
        r"^(?:(?:strong|solid|good|proven|hands-on|deep|excellent|extensive)\s+)*(?:experience|knowledge|"
        r"proficiency|expertise|understanding|familiarity)$", before.strip(), re.I)
    if len(words) < 2:
        return False
    has_object = has_object or bool(re.search(r"\w+\s+(?:skills|management)$", before.strip(), re.I)
                                    and len(words) >= 2
                                    and words[-2].lower() not in ("strong", "solid", "good", "proven", "hands-on"))
    return has_object and bool(SPLIT_RE.search(rest))


def _split_list(s: str) -> list[str]:
    """Split one clause, either as head + list or as a bare coordinated list."""
    if config.SPLIT_REPAIRS and _NAME_NOUN_PAIR_RE.search(s) and not re.search(r",", s):
        return [s]
    if config.SPLIT_REPAIRS:
        last = list(re.finditer(r"\s(across|within|in|with|for)\s+", s, re.I))
        if last:
            before, trig, rest = s[: last[-1].start()], last[-1].group(1).lower(), s[last[-1].end():]
            eased = re.sub(r"\s+and\s+(?:ease|comfort)\s+(?:in\s+)?(?:working|interacting|collaborating|dealing)$",
                           "", before, flags=re.I)
            areas = [clean(x) for x in SPLIT_RE.split(rest) if clean(x)]
            if any(re.match(r"(?:multiple|various|several|different|other|all|many)\b", a, re.I) for a in areas):
                areas = []
            if len(areas) >= 2 and trig in ("across", "within") and all(re.fullmatch(
                    r"(?:the\s+)?(?:teams?|domains?|functions?|departments?|levels?|regions?|cultures?|time\s*zones?|"
                    r"borders?|boundaries|organi[sz]ations?|disciplines?|business\s+units?|countries|geographies)",
                    a, re.I) for a in areas):
                return [clean(f"{p} {trig} {rest}") for p in _split_list(clean(before))]
            if len(areas) >= 2 and (eased != before or trig in ("across", "within")) \
                    and _context_list(eased, "across", rest):
                return [clean(eased)] + areas
            if trig in ("in", "for") and not SPLIT_RE.search(before) and _context_list(before, trig, rest):
                return [s]
        m = _DEG_WITH_EXP_RE.match(s)
        if m:
            # `Bachelor's degree in IT with Financial systems experience
            # required`: a degree and an experience, two requirements. Left
            # whole, the experience became part of the degree's field. Rules 0.4.1.
            return _split_list(clean(m.group("deg"))) + [clean(m.group("exp"))]
        degrees = _degree_alternatives(s)
        if degrees:
            return degrees
        m = _FRAME_PAIR_RE.match(s)
        if m and any(w.lower() not in _FRAME_PAIR_PRE for w in m.group("pre").split()):
            # `business understanding as well as experience in X`: the first frame
            # has its own object in front, so the two are two requirements.
            m = None
        if m:
            # `Solid knowledge and use of SQL`: two frame nouns over one object
            # are one ask, as coordinated verbs are (2026-10-29); the first frame
            # keeps the object. Rules 0.3.0, from the 2026-11-09 trial.
            h1 = m.group("h1")
            s = clean(f"{m.group('pre')}{h1} {_FRAME_PREP.get(h1.lower(), 'of')} {m.group('obj')}")
            if not SPLIT_RE.search(m.group("obj")):
                return _one(s)
    if _use_pos() and SALES_PATTERNS:
        clauses = _split_gerund_clauses(s)
        if clauses:
            return clauses
    head, rest = "", s
    lead: list[str] = []

    # An explicit introducer (`such as`, `including`, `:`) is a stronger signal
    # than a bare preposition, and it tells us where the filler ends. Preferred
    # over the preposition search, and the head is trimmed back past the filler.
    intro = (INTRODUCER_RE_V2 if config.SPLIT_REPAIRS else INTRODUCER_RE).search(s)
    if intro:
        pre = clean(s[: intro.start()])
        head, rest = _trim_head(pre), s[intro.end():]
        lead_ok = bool(pre) and not GENERIC_TAIL_RE.search(pre) and len(pre.split()) > 1 \
            and not (config.SPLIT_REPAIRS and LEAD_CATEGORY_RE.search(pre))
        if config.SPLIT_REPAIRS:
            # The user's calls of 2026-11-17, from the review of batch 2: NAMED
            # examples are the requirements and the category goes (`databases
            # such as PostgreSQL, MongoDB`); examples that are common nouns, and
            # what `including` lists, belong to the category: one requirement,
            # the examples kept in a bracket for `extra` (`digital components
            # such as Ethernet switch, memories, modem`; `a sales pipeline,
            # including forecasting`). After a colon only under a name
            # (`concurrent Python: threading, multiprocessing`); `one of the core
            # industries: X, Y` lists the requirements themselves.
            from . import normalise_req as _nr     # it imports this module
            word = re.sub(r"[\s,:]+", " ", intro.group(0)).strip().lower()
            examples = [e for e in _cut(rest) if e.strip()]
            named = [bool(_nr._name_runs(e)) for e in examples]
            if re.search(r"\bone\s+(?:or\s+more\s+)?of\s+(?:the\s+)?(?:following\s+)?|\bone\s+or\s+more\b",
                         pre, re.I):
                lead_ok = False
            elif examples and all(named) and _PLATFORM_RE.search(_unmasked(pre)):
                # the examples are parts of a platform named before them: the
                # platform is asked, its services kept for `extra` (review of batch 3)
                return [clean(f"{pre} ({rest.strip(' .;')})")]
            elif examples and (all(named) or (word.startswith("including") and sum(named) >= 2
                                              and len(examples) >= 3)):
                lead_ok = False
                # the category goes with the lead: `Scripting languages such as
                # Python or Bash` is Python and Bash, the frame kept up to its
                # preposition (`Experience with`)
                frame = list(TRIGGER_RE.finditer(head + " "))
                head = (head + " ")[: frame[-1].end()] if frame else ""
                body = pre[len(head.rstrip()):] if head.strip() and pre.startswith(head.rstrip()) else ""
                parts = [clean(LEAD_CONJ_RE.sub("", clean(p))) for p in SPLIT_RE.split(body) if clean(p)]
                # two categories joined are one (`big data frameworks and technologies such as`);
                # a name, or a real list, are requirements of their own
                if len(parts) >= 3 or (len(parts) == 2 and _nr._name_runs(_unmasked(parts[0]))):
                    lead = [clean(f"{head} {p}") for p in parts[:-1]]
                elif re.search(r"\b(?:role|position)s?\b", body, re.I):
                    # `3 years in a DevOps role with cloud platforms like AWS`: the role too
                    lead = [clean(f"{head} " + re.sub(r"(\b(?:role|position)s?)\b.*$", r"\1", body, flags=re.I))]
            elif len(examples) >= 2 and not word and sum(named) * 2 < len(examples) \
                    and _nr._name_runs(_unmasked(pre)) and len(pre.split()) <= 4 \
                    and not re.search(r"\b(?:Skills?|Requirements?|Languages?|Tools?|Technolog(?:y|ies)|Stack|"
                                      r"Frameworks?|Protocols?|Qualifications?)\b", _unmasked(pre)):
                return [clean(f"{pre} ({rest.strip(' .;')})")]
            elif len(examples) >= 2 and not word \
                    and ((not _nr._name_runs(_unmasked(pre))
                          and not all(w[:1].isupper() for w in _unmasked(pre).split()))
                         # a generic word heads it, capitals or not (`L2/L3 Protocols:`, rules 0.4.8)
                         or re.search(r"\b(?:Skills?|Requirements?|Languages?|Tools?|Technolog(?:y|ies)|"
                                      r"Protocols?|Qualifications?|Experience|Knowledge|Stack|Frameworks?|"
                                      r"Fundamentals|Concepts)\b", _unmasked(pre))) \
                    and (any(named) or not re.search(r"(?<![\w-])[A-Z]", _unmasked(rest))):
                # (names the name test missed, `comfortable administering Windows
                # and/or Linux workstations`, keep the rule as it was)
                # `Header: a, b, c` under a header that is no name (rules 0.4.7,
                # batch 5: the header was glued onto every item, `backend
                # fundamentals queues`). Common nouns only: the header is the
                # requirement, they its `extra` (`Experience building evaluation
                # pipelines: datasets, labelling, metrics`). Some names among
                # them: the items are the requirements, the header goes
                # (`Strong backend fundamentals: PostgreSQL, async workflows`).
                # A name as header stays on its items (`Palo Alto Networks: NGFW`).
                if not any(named):
                    return [clean(f"{pre} ({rest.strip(' .;')})")]
                lead_ok = False
                frame = list(TRIGGER_RE.finditer(head + " "))
                head = (head + " ")[: frame[-1].end()] if frame else ""
            elif examples and (not any(named) or (word == "including" and not all(named))) \
                    and (word or _nr._name_runs(_unmasked(pre))) and word not in ("i.e.", "ie"):
                if PLACEHOLDER_RE.search(pre):
                    # `Solid cloud experience (AWS or Azure), including managed
                    # services`: what is included is implied, the bracket split as usual
                    return _split_list(pre)
                return [clean(f"{pre} ({rest.strip(' .;')})")]
        if lead_ok:
            lead = [pre]
    else:
        matches = [x for x in TRIGGER_RE.finditer(s) if not (config.SPLIT_REPAIRS and _quantity_prep(s, x))]
        if matches:
            head, rest = s[: matches[-1].end()], s[matches[-1].end():]

    if CORREL_LEAD_RE.match(rest.strip()):
        # `both written and spoken` is one ask, but `both Windows and Linux OS`
        # names two systems: when every item is a name, `both` only stresses the
        # list (rules 0.3.0).
        plain = CORREL_LEAD_RE.sub("", rest.strip())
        if not (config.SPLIT_REPAIRS and len(_cut(plain)) > 1
                and all(i[:1].isupper() or i[:1].isdigit() for i in _cut(plain))):
            return [s]
        rest = plain
        s = clean(f"{head} {plain}") if head else plain

    if config.SPLIT_REPAIRS:
        m = _AS_ROLE_RE.search(s)
        if m and _ROLE_END_RE.search(s[m.end():]) and SPLIT_RE.search(s[m.end():]):
            # `2+ years of experience as a Machine Learning or Software engineer`:
            # roles in alternative, any one will do — one requirement, by the
            # convention for equivalent alternatives (rules 0.3.0). Unless they
            # are different roles (rules 0.4.6, 2026-11-18): `as a Data Engineer
            # or Data Scientist` is two requirements.
            alts = role_alternatives(s[m.end():])
            if len(alts) > 1 and len({_role_noun(a) for a in alts}) > 1:
                prefix = re.sub(r"\s+an?\s*$", " ", s[:m.end()])
                return [clean(f"{prefix}{a}") for a in alts]
            return _one(s)
        if _CANDIDATE_RE.match(s) and re.search(r"\s+or\s+an?\s+", s, re.I):
            # `Are a student in your final year or a young professional with ...`:
            # two descriptions of who may apply, either will do.
            return _one(s)

    items = _cut(rest)
    if config.SPLIT_REPAIRS and head.strip():
        merged = _merge_purposes(items)
        if merged != items:
            heads = _head_alternatives(head.strip())
            out = lead + [clean(f"{h} {i}") for h in heads for i in merged]
            return _one(out[0]) if len(out) == 1 else out
    if config.SPLIT_REPAIRS:
        # STOP_RE drops `equivalent experience` as filler, but it is an
        # alternative route into the job, and without it the ask is stricter
        # than the employer wrote: `Bachelor's degree or equivalent experience`
        # is not `Bachelor's degree`. Keep such an item whole.
        dropped = [clean(LEAD_CONJ_RE.sub("", clean(p))) for p in SPLIT_RE.split(rest)]
        if any(p and p not in items and _ALT_PATH_RE.search(p) for p in dropped):
            return [s]
    if config.SPLIT_REPAIRS and len(items) == 1 \
            and len([p for p in SPLIT_RE.split(rest) if p.strip()]) > 1:
        # `Strong experience with React or similar frameworks`: dropping the
        # filler leaves one item, which is a requirement in its own right, not
        # a reason to keep the filler. Without this the segment fell back to
        # whole, `or similar` and all. With no head the item already carries
        # its own (`Abgeschlossenes Studium der Informatik oder vergleichbare`).
        # One head per alternative it offers: `Bachelor's or Master's degree in
        # IT studies or related field` is two degrees once the filler is gone.
        heads = _head_alternatives(head.strip()) if head.strip() else [""]
        return lead + [clean(f"{h} {items[0]}") for h in heads]
    resolved = _resolve_elision(items) if items else items
    if resolved is None:
        return [s]
    items = resolved
    if config.SPLIT_REPAIRS and _activity_run(items):
        return [s]
    if config.SPLIT_REPAIRS:
        merged = _merge_verb_runs(items)
        if len(merged) == 1 < len(items):
            return [s]
        if merged != items:
            # The merged run is long, so the list test would reject it and
            # leave `building and maintaining X and Y` whole; the objects are
            # already distributed, so only the head is left to add.
            heads = _head_alternatives(head.strip()) if head.strip() else [""]
            return lead + [clean(f"{h} {i}") for h in heads for i in merged]
    if _use_pos() and len(_head_alternatives(head.strip()) if head.strip() else [""]) == 1:
        tailed = _shared_tail(head.strip(), items, bool(_OR_RE.search(rest)))
        if tailed is ONE_REQUIREMENT:
            return [s]
        if tailed:
            return lead + tailed

    if _is_list(items):
        head = head.strip()
        if len(head) > config.MAX_HEAD_CHARS or CORREL_TAIL_RE.search(head):
            return [s]
        # A run of modifiers shares the noun at its end rather than a head.
        if config.DISTRIBUTE_SHARED_TAIL and _is_modifier_run(items):
            return lead + _distribute_shared_tail(items)
        if not head:
            # No trigger word, so the head is inside the first item rather than
            # in front of the list: `Previous work experience under KPIs and
            # deadlines` has to be distributed from within, not prefixed.
            return lead + _distribute_shared_head(items)
        # One head per alternative it offers, each distributed over every item.
        if _use_pos() and SALES_PATTERNS:
            return lead + [i if k and _owns_head(i) else clean(f"{h} {i}")
                           for h in _head_alternatives(head) for k, i in enumerate(items)]
        return lead + [clean(f"{h} {i}") for h in _head_alternatives(head) for i in items]

    # No usable head + list reading. Fall back to reading the whole clause as a
    # coordinated list — `Sales experience and comfort with targeting new
    # business` is two requirements, but a late preposition inside the second
    # one used to capture the head and suppress the split entirely.
    bare = _cut(s)
    resolved = _resolve_elision(bare) if bare else bare
    if config.SPLIT_REPAIRS and resolved and _activity_run(resolved):
        return [s]
    if config.SPLIT_REPAIRS and resolved:
        merged = _merge_verb_runs(resolved)
        if len(merged) == 1 < len(resolved):
            return [s]
        if merged != resolved:
            return _distribute_shared_head(merged)
    if _use_pos() and resolved:
        tailed = _shared_tail("", resolved, bool(_OR_RE.search(s)))
        if tailed is ONE_REQUIREMENT:
            return [s]
        if tailed:
            return tailed
    if config.SPLIT_REPAIRS and resolved and len(resolved) > 1 and all(_trait(i) for i in resolved):
        # `Reliable, proactive, and self-motivated`: adjectives with no noun
        # after them describe the person, each a requirement. Before a noun they
        # share it and stay one (`Structured and project-based work`, convention
        # of 2026-10-30), which `_is_modifier_run` keeps. Rules 0.3.0.
        return resolved
    if resolved is not None and _is_list(resolved):
        return _distribute_shared_head(resolved)
    if config.SPLIT_REPAIRS:
        clauses = _split_ability(s) or _split_clauses(s)
        if clauses:
            return clauses
    return [s]


_OR_RE = re.compile(r"\s(?:or|and/or)\s", re.I)
_GERUND_CONJ_RE = re.compile(r"\s(?:and|or|as well as)\s+", re.I)


def _split_gerund_clauses(s: str) -> list[str] | None:
    """P15: `<head> <gerund> <object> and <gerund> <object>` -> two, head shared.

    `Experience designing REST APIs and building data pipelines`, `Strong
    experience developing customer relationships and managing tenders`,
    `Demonstrated success in building sales strategies and consistently
    meeting or exceeding revenue objectives`: two activities, each with its own
    object, under one head. Split at the first conjunction followed by a gerund
    (an adverb may come between), and the head before the first gerund goes onto
    the second. Verbs that SHARE an object stay one (`building and maintaining
    CI/CD pipelines`, decided 2026-10-29): the left side must not end on its
    gerund. Each side is then split as usual. No commas: in a list
    (`Clear communication skills, including leading incidents and writing
    postmortems`) the gerunds are its members, and the list rules decide.
    """
    if "," in s:
        return None
    for m in _GERUND_CONJ_RE.finditer(s):
        right = s[m.end():].split()
        k = 1 if len(right) > 2 and pos.tag(right[0])[0] == "ADV" else 0
        if len(right) < k + 2 or pos.tag(right[k])[1] != "VBG" or not _verb(right[k]):
            continue
        left = s[: m.start()].split()
        gers = [i for i, w in enumerate(left) if i and pos.tag(w)[1] == "VBG" and _verb(w)]
        if not gers or gers[0] == len(left) - 1 or gers[-1] == len(left) - 1:
            return None
        head = " ".join(left[: gers[0]])
        return _split_list(" ".join(left)) + _split_list(clean(f"{head} {' '.join(right)}"))
    return None


# Words that open a requirement of their own. Used only to decide that the
# right side of a single conjunction is a second requirement, never to split.
_OPENER_RE = re.compile(
    r"^(?:(?:the|an?)\s+)?(?:\d|ability|able|experience|knowledge|understanding|"
    r"familiarity|proficiency|expertise|background|degree|bachelor|master|phd|msc|bsc|"
    r"diploma|certification|certified|fluency|fluent|willingness|readiness|passion|interest|"
    r"strong|excellent|good|very|solid|proven|demonstrated|demonstrable|deep|hands-on|"
    r"practical|prior|previous|relevant|track record|at least|minimum|proficient|"
    r"experienced|comfortable|capacity|commitment|eagerness|desire|motivation|exposure)\b",
    re.I)


def _opens_requirement(right: str) -> bool:
    """Does the right side of a single conjunction start a requirement of its own?

    A list of opening words (`_OPENER_RE`), also with the tagger on. Tried
    2026-10-30: replacing it with a shape — any noun phrase of 3+ words — split
    inside noun phrases (`communication and interpersonal skills`, `the
    architecture and integration of`) on most of the 157 items it changed. One
    conjunction does not say where a requirement starts; the opener words do.
    """
    return bool(_OPENER_RE.match(right))


def _split_clauses(s: str) -> list[str] | None:
    """Two complete requirements joined by one conjunction.

    `A degree in computer science or 5+ years of experience in professional
    web development` and `Excellent problem-solving skills and the ability to
    work in a fast-paced environment` are two requirements each — the guide's
    `Sales experience and comfort with targeting new business` — but both
    sides are too long for the list test, so they stayed whole (the largest
    sub-class of `New project/unsplit_compounds.py` U6, ~960 occurrences).

    Deliberately narrow: no comma, exactly one top-level conjunction, and the
    right side must OPEN like a requirement. `Change management and
    implementation of new working methods` does not, and stays whole.
    """
    masked = PAREN_RE.sub(lambda m: "_" * len(m.group(0)), s)
    if "," in masked:
        return None
    conj = list(re.finditer(r"\s(?:and/or|and|or|as well as)\s", masked, re.I))
    if len(conj) != 1:
        return None
    left, right = clean(s[: conj[0].start()]), clean(s[conj[0].end():])
    if len(left.split()) < 2 or len(right.split()) < 2 or not _opens_requirement(right):
        return None
    last = left.split()[-1]
    # `in a clear and concise manner`, `across technical and business teams`
    if _adjectival(last) and not _nominal_ing(last) or _GOVERNS_END_RE.search(left + " "):
        return None
    # `A good working knowledge and experience of security risk analysis`:
    # the left side is a relational noun waiting for the complement on the
    # right, so the two share it — the bare-head defect of `flag_bare_head`.
    if re.sub(r"\W", "", last).lower() in _RELATIONAL_NOUNS:
        return None
    return [left, right]


_RELATIONAL_NOUNS = {
    "knowledge", "experience", "experiences", "understanding", "expertise", "familiarity",
    "proficiency", "exposure", "background", "skills", "competence", "competencies",
    "command", "mastery", "awareness", "know-how", "knowhow", "insight", "insights",
}


_ABILITY_RE = re.compile(
    r"^(?P<head>(?:[\w-]+\s+){0,2}?(?:ability|able|capacity|capability|willingness|"
    r"readiness|eagerness)\s+to)\s+(?P<left>.+?)\s+(?:and|or)\s+(?P<right>.+)$", re.I)
_VERBS = {
    "work", "manage", "communicate", "translate", "drive", "build", "lead", "deliver", "learn",
    "adapt", "explain", "collaborate", "influence", "prioritize", "prioritise", "handle",
    "solve", "think", "take", "make", "engage", "present", "write", "develop", "design",
    "travel", "identify", "analyze", "analyse", "understand", "operate", "navigate",
    "balance", "coordinate", "organize", "organise", "plan", "meet", "deal", "juggle",
    "multitask", "thrive", "interact", "support", "mentor", "coach", "own", "challenge",
    "simplify", "articulate", "negotiate", "create", "turn", "bring", "convey", "partner",
    "apply", "perform", "execute", "maintain", "evaluate", "assess", "research", "review",
    "test", "document", "implement", "define", "shape", "set", "use", "combine", "connect",
    "motivate", "inspire", "prepare", "produce", "provide", "ensure", "keep", "stay",
    "remain", "act", "respond", "resolve", "troubleshoot", "debug", "integrate", "scale",
    "deploy", "monitor", "report", "read", "speak", "grasp", "pick", "foster", "align",
    "facilitate", "translate", "contribute", "drive", "hit", "achieve", "exceed", "close",
    "win", "sell", "grow", "build", "develop", "establish", "maintain", "pursue",
}


def _ability_verb(word: str) -> bool:
    """Does the right side of `ability to L and R` open with a verb? The list,
    plus the tagger's base verbs when it is on (P4), so `federate`, `re-seat`
    are verbs too."""
    if word.lower() in _VERBS:
        return True
    return _use_pos() and pos.tag(word)[1] == "VB"


def _split_ability(s: str) -> list[str] | None:
    """`Ability to manage competing priorities and drive consensus` -> two.

    Two verbs with their OWN objects are two demands, and the head carries
    over: `Ability to drive consensus`. Two verbs SHARING one object stay one,
    as decided 2026-10-29 for `building and maintaining CI/CD pipelines`:
    `Demonstrated ability to shape and communicate architectural strategies`
    has a bare verb on the left, so it is not split.
    """
    if "," in PAREN_RE.sub("", s):
        return None
    m = _ABILITY_RE.match(s)
    if not m:
        return None
    left, right = m.group("left").split(), m.group("right").split()
    if len(left) < 2 or len(right) < 2 or not _ability_verb(right[0]):
        return None
    # `to identify and prevent issues`: the left side ends in its own bare
    # infinitive, which shares the object on the right.
    if len(left) >= 2 and left[-2].lower() == "to" or _adjectival(left[-1]) and not _nominal_ing(left[-1]):
        return None
    head = m.group("head")
    return [clean(f"{head} {' '.join(left)}"), clean(f"{head} {' '.join(right)}")]


# A bracket holding a LIST is a list; a bracket holding one example is not.
#
# `PAREN_RE` masks brackets so their commas cannot drive a split, and the
# labelling guide agrees for the case it names — `version control (such as Git)`
# is one requirement. But the labels expand a bracket that contains several
# items, distributing the head: `plateforme d'intégration (Boomi, MuleSoft,
# Talend, etc.)` is four requirements, not one. Masking made that unreachable,
# and parenthetical lists were the worst-recovering shape in the sample at 8%
# against 55% overall.
#
# The distinction is countable, so it is applied by counting rather than by
# guessing: two or more comma-separated items inside the bracket is a list.
PAREN_LIST_RE = re.compile(r"\(([^()]{2,200})\)")
# A whole named world whose bracket describes its parts (see `_atomise_once`).
ECOSYSTEM_RE = re.compile(r"\b(?:ecosystems?|landscapes?|universe|world|[oö]kosystem|[ée]cosyst[eè]me)\s*$",
                          re.I)

# Generic nouns a bracket typically exemplifies. Kept separate from
# GENERIC_TAIL_RE on purpose: widening that one changed head trimming on every
# other path and cost 8 points of overall recovery, so this list applies only
# where a bracketed list is being expanded.
#
# ⚠️ Found 2026-10-29: the committed pattern opened with a literal BACKSPACE
# (0x08), not `\b` — the heredoc trap recorded in CLAUDE.md. It therefore
# never matched, and the generic-noun drop it implements has been dead code
# in every published run. Kept byte-identical here, now spelled `\x08` so it
# is visible, so Week 1-4 figures still reproduce; the working pattern is
# PAREN_GENERIC_RE_V2, used under config.SPLIT_REPAIRS.
PAREN_GENERIC_RE = re.compile(
    "\x08" r"(?:platforms?|systems?|concepts?|solutions?|products?|providers?|"
    r"vendors?|suites?|stacks?|frameworks?|plateformes?|syst[eè]mes?|"
    r"sprache|sprachen|werkzeuge)\s*$", re.I)
PAREN_GENERIC_RE_V2 = re.compile(PAREN_GENERIC_RE.pattern.replace("\x08", r"\b", 1), re.I)
_PAREN_LEAD_RE = re.compile(
    r"^(?:e\.?g\.?|i\.?e\.?|z\.?b\.?|such as|like|etwa|ex\.?|par exemple|"
    r"come|p\.?ej\.?|bijv\.?)[\s:,]*", re.I)
# The repaired form (config.SPLIT_REPAIRS). Two defects in the one above, both
# found by grouping damaged splits over the corpus: `ex\.?` makes the dot
# optional, so `(Excel, Word, PowerPoint)` lost its first two letters and
# shipped `Maîtrise du pack office cel`; and `z\.?b\.?` allows no space, so the
# German house style `z. B.` was never recognised and became an item —
# `Erste Praxiserfahrung in z. B. Go`. 136 unique items in that class alone.
_PAREN_LEAD_RE_V2 = re.compile(
    r"^(?:e\.?\s?g\.?|i\.?\s?e\.?|z\.?\s?b\.?|bspw\.?|zum beispiel|such as|like|etwa|"
    r"ex\.|par ex\.|par exemple|come|p\.?\s?ej\.?|bijv\.?|"
    # Adverbs that open a bracket and name nothing: `(particularly python and
    # R)` became `Experience with particularly python`.
    r"particularly|especially|notably|preferably|ideally|insbesondere|vor allem|"
    r"vorzugsweise|idealerweise|bevorzugt|notamment|de pr[eé]f[eé]rence|id[eé]alement|"
    r"in particolare|preferibilmente|idealmente|bij voorkeur|bijvoorbeeld)(?!\w)[\s:,]*", re.I)


def _paren_items(inner: str) -> list[str]:
    """The bracket's contents as list items, or [] if it is not a list."""
    if config.SPLIT_REPAIRS:
        # Cut on conjunctions as well as commas, so `(z. B. Go, PHP oder
        # Python)` is three items and `(Palo Alto, Fortinet, or similar)` does
        # not emit `or similar` as a fourth.
        inner = _PAREN_LEAD_RE_V2.sub("", inner).strip()
        if "," not in inner and " / " in inner:
            # `(Ruby on Rails / React / Typescript)`: a spaced slash separates
            # names as a comma does; `CI/CD` has no spaces and stays one
            inner = inner.replace(" / ", ", ")
        items = _cut(inner)
        # Without a comma, a conjunction joins modifiers as often as items:
        # `(spoken and written)` qualifies one skill, `(GitHub or GitLab)` names
        # two tools. Only names — capitalised or numeric — are split then.
        if "," not in inner and not all(i[:1].isupper() or i[:1].isdigit() for i in items):
            return []
        if len(items) < 2 or any(len(i.split()) > config.MAX_ITEM_WORDS for i in items):
            return []
        return items
    inner = _PAREN_LEAD_RE.sub("", inner).strip()
    items = [clean(p) for p in inner.split(",")]
    items = [i for i in items if i and not STOP_RE.match(i)]
    if len(items) < 2:
        return []
    # A bracket of clauses is prose, not a list — the same shape test used for
    # comma runs elsewhere.
    if any(len(i.split()) > config.MAX_ITEM_WORDS for i in items):
        return []
    return items


_PLATFORM_RE = re.compile(r"\b(?:AWS|Azure|GCP|Google\s+Cloud|Salesforce)\b")
_INCLUDING_RE = re.compile(r"(?:including|includes|such as|e\.g\.|like)\b", re.I)


def _examples_named(before: str, after: str, items: list[str]) -> str:
    """`all` when every bracket item is a name, `none` when none is, else ``.

    Only where the bracket plainly exemplifies the phrase in front of it: a
    list or a verb phrase in front, an introducer, or a governor after the
    bracket keep the older path (`_repair_head` explains each).
    """
    from . import normalise_req as _nr     # it imports this module
    # what `including` adds after the bracket is implied (the user's call of
    # 2026-11-17); any other governor there means the bracket qualifies the head
    governed = _GOVERNOR_RE.match(after + " ") and not _INCLUDING_RE.match(after)
    if INTRODUCER_RE_V2.search(before) or governed:
        return ""
    frame = [f for f in TRIGGER_RE.finditer(before + " ") if f.group().strip().lower() != "an"]
    tail = before[frame[-1].end():] if frame else before
    words = tail.split()
    joined = re.search(rf"\s(?:{_CONJ})\s", f" {tail} ", re.I)
    # `concepts of virtualization and containerization (VMware, Docker)`: two
    # categories joined by `and`, no names, are the category the names exemplify
    # (review of batch 3); a comma or a name there is a real list
    joined = joined and _nr._name_runs(tail)
    all_named = bool(items) and all(_nr._name_runs(i) for i in items)
    if "," in tail or joined or (
            len(words) >= 2 and re.fullmatch(r"\w{3,}ing", words[0], re.I) and not all_named):
        return "list"
    named = [bool(_nr._name_runs(i)) for i in items]
    return "all" if all(named) else "none" if not any(named) else ""


def _split_paren_list(segment: str) -> list[str] | None:
    """Expand a multi-item bracket over the head that governs it.

    Returns None when the segment holds no such bracket, so the caller falls
    through to the ordinary masking path and single-example brackets keep their
    existing, correct behaviour.
    """
    m = PAREN_LIST_RE.search(segment)
    if not m:
        return None
    items = _paren_items(m.group(1))
    if not items:
        return None

    before = clean(segment[: m.start()])
    after = clean(segment[m.end():])
    if not before or len(before) > config.MAX_HEAD_CHARS * 2:
        return None

    if config.SPLIT_REPAIRS and not _DEGREE_HEAD_RE.search(before):
        named = _examples_named(before, after, items)
        if named == "list":
            # `Knowledge of data protection laws, healthcare IT standards
            # (e.g., HIPAA)`: the bracket belongs to the list's last item, and
            # the list is split first (the masked path, then this on each piece)
            return None
        if named == "none":
            # The user's call of 2026-11-17: examples that are common nouns
            # belong to their category, one requirement (`soft skills
            # (communication, teamwork)`), the bracket kept for `extra`
            return None
        if named == "all":
            # Named examples ARE the requirements and the category goes:
            # `relational databases (PostgreSQL, MySQL)` is PostgreSQL and
            # MySQL; `Diagnosis (KwP, UDS)` is KwP and UDS. The frame stays up
            # to its preposition (`Experience with`); a name inside the
            # category is a requirement too (`Linux environments (RHEL)`).
            frame = [f for f in TRIGGER_RE.finditer(before + " ") if f.group().strip().lower() != "an"]
            head = clean(before[: frame[-1].end()]) if frame else ""
            from . import normalise_req as _nr     # it imports this module
            tail = before[len(head):]
            # a lone common word is the category (`Diagnosis (KwP, UDS)`), not a name
            keep = [r for r in _nr._name_runs(tail) if len(r.split()) > 1 or _nr._strong_name(r)
                    or len(tail.split()) > 1]
            out = [before] if keep else []
            out += [clean(f"{h} {i}") for h in _head_alternatives(head) for i in items] if head \
                else list(items)
            if not _INCLUDING_RE.match(after):
                # what `including` adds is implied by what came before it
                out.extend(_paren_remainder(before, after))
            return [a for a in out if _keep_atom(a)] or None

    # The head is the phrase before the bracket, trimmed of the generic noun the
    # bracket exemplifies — `... at least one integration platform (Boomi, ...)`
    # is about Boomi, not about the word `platform`.
    # A bracket always exemplifies the phrase in front of it, so the generic
    # noun it stands for is dropped — and a long head is trimmed regardless,
    # since `... at least one integration platform` names nothing by itself.
    # Drop only the generic noun the bracket exemplifies, not the whole
    # prepositional chain leading to it. `Expertise avancée dans l'utilisation
    # d'au moins une plateforme d'intégration (Boomi, ...)` is about
    # `l'utilisation de Boomi`; trimming back to the FIRST preposition gave
    # `Expertise avancée dans Boomi` and lost the part carrying the meaning.
    generic_re = PAREN_GENERIC_RE_V2 if config.SPLIT_REPAIRS else PAREN_GENERIC_RE
    m_generic = GENERIC_TAIL_RE.search(before) or generic_re.search(before)
    if m_generic:
        kept = before[: m_generic.start()]
        # step back over the quantifier or article that introduced that noun
        kept = re.sub(r"(?:\b(?:at least|au moins|mindestens|one|a|an|une|un|"
                      r"einer|eine|einem)\b\s*|\bd\s+)+$", "", kept, flags=re.I)
        head = clean(kept) or _trim_head(before)
    elif len(before.split()) > 4:
        head = _trim_head(before)
    else:
        head = before

    if config.SPLIT_REPAIRS:
        head = _repair_head(before, head, after)
        if head is None:
            return None
    heads = _head_alternatives(head)

    out = [clean(f"{h} {i}") for h in heads for i in items]
    # The phrase before the bracket is usually a requirement in its own right,
    # exactly as with an unbracketed introducer.
    keep_before = not GENERIC_TAIL_RE.search(before)
    if config.SPLIT_REPAIRS and keep_before and LEAD_CATEGORY_RE.search(before):
        # `integration platforms (Boomi, MuleSoft, Talend)` as `frameworks like
        # Spark, ...` in `_split_list`: the category the names stand for is not
        # a requirement beside them (rules 0.3.0).
        keep_before = False
    if config.SPLIT_REPAIRS and not keep_before:
        # Dropping the generic noun phrase is the labelled convention, but a
        # name inside it is a requirement: `Proficiency in Linux environments
        # (RHEL, CoreOS)` lost `Linux`.
        tail = before[len(head.rstrip()):]
        keep_before = any(w[:1].isupper() for w in tail.split())
    if keep_before and len(before.split()) > 1:
        out.insert(0, before)
    if config.SPLIT_REPAIRS:
        out.extend(_paren_remainder(before, after))
    elif after and len(after.split()) > 2:
        out.extend(_atomise_once(after))
    return [a for a in out if _keep_atom(a)] or None


def _repair_head(before: str, head: str, after: str) -> str | None:
    """The head a bracket list distributes over, or None to abstain.

    Every rule here is one damage class from `New project/split_damage.py`,
    grouped over the whole export and checked by reading the changed items.
    """
    # `... protocols and standards: OData (v2 and v4), REST` is a list led by
    # the colon, and the bracket qualifies one of its items. Taking the bracket
    # as the list emitted `Proficiency with v2`.
    if INTRODUCER_RE_V2.search(before):
        return None
    # `Abgeschlossenes Studium (Bachelor oder Master) in Informatik`: the field
    # comes AFTER the bracket, so the bracket qualifies the head rather than
    # listing what it governs. Expanding it gave `Studium im Bereich Bachelor`.
    if _GOVERNOR_RE.match(after + " "):
        return None
    # `in at least one major language (Java, ...)` must cut at `in`, not at
    # the `at` of the quantifier: that gave `skills in at Java`.
    head = clean(_QUANTIFIER_TAIL_RE.sub("", head)) or head
    if _GOVERNS_END_RE.search(head + " "):
        return head

    # The head must end in the word that governs the items, or each item is
    # glued onto a noun: `Familiarity with IT infrastructure servers`. The
    # largest damage class in the corpus (1,552 unique items) is exactly this —
    # a generic noun the lists above do not name (`infrastructure`,
    # `management`, `OOP`). Cut back to the LAST governor, which keeps the
    # prepositional chain the comment in `_split_paren_list` protects.
    # PREP_RE holds the German `an`, which is also the English article:
    # `Experience with an identity provider (Okta, ...)` cut at `an` and gave
    # `Experience with an Okta`.
    preps = [m for m in _GOVERNOR_RE.finditer(head) if m.group().strip().lower() != "an"]
    if preps:
        dropped = head[preps[-1].end():].split()
        # The cut may only remove the noun phrase the bracket exemplifies.
        # A list in there is content: `Hands-on experience with Docker,
        # Kubernetes, and CI/CD tools (Git, GitLab, Nexus)` lost Docker and
        # Kubernetes. A verb phrase is too: `A track record of building DevOps
        # pipelines (GitHub or GitLab)` is not `A track record of GitHub`. A
        # one-word gerund (`Proficiency in scripting (Bash, Python)`) is a
        # field name and is cut as usual. Either way, abstain.
        rest = " ".join(dropped)
        has_list = "," in rest or re.search(rf"\s(?:{_CONJ})\s", f" {rest} ", re.I)
        starts_verb = len(dropped) >= 2 and re.fullmatch(r"\w{3,}ing", dropped[0], re.I)
        if has_list or starts_verb:
            return None
        return clean(head[: preps[-1].end()])

    # A degree is the one head whose connector is fixed by the language, so it
    # can be supplied rather than abstained on: `Master's degree (business,
    # engineering)` is `Master's degree in business`, as the guide's own
    # examples write it. Only for the language the connector belongs to —
    # `diplôme Bac ou Bachelor` took an English `in`.
    degree = _DEGREE_HEAD_RE.search(head)
    if degree:
        from . import language
        lang = language.detect(head)[0]
        if degree.group("en") and lang in (None, "English"):
            return clean(f"{head} in")
        if not degree.group("en") and lang in (None, "Deutsch"):
            return clean(f"{head} im Bereich")
    # No governor at all (`Strong testing habits (JUnit, ...)`, `STEM Degree
    # (Science, ...)`): there is no head to distribute. Abstain, and the
    # bracket stays attached to a whole requirement.
    return None


_QUANTIFIER_TAIL_RE = re.compile(
    r"\s(?:at least|au moins|mindestens|almeno|minstens|minimaal|al menos)\b.*$", re.I)

_DEGREE_HEAD_RE = re.compile(
    r"(?:(?P<en>\b(?:degree|diploma|bachelor'?s?|master'?s?|msc|bsc|phd|mba))|"
    r"(?:studium|hochschulstudium|ausbildung|abschluss|hochschulabschluss))\s*$", re.I)

# What a remainder says about the requirement rather than adding one: `(...)
# appréciées`, `... are a plus`. Distributed, it shipped `Connaissances des
# appréciées`.
_EVALUATIVE_RE = re.compile(
    r"^(?:is |are |would be |will be |sont |est |ist |sind |è |sono |zijn |is een )?"
    r"(?:an? (?:big |strong |real )?(?:plus|advantage|asset|bonus)|preferred|desirable|"
    r"welcome|nice to have|highly valued|appr[eé]ci[eé]e?s?|souhait[eé]e?s?|"
    r"(?:un |une )?(?:plus|atout)|von vorteil|w[uü]nschenswert|ein plus|"
    r"gradit[oaie]|preferibile|un plus|een pr[eé]|pluspunt|meegenomen)\b", re.I)

# Filler a remainder can consist of: `... or equivalent experience`, `oder
# vergleichbare Ausbildung`. Dropped, as the guide drops `or equivalent`.
#
# Whole words, inflections spelled out. A bare stem `similar` matched
# `similarity` and silently dropped `similarity search at scale` from
# `Solid understanding of indexing strategies and similarity search at scale`.
_FILLER_LEAD_RE = re.compile(
    r"^(?:an?\s+|the\s+|eine?[nmrs]?\s+|une?\s+)?(?:equivalent|similar|comparable|related|"
    r"[eé]quivalent(?:e|es|s)?|vergleichbar(?:e|en|er|es|em)?|gleichwertig(?:e|en|er|es|em)?|"
    r"[aä]hnlich(?:e|en|er|es|em)?|gelijkwaardig(?:e)?|vergelijkbar(?:e)?|"
    r"equivalent[ei]|simil[ie]|comparabil[ei]|affin[ei])(?!\w)", re.I)

# A closing `or equivalent ...` alternative, outside any bracket.
#
# Dutch `of` ("or") is only accepted before a Dutch filler word. As a general
# conjunction it is also the English preposition, and `5-10 years of relevant
# work experience` was cut into `5-10 years` + `relevant work experience`.
_ALT_TAIL_RE = re.compile(
    r"[,;]?\s+(?:(?:or|oder|ou|o|eller|lub|bzw\.)\s+"
    r"(?P<alt>(?:(?:an?|the|eine?[nmrs]?|une?)\s+)?"
    r"(?:equivalent|similar|comparable|[eé]quivalente?s?|vergleichbar\w*|"
    r"gleichwertig\w*|[aä]hnlich\w*|equivalent[ei]|comparabil[ei])\b[^,;()]*)|"
    r"of\s+(?P<alt_nl>(?:een\s+)?(?:gelijkwaardig|vergelijkbar)\w*\b[^,;()]*))[.]?$", re.I)

_EQUIV_DEGREE_RE = re.compile(
    r"^(?:(?:an?|the)\s+)?(?:equivalent|similar|comparable)"
    r"(?:\s+(?:relevant|technical|academic|professional|university|scientific|higher))*"
    r"\s+(?:qualifications?|degrees?|diplomas?|education|studies)$", re.I)

# An alternative route into the job, which is a requirement, not filler.
_ALT_PATH_RE = re.compile(
    r"\b(?:experience|qualifications?|background|education|training|degrees?|diploma|"
    r"certifications?|level|erfahrung|berufserfahrung|qualifikation(?:en)?|ausbildung|"
    r"abschluss|studium|exp[eé]rience|formation|dipl[oô]me|niveau|esperienza|titolo|"
    r"ervaring|opleiding|experiencia|titulaci[oó]n)\b", re.I)

# The categories a filler alternative points at.
_GENERIC_CATEGORY_RE = re.compile(
    r"^(?:tools?|technolog(?:y|ies)|frameworks?|libraries|languages?|platforms?|"
    r"solutions?|systems?|products?|software|stacks?|services?|environments?|fields?|"
    r"areas?|disciplines?|subjects?|domains?|roles?|positions?|functions?|industr(?:y|ies)|"
    r"sectors?|compan(?:y|ies)|organi[sz]ations?|institutions?|markets?|providers?|"
    r"vendors?|suites?|applications?|methodolog(?:y|ies)|methods?|"
    r"fachrichtung(?:en)?|studieng[aä]ng(?:e)?|studienrichtung(?:en)?|bereich(?:e|en)?|"
    r"rolle|position|branche(?:n)?|umfeld|technologien|plattformen|l[oö]sungen|systeme|"
    r"outils|technologies|domaines?|plateformes?|solutions|strumenti|tecnologie|"
    r"settori?|ambiti?)[.,;]?$", re.I)


def _paren_remainder(before: str, after: str) -> list[str]:
    """The requirements in the text after a bracket list.

    Three defects of the original handling, each a damage class in the corpus.
    The conjunction that joined the remainder was kept (`and CI/CD pipelines`,
    321 items). A short remainder was dropped outright, so `Experience with
    relational databases (PostgreSQL, MySQL) and SQL` silently lost `SQL`. And a
    bare noun phrase was emitted without the head it shares with the bracket:
    `or Android (Java, Kotlin)` is `Good knowledge of Android`, not `or Android`.
    """
    rest = clean(LEAD_CONJ_RE.sub("", clean(after)))
    if not rest or STOP_RE.match(rest) or _is_filler_item(rest) or _EVALUATIVE_RE.match(rest):
        return []
    outside = PAREN_RE.sub("", rest)
    own_head = _GOVERNOR_RE.search(" ".join(outside.split()[:2]) + " ")
    preps = list(_GOVERNOR_RE.finditer(before))
    # Distribute only onto a short bare phrase that carries no head of its own.
    # `and understanding of how they affect system design` already has one;
    # `oder die Bereitschaft, sich ... einzuarbeiten` is a clause.
    if preps and not own_head and "," not in outside and len(outside.split()) <= 6:
        rest = clean(f"{before[: preps[-1].end()]} {rest}")
    return _atomise_once(rest)


def _distribute_skill_tail(segment: str) -> list[str] | None:
    """`Strong organizational and management skills` -> two skills.

    Coordinated single words in front of `skills` name different skills, and
    the labels split them (`Proven analytical and communication skills` is
    two). Distinguished from the guide's `excellent written and verbal
    communication`, which stays one, by shape: there the last conjunct is
    `verbal communication`, two words, so the modifiers describe one skill.
    Here every conjunct is ONE word directly before the tail noun.
    """
    m = _SKILL_TAIL_RE.match(segment)
    if not m:
        return None
    mods = re.sub(r"[\s,]*(?:and/or|and|or|&)[\s,]*$", "", m.group("mods"), flags=re.I)
    words = re.split(r"\s*,\s*|\s+(?:and/or|and|or|&)\s+", mods.strip(" ,"), flags=re.I)
    words = [w for w in words if w] + [m.group("last")]
    # `written and verbal skills` are modes of one skill, as in the guide.
    if len(words) < 2 or all(w.lower() in _MODE_WORDS for w in words):
        return None
    # A conjunct that is a requirement by itself is not a skill name:
    # `Strong analytical mindset and problem-solving skills` is not
    # `analytical mindset skills`.
    if any(w.lower() in _STANDALONE_NOUNS for w in words):
        return None
    prefix = (m.group("prefix") or "").strip()
    # The prefix qualifies every skill, so it may only be an intensifier or a
    # language name (`Excellent English communication and reporting skills`).
    pw = prefix.split()
    if pw and not (all(p.lower() in _INTENSIFIERS for p in pw[:-1])
                   and (pw[-1].lower() in _INTENSIFIERS or pw[-1][:1].isupper())):
        return None
    rest = (m.group("rest") or "").strip(" .")
    return [clean(f"{prefix} {w} {m.group('tail')} {rest}") for w in words]


_LANGS = (
    "English|German|French|Dutch|Flemish|Italian|Spanish|Portuguese|Swedish|Danish|"
    "Norwegian|Finnish|Polish|Czech|Slovak|Hungarian|Romanian|Bulgarian|Greek|Turkish|"
    "Croatian|Serbian|Slovenian|Lithuanian|Latvian|Estonian|Russian|Ukrainian|Arabic|"
    "Hebrew|Chinese|Mandarin|Cantonese|Japanese|Korean|Hindi|Luxembourgish|Catalan|Basque")
_LANG_LIST_RE = re.compile(
    rf"^(?P<pre>.*?)(?:\b(?:both|either)\s+)?(?P<langs>\b(?:{_LANGS})\b"
    rf"(?:\s*,\s*\b(?:{_LANGS})\b)*\s*,?\s+(?:and/or|and|or|&|as well as)\s+\b(?:{_LANGS})\b)"
    rf"(?P<post>.*)$")


def _split_languages(segment: str) -> list[str] | None:
    """`Excellent written and spoken German and English skills` -> two.

    The guide's own rule — `fluent German and English` is TWO, because two
    languages are named — but the coordinated modes in front (`written and
    spoken`) made the list test read the whole item as one modifier run, so
    ~530 occurrences stayed whole. Each language takes everything around it:
    `Excellent written and spoken German skills`.
    """
    clauses = _language_clauses(segment)
    if clauses:
        return clauses
    m = _LANG_LIST_RE.match(segment)
    if not m:
        return None
    # Inside a bracket the languages qualify the requirement around them:
    # `Proficiency in English (German or French is an advantage)` became two
    # atoms that both say English.
    if any(p.start() <= m.start("langs") < p.end() for p in PAREN_RE.finditer(segment)):
        return None
    langs = re.findall(rf"\b(?:{_LANGS})\b", m.group("langs"))
    if len(langs) < 2:
        return None
    pre, post = m.group("pre"), m.group("post")
    combo = _LANG_COMBO_RE.match(pre) if config.SPLIT_REPAIRS else None
    if combo:
        # `Speak English fluently, in combination with Dutch or French`: the
        # first language is a requirement of its own, and the ones after the
        # connector are not asked the way the first is (rules 0.3.0).
        return [clean(combo.group("first"))] + langs
    return [clean(f"{pre}{lang}{post}") for lang in langs]


# A clause naming a language, then a connector that adds more languages.
_LANG_COMBO_RE = re.compile(
    rf"^(?P<first>.*\b(?:{_LANGS})\b.*?)\s*,?\s*(?:in combination with|combined with|together with|"
    r"along with|alongside|plus|as well as|and ideally|and preferably|and also)\s+$", re.I)
_LANG_PART_SEP = re.compile(r"\s*,\s*|\s+(?:and|as well as|&)\s+", re.I)


def _language_clauses(segment: str) -> list[str] | None:
    """`Very good knowledge of German and good knowledge of English` -> two.

    Each part is a requirement written in full, one language each, so the list
    test reads them as clauses and gives up (route `llm`). Only when EVERY part
    has two words or more and exactly one language, all different: `German
    and English` has a bare part, and `_LANG_LIST_RE` gives it its head.
    Rules 0.3.0, from the 2026-11-09 trial."""
    if not config.SPLIT_REPAIRS or "(" in segment:
        return None
    parts = [clean(p) for p in _LANG_PART_SEP.split(segment) if clean(p)]
    if len(parts) < 2 or any(len(p.split()) < 2 for p in parts):
        return None
    langs = [re.findall(rf"\b(?:{_LANGS})\b", p) for p in parts]
    if any(len(x) != 1 for x in langs) or len({x[0] for x in langs}) < len(parts):
        return None
    return parts


_MODE_WORDS = {"written", "verbal", "oral", "spoken", "reading", "writing", "speaking",
               "listening", "interpersonal"}
_STANDALONE_NOUNS = {"mindset", "attitude", "thinking", "approach", "judgment", "judgement",
                     "personality", "spirit", "drive", "attention", "eye", "sense", "focus",
                     "background", "experience", "knowledge", "understanding"}
_INTENSIFIERS = {"strong", "excellent", "good", "very", "proven", "solid", "great",
                 "outstanding", "exceptional", "superior", "advanced", "basic", "sound",
                 "effective", "demonstrated", "demonstrable", "high", "highly", "well-developed",
                 "exemplary", "superb", "first-class", "robust", "keen", "polished",
                 "decent", "fair", "adequate", "extensive", "deep", "relevant", "the", "good"}

_SKILL_TAIL_RE = re.compile(
    r"^(?P<prefix>(?:[\w-]+\s+){0,2}?)"
    r"(?P<mods>[\w-]+(?:\s*,\s*[\w-]+)*\s*,?\s+(?:and|or|&|and/or)\s+)"
    r"(?P<last>[\w-]+)\s+(?P<tail>skills|abilities|capabilities|competencies|competences)"
    r"(?P<rest>(?:\s+(?:in|for|with)\s+[^,;()]{1,40})?)\s*\.?$", re.I)


# Adverbs that ADD a requirement rather than narrow one: `Python, also Java`.
# A closed functional class, so a list is the right tool here.
_ADDITIVE_ADV = {"also", "additionally", "too", "further", "furthermore", "plus", "moreover",
                 "besides", "then", "as", "well", "not", "only", "very", "more", "most"}
_FIXED_QUALIFIER_RE = re.compile(r"\b(?:if|where|when|whenever)\s+(?:possible|applicable|relevant)\b", re.I)
_TOKEN_RE = re.compile(r"[\w'’+#./-]+|[,;()]")


def _qualifier(segment: str) -> tuple[str, str, str] | None:
    """PATTERNS.md P6: find the phrase that narrows the requirement before it.

    Returns ``(main, qualifier, kind)``. The shape, read off the tagger:

    * ``narrow`` — an adverb after a noun or a comma, followed by a
      preposition: `Expertise in Power BI, particularly in complex data
      modeling`, `insurance experience preferably in client management,
      consulting, or project management`. The adverb after a VERB is manner, not
      a qualifier (`communicate clearly with customers`), and an adverb followed
      by a bare noun phrase may add a requirement (`Fluent English, ideally
      German`), so both are left alone. So is `if possible ...`, a fixed phrase.
    * ``both`` — `both` / `either` + preposition after the requirement:
      `Excellent communicative skills, both in Dutch and English` is the skill in
      each language, two requirements, never `both in Dutch` as one.
    """
    toks = [(m.group(), m.start()) for m in _TOKEN_RE.finditer(segment)]
    depth = 0
    for k, (w, start) in enumerate(toks):
        if w == "(":
            depth += 1
        elif w == ")":
            depth = max(0, depth - 1)
        if depth or k < 2 or k + 1 >= len(toks):
            continue
        prev, nxt = toks[k - 1][0], toks[k + 1][0]
        if prev == "(" or nxt in (",", ";", "(", ")"):
            continue
        prev_ok = prev == "," or pos.tag(prev)[0] in ("NOUN", "PROPN")
        lw = w.lower()
        if lw in ("both", "either") and prev_ok and pos.tag(nxt)[0] == "ADP":
            return clean(segment[:start]), clean(segment[start + len(w):]), "both"
        # `e.g.` introduces examples (P5), not a narrowing.
        if lw in _ADDITIVE_ADV or "." in w or not prev_ok:
            continue
        if pos.tag(w)[0] == "ADV" and pos.tag(nxt)[0] == "ADP":
            return clean(segment[:start]), clean(segment[start:]), "narrow"
    m = _FIXED_QUALIFIER_RE.search(PAREN_RE.sub(lambda x: "_" * len(x.group()), segment))
    if m and m.start() > 0:
        return clean(segment[: m.start()]), clean(segment[m.start():]), "narrow"
    return None


def _split_qualified(segment: str) -> list[str] | None:
    """Split the requirement, never its qualifier (`_qualifier`)."""
    q = _qualifier(segment)
    if not q or len(q[0].split()) < 2:
        return None
    main, qual, kind = q
    if kind == "both":
        prep, _, rest = qual.partition(" ")
        items = _cut(rest)
        if len(items) < 2 or len(rest.split()) > 6:
            return None
        # `both in speech and writing` names modes of one skill (P2a), not two.
        if any(w.lower() in _MODE_WORDS | {"speech", "word", "words", "writing"}
               for i in items for w in i.split()):
            return None
        return [clean(f"{main} {prep} {i}") for i in items]
    atoms = _atomise_once(main) or [main]
    # The qualifier rejoins the last requirement as the employer wrote it,
    # with a comma only where there was one.
    sep = "," if segment[: segment.find(qual)].rstrip().endswith(",") else ""
    return atoms[:-1] + [clean(f"{atoms[-1]}{sep} {qual}")]


def _atomise_once(segment: str) -> list[str]:
    """One splitting pass over a segment."""
    # The degree routes first since rules 0.4.4: they fire only on a degree,
    # and the qualified split had taken `Good Bachelor's or Master's degree,
    # ideally with economic relevance` apart before them.
    if config.SPLIT_REPAIRS:
        degree = _degree_routes(segment)
        if degree:
            return degree
    if _use_pos():
        qualified = _split_qualified(segment)
        if qualified:
            return qualified
    if config.SPLIT_REPAIRS:
        tail = _distribute_skill_tail(segment)
        if tail:
            return tail
        langs = _split_languages(segment)
        if langs:
            # Each piece names one language now, so this cannot recurse again;
            # the rest of the item (`Python, SQL and fluent German`) still
            # needs its ordinary split.
            return [a for piece in langs for a in (_atomise_once(piece) or [piece])]
        # `... in Informatik, Data Science oder vergleichbare Qualifikation`:
        # the closing alternative is a route into the job, not filler, and the
        # labels keep it as a requirement of its own (`Vergleichbare
        # Qualifikation`) while splitting the rest. Detached before splitting,
        # so it is neither distributed over (`Studium in vergleichbare
        # Qualifikation`) nor dropped by STOP_RE.
        m = _ALT_TAIL_RE.search(segment)
        alt = m and (m.group("alt") or m.group("alt_nl"))
        main = clean(segment[: m.start()]) if m else ""
        if alt and main and _DEG_ANY_RE.search(main) and _EQUIV_DEGREE_RE.match(alt):
            # `Degree in X, Y, or equivalent technical qualification`: another
            # degree that would do as well, so the alternatives count once
            # (the user's convention of 2026-10-30). Kept, it was read as
            # `Degree (any field)`. An equivalent EXPERIENCE is a different
            # route and stays below. English only: the German labels keep
            # `vergleichbare Qualifikation`. Rules 0.4.1.
            return _atomise_once(main) or [main]
        if m and m.group("alt_nl") and main and not _ALT_PATH_RE.search(alt):
            # The Dutch `of gelijkwaardig` is `or equivalent`: filler, which no
            # split saw because `of` is not a conjunction elsewhere. Rules 0.4.1.
            segment = main
        elif alt and _ALT_PATH_RE.search(alt) and main:
            # The alternative is split like anything else: `equivalent
            # experience in Physics or Engineering` is two.
            return _atomise_once(clean(segment[: m.start()])) + _atomise_once(clean(alt))
    if config.SPLIT_REPAIRS and ";" in PAREN_RE.sub("", segment):
        # A semicolon separates requirements more surely than anything inside
        # them, so it is cut first. The bracket path below never saw it and
        # took `Fluency in English; additional languages (e.g. Dutch, German)`
        # as one head: `Fluency in English; additional Dutch`. A part opening
        # with `or` is an alternative stated in full (`...; or Master's degree
        # with 8+ years`), so the conjunction goes and the part stays whole.
        parts = [clean(LEAD_CONJ_RE.sub("", clean(p))) for p in _split_outside_parens(segment, ";")]
        parts = [p for p in parts if p]
        if len(parts) > 1:
            return [a for p in parts for a in _atomise_once(p)]
    if config.SPLIT_REPAIRS:
        m = _IDEALLY_TAIL_RE.search(segment)
        main = clean(segment[: m.start()]) if m else ""
        names = _cut(m.group("tail")) if m else []
        if len(main.split()) > 1 and len(names) > 1 and all(n[:1].isupper() for n in names):
            # `Experience with analytics and BI tools, ideally Excel, Qlik Sense
            # or comparable solutions`: `ideally` qualifies, it does not add
            # (COUNT_GUIDE). The names stay, marked optional, and are not
            # counted beside the requirement they qualify (`counted`). Rules 0.3.0.
            word = m.group("word")
            return (_atomise_once(main) or [main]) + [f"{word[:1].upper()}{word[1:]} {n}" for n in names]
        # `Understanding of the Microsoft ecosystem (Azure, data, AI, custom
        # development)`: the bracket lists what the ecosystem is made of, not
        # what is asked, and the user's reading of the 2026-11-09 trial keeps the
        # one requirement, bracket dropped (rules 0.3.0).
        m = PAREN_LIST_RE.search(segment)
        if m and ECOSYSTEM_RE.search(segment[: m.start()]) and not clean(segment[m.end():]):
            return [clean(segment[: m.start()])]
    if config.EXPAND_PAREN_LISTS:
        paren = _split_paren_list(segment)
        if paren and len(paren) > 1:
            return paren

    store: list[str] = []

    def _mask(m: re.Match) -> str:
        store.append(m.group(0))
        return f"@@{len(store) - 1}##"

    masked = PAREN_RE.sub(_mask, segment)
    if _use_pos():
        # PATTERNS.md P1, its limit: `between` relates its members rather than
        # listing them (`trade-offs between scope, quality and timeline`,
        # `switch between vision and detail`), so the span is one unit.
        masked = BETWEEN_RE.sub(_mask, masked)
        # `within operations or planning` after the requirement's own object
        # (`experience in supply chain management within ...`) sets its scope,
        # one requirement (decided 2026-10-30 on the human count). Opening the
        # requirement (`Experience within banking or insurance`) it is the
        # governing preposition and the list counts as usual.
        masked = WITHIN_RE.sub(
            lambda m: _mask(m) if PREP_RE.search(masked[: m.start()]) else m.group(0), masked)
        # `100,000 endpoints`: a thousands separator is not a list comma.
        masked = NUM_COMMA_RE.sub(_mask, masked)

    out: list[str] = []
    for part in masked.split(";"):
        part = clean(part)
        if part:
            out.extend(_split_list(part))

    def _unmask(s: str) -> str:
        # until none is left: a mask can hold another (`within ... (IAM)`, rules 0.4.9,
        # batch 7 leaked `@@0##` into two keys)
        for _ in range(4):
            if not PLACEHOLDER_RE.search(s):
                break
            s = PLACEHOLDER_RE.sub(lambda m: store[int(m.group(1))], s)
        return s

    atoms = [a for a in (clean(_unmask(x)) for x in out) if _keep_atom(a)]
    if config.SPLIT_REPAIRS:
        atoms = [b for a in atoms for b in _expand_name_slash(a)]
        atoms = [b for a in atoms for b in ((_verb_split(a) if not _atom_has_name(a) else None) or [a])]
    if config.SPLIT_REPAIRS and len(atoms) > 1:
        # The bracket path abstains on a head that is itself a list, so the
        # list is split here — and its last piece still carries the bracket:
        # `Practical experience with centralized logging platforms (e.g.,
        # Splunk, ...)`. One level of expansion on the pieces.
        atoms = [x for a in atoms for x in (_split_paren_list(a) or [a])]
    return atoms


def atomise(segment: str) -> list[str]:
    """Split one `must_have` segment into individual requirements.

    Applied repeatedly to its own output, up to ``config.ATOMISE_MAX_PASSES``,
    because real requirements nest and one pass only unwraps the outermost
    layer. `Experience designing and operating ETL pipelines using Airflow,
    Azure Data Factory` is a coordination of two activities *over* a list of
    tools: the first pass splits the tool list, and only a second pass can
    reach the `designing and operating` inside each result.

    Stops as soon as a pass changes nothing, so a single-requirement segment
    costs one pass and the fixpoint is reached in two for almost everything.
    """
    global _DEPTH
    if _use_pos() and _DEPTH == 0:
        # Words are tagged in the whole item, not in the chunk being split.
        pos.set_context(segment)
    _DEPTH += 1
    try:
        return _atomise(segment)
    finally:
        _DEPTH -= 1


_DEPTH = 0


def _use_pos() -> bool:
    return config.SPLIT_REPAIRS and config.SPLIT_POS


# A bracket naming only kinds of school says where the degree is from, not a
# field: `Bac+5 degree in Data (University or Engineering School)` was crossed
# into `Bac+5 degree in University`. Dropped. Rules 0.4.1.
_SCHOOL = (r"(?:(?:an?|the|une?)\s+)?(?:universit(?:y|ies|[eé]s?|[aä]t)|(?:engineering|business|technical)\s+schools?|"
           r"schools?\s+of\s+engineer(?:ing|s)?|[eé]coles?\s+(?:d['’]\s*)?(?:ing[eé]nieurs?|de\s+commerce)|"
           r"grandes?\s+[eé]coles?|colleges?|(?:fach)?hochschulen?|polytechnics?|iae)")
_SCHOOL_BRACKET_RE = re.compile(rf"\s*\(\s*{_SCHOOL}(?:\s*(?:,|/|\bor\b|\bou\b|\band\b|\bet\b|\boder\b)\s*{_SCHOOL})*"
                                r"\s*\)", re.I)


# `HBO werk- en denkniveau`, translated `HBO work and thinking level`: a level
# of education, one requirement, not `HBO work` + `thinking level`. Rules 0.4.2.
_DUTCH_LEVEL_RE = re.compile(r"\b(?P<deg>(?:HBO|WO|MBO)\+?(?:\s*/\s*(?:HBO|WO)\+?)?)\s+(?:work(?:ing)?|think(?:ing)?)"
                             r"(?:\s*(?:and|&)(?:/or)?\s*(?:work(?:ing)?|think(?:ing)?))?\s+level\b", re.I)
# Its other spellings in batch 2 (rules 0.4.3): `Hbo- or wo-work- and
# think-level`, and `or comparable level of work and thinking` after a degree,
# which adds nothing, as `or equivalent qualification` does not.
_DUTCH_LEVEL2_RE = re.compile(r"\bhbo-?\s*(?:or|of)\s*wo-?\s*work-?\s*and\s*think(?:ing)?-?\s*level\b", re.I)
# untranslated, rules 0.4.4: `HBO+ of WO werk- en denkniveau in Data Science`
_DUTCH_LEVEL_NL_RE = re.compile(r"\s+werk-?\s*en\s*denkniveau\b", re.I)
_COMPARABLE_LEVEL_RE = re.compile(r"\s*,?\s+or\s+(?:a\s+)?(?:comparable|equivalent|similar)\s+(?:level\s+of\s+work\s+and\s+"
                                  r"thinking|work[- ]?\s*and\s+think(?:ing)?[- ]?\s*level)\b", re.I)
# `or similar`, `or a similar direction` closing a list: it adds nothing, and
# left on the list it kept the list whole (`Ansible, Cloud formation or
# similar`). Rules 0.4.3. Never `or equivalent experience`, a second route.
_OR_SIMILAR_LIST_RE = re.compile(
    r"\s*,?\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:similar|comparable|equivalent)(?:\s*\([^()]*\))?"
    r"(?:\s+(?:roles?|positions?|functions?|tools?|technolog(?:y|ies)|platforms?|solutions?|software|languages?|"
    r"directions?|fields?|areas?|(?:technical\s+)?training|programmes?|subjects?|study|studies))?"
    # before a closing bracket or the end; before a comma too (`or similar role,
    # ideally with ...`) and never before a bracket followed by more (`or
    # equivalent (minimum 12 years) work experience` is the second route). 0.4.4
    r"(?=\s*(?:\([^()]*\)\s*[.;]?\s*$|\)|[.;,]|$))", re.I)
# Rules 0.4.3. The marker alone after a comma (`Lean Explorer certification,
# desired`) was cut into an atom of its own, and `, but not required` after `is
# a plus` became the atom `Experience with`: both are joined to the atom they
# qualify. `Bonus points for` and `Desired` open an optional one.
_COMMA_MARK_RE = re.compile(r",\s*(?P<m>desired|preferred|desirable|a\s+plus|appreciated|welcome|valued|advantageous)"
                            r"\s*[.!]?$", re.I)
# `is not a requirement, but an asset` (rules 0.4.4): the comma cut `but an asset` into an atom
_NOT_REQ_BUT_RE = re.compile(r"\s+is\s+not\s+a\s+(?:requirement|must),\s*but\s+(?:an?\s+)?(?:asset|plus|advantage|bonus)"
                             r"\s*[.!]?$", re.I)
_NOT_REQUIRED_RE = re.compile(r",?\s*(?:but|though)\s+not\s+(?:required|mandatory|essential)\s*[.!]?$", re.I)
_BONUS_POINTS_RE = re.compile(r"^bonus\s+points?\s+(?:for|if)\s+", re.I)


def _drop_or_similar(segment: str) -> str:
    """`Ansible, Cloud formation or similar` -> `Ansible or Cloud formation`: the
    `or` was the list's conjunction, so the last comma takes its place."""
    m = _OR_SIMILAR_LIST_RE.search(segment)
    if not m:
        return segment
    before, after = segment[: m.start()], segment[m.end():]
    k = before.rfind(",")
    if k != -1 and not re.search(r"\b(?:and|or|and/or|&)\b", before[k:], re.I):
        before = f"{before[:k]} or{before[k + 1:]}"
    return before + after
# `in a technical direction, e.g. X or Y`: the category before the examples
# is not a requirement (count guide), and `with 4+ years as a Scrum Master`
# after another experience is a second one.
_CATEGORY_EG_RE = re.compile(r"\s+in\s+an?\s+(?:technical|relevant|related|similar)\s+(?:direction|field|area|discipline)"
                             r",?\s+(?:e\.g\.|such\s+as|for\s+example|like)\s+", re.I)
_WITH_YEARS_RE = re.compile(r",\s*with\s+(?=(?:at\s+least\s+|(?:a\s+)?minimum\s+(?:of\s+)?)?\d{1,2}\s*\+?\s*years?\s+(?:as|in|of|at)\b)",
                            re.I)
# `3 years or more of experience` (rules 0.4.4): `or more` is not an alternative
_YEARS_OR_MORE_RE = re.compile(r"\b(\d{1,2})\s*(years?|yrs?)\s+or\s+more\b", re.I)
_MARKER_AND_RE = re.compile(r"(\b(?:is|are)\s+(?:given\s+priority|(?:even\s+)?better|preferred|an?\s+plus|"
                            r"an?\s+advantage))\s*,\s*(?:and\s+)?(?=\S)", re.I)
_POSSIBILITY_RE = re.compile(r"^(?:the\s+)?(?:possibility|willingness)\s+to\s+(?:complete|undergo)"
                             r"\s+(?:an?\s+|the\s+)?(?=\S)", re.I)
# `at C1 level or above` (batch 3): `above` was a second English requirement
_LEVEL_OR_ABOVE_RE = re.compile(r"(\b(?:level|[ABC][12]|grade|score))\s+or\s+(?:above|higher|better)\b", re.I)
# `Highly organized with the ability to manage ...` (rules 0.4.4, review of batch 2):
# a trait and an ability, two requirements
_TRAIT_WITH_ABILITY_RE = re.compile(
    r"^(?P<trait>(?:highly|very|extremely)?\s*[a-z-]+(?:ed|ive|ous|ful|ent|ant|al|ic))\s*,?\s+with\s+"
    r"(?P<ability>(?:the|an?|strong|proven|good)?\s*abilit(?:y|ies)\s+to\s+.+)$", re.I)


# Rules 0.4.5, from the user's review of batch 3 (2026-11-18).
# `Master's degree in Power Electronics/Electrical/Mechatronics`: fields in
# alternative (review of batch 4); `AI/ML` and `CI/CD` are too short to touch
_DEGREE_SLASH_FIELDS_RE = re.compile(
    r"(?<=\bin\s)[A-Za-z][\w ]{3,}?(?:/[A-Za-z][\w ]{3,}?)+(?=$|[,.;(])")
_NAMES_SLASHED = (r"C\+\+|C#|C|Python|Java|JavaScript|TypeScript|Go|Golang|Rust|Scala|Kotlin|Ruby|PHP|R|SQL|Bash|Perl|"
                  r"Swift|MATLAB|Matlab|Spark|Databricks|Kafka|Docker|Kubernetes|Terraform|Ansible|AWS|Azure|GCP|"
                  r"Snowflake|Tableau|Excel|React|Angular|Vue|Node\.js|Django|Flask|PyTorch|TensorFlow")
_NAME_SLASH_RE = re.compile(rf"(?<![\w+#./-])({_NAMES_SLASHED})\s*/\s*({_NAMES_SLASHED})(?![\w+#/-])")
def _atom_has_name(atom: str) -> bool:
    """A name in the atom, a category name aside: with a name the name wins and the verbs go."""
    from . import normalise_req as _nr     # it imports this module
    return any(r not in _nr._CATEGORY_NAMES for r in _nr._name_runs(atom))


def _expand_name_slash(atom: str) -> list[str]:
    """`proficient in C++/Python`: two languages or tools, two requirements (the user's review
    of batch 8, [17]; batch 7, `Databricks/Spark`). Only between names of the closed list,
    so `CI/CD`, `PL/SQL`, `KYC/KYB` stay whole."""
    m = _NAME_SLASH_RE.search(atom)
    if not m:
        return [atom]
    out = []
    for name in (m.group(1), m.group(2)):
        out += _expand_name_slash(atom[:m.start()] + name + atom[m.end():])
    return out


_STUDENT_FORM_RE = re.compile(
    r"^(?=[^,]{0,80}\b(?:students?|final[- ]year|last\s+(?:year|degree)|currently\s+in\s+the)\b)"
    r"(?:(?:senior|current(?:ly)?)\s+(?:or\s+)?)?(?:(?:enrolled|studying)\s+)?"
    r"(?:(?:in\s+)?(?:the\s+)?(?:final|last)[- ]year\s+(?:of\s+)?)?"
    r"(?:students?\s+(?:pursuing|of|in|enrolled\s+in|studying)\s+)?"
    r"(?:(?:the\s+)?(?:last|final)\s+(?:year\s+of\s+)?)?(?:an?\s+)?"
    r"(?:(?:bachelor|master|degree|bsc|msc)(?:['’]?s)?(?:\s+degree)?\s*(?:,|or|and|/)?\s*)+"
    r"(?:degree\s+)?(?:in|of)\s+(?=\w)", re.I)
_ROLE_END_RE = re.compile(r"\b(?:engineer|developer|manager|analyst|architect|consultant|specialist|lead|role|"
                          r"scientist|designer|owner|administrator|officer|advisor|adviser|partner|director|head|"
                          r"tester|programmer|technician|coordinator|researcher)s?$", re.I)
_YEARS_AS_ROLES_RE = re.compile(
    r"^(?P<y>(?:(?:at\s+least|minimum(?:\s+of)?)\s+)?\d{1,2}(?:\s*[-–]\s*\d{1,2})?\+?\s*(?:years?|yrs?)"
    r"(?:\s+of\s+(?:\w+\s+)?experience)?)\s+as\s+(?P<a>an?\s+)?"
    r"(?P<l>[^,()]+(?:\s*,\s*[^,()]+)+)\s*\.?$", re.I)
_INDEP_COLLAB_RE = re.compile(
    r"^(?P<h>.*?\b(?:work|working))\s+(?P<a>independently|autonomously)\s+(?:and|as\s+well\s+as|&)\s+"
    r"(?P<b>collaboratively|in\s+(?:a\s+)?teams?|as\s+(?:part\s+of\s+)?a\s+team|"
    r"(?:with)?in\s+(?:a\s+)?team(?:\s+(?:environment|setting|context))?)\s*\.?$", re.I)
_ABILITY_AND_TRAIT_RE = re.compile(
    r"^(?P<a>(?:the\s+)?abilit(?:y|ies)\s+to\s+.+?)\s+and\s+(?P<t>autonomy|independence|creativity|flexibility|"
    r"initiative|curiosity|resilience|proactivity|reliability)\s*\.?$", re.I)
# who the communication is for is its context, not more requirements
_SKILL_CONTEXT_RE = re.compile(
    r"^(?P<s>.*?\bcommunication\s+skills?)\s+(?P<c>(?:targeted\s+)?(?:towards?|with|for|across|"
    r"to\s+(?:interact|communicate|work)\s+with)\s+.+?)\s*\.?$", re.I)
# what a skill is for: `Basic programming skills to support scripting and configuration tasks`
_SKILL_PURPOSE_RE = re.compile(
    r"^(?P<s>.*?\bskills?)\s+(?P<p>to\s+(?:support|help|enable|perform|handle|automate)\b.+?)\s*\.?$", re.I)


# `Any degree and 8+ years' relevant experience`: a degree and an experience (batch 4)
_DEGREE_AND_YEARS_RE = re.compile(
    r"^(?P<d>.*?\b(?:degree|diploma|bachelor\S*|master\S*|ph\.?d)\b[^,;]*?)\s*,?\s+(?:and|plus|\+)\s+"
    r"(?P<y>(?:at\s+least\s+|minimum\s+(?:of\s+)?)?\d{1,2}\s*\+?\s*(?:years?|yrs?)\b.*)$", re.I)


_WITH_FRAME_TAIL_RE = re.compile(
    r"^(?P<a>.+?),\s*with\s+(?:an?\s+)?(?P<b>(?:(?:strong|solid|good|deep|proven|hands-on|extensive|excellent|"
    r"some|practical)\s+)?(?:[\w/+#.-]+\s+){0,3}(?:experience|expertise|knowledge|skills|understanding|background)"
    r"(?:\s+(?:of|in|with|on)\s+.+)?)\s*\.?$", re.I)
_TRAIT_WITH_RE = re.compile(
    r"^(?P<t>[\w-]+-(?:oriented|minded|driven)|detail[- ]oriented|self-?motivated|proactive|curious|organi[sz]ed|"
    r"structured|rigorous|autonomous)\s+with\s+(?:an?\s+)?(?P<p>(?:[\w-]+\s+){0,2}(?:approach|mindset|attitude|"
    r"sense|eye)\b.*)$", re.I)


def _review_045_split(segment: str) -> list[str] | None:
    s = segment.strip()
    # batch 8: `About 5 years as a Product Owner, with a solid experience of eCommerce`:
    # the second frame is a requirement of its own (13 rows)
    m = _WITH_FRAME_TAIL_RE.match(s)
    if m and (_CLAUSE_DONE_RE.search(m.group("a")) or re.search(r"\d\s*\+?\s*(?:years?|yrs?)\b", m.group("a"), re.I)):
        return _atomise_once(clean(m.group("a"))) + _atomise_once(clean(m.group("b")))
    # `Detail-oriented with a structured approach to work`: two traits (8 rows)
    m = _TRAIT_WITH_RE.match(s)
    if m:
        return [m.group("t"), clean(m.group("p"))]
    # [47] `Self-motivated with a passion for renewable energy`: the trait, and the passion
    m = re.match(r"^(?P<t>self-?motivated|motivated|driven|curious|proactive|enthusiastic|ambitious)\s+with\s+"
                 r"(?:an?\s+)?(?P<p>(?:(?:strong|real|genuine|deep)\s+)?(?:passion|interest|curiosity|enthusiasm)\s+"
                 r"(?:for|in)\s+.+)$", s, re.I)
    if m:
        p = clean(m.group("p"))
        # `a passion for X and Y` is two passions, one per object (the user, 2026-11-23,
        # reversing the one-ask reading of 0.4.9)
        return [m.group("t")] + _atomise_once(p)
    m = _DEGREE_AND_YEARS_RE.match(s)
    if m:
        return [clean(m.group("d"))] + _atomise_once(clean(m.group("y")))
    m = _YEARS_AS_ROLES_RE.match(s)
    if m:
        roles = [clean(x) for x in re.split(r"\s*,\s*(?:(?:or|and)\s+)?|\s+(?:or|and)\s+", m.group("l")) if clean(x)]
        if len(roles) >= 2 and all(len(r.split()) <= 4 and _ROLE_END_RE.search(r) for r in roles):
            return [clean(f"{m.group('y')} as {m.group('a') or 'a '}{r}") for r in roles]
    m = _INDEP_COLLAB_RE.match(s)
    if m:
        return [clean(f"{m.group('h')} {m.group('a')}"), clean(f"{m.group('h')} {m.group('b')}")]
    m = _ABILITY_AND_TRAIT_RE.match(s)
    if m:
        return [clean(m.group("a")), m.group("t")[:1].upper() + m.group("t")[1:]]
    for rx, part in ((_SKILL_CONTEXT_RE, "c"), (_SKILL_PURPOSE_RE, "p")):
        m = rx.match(s)
        if m and "(" not in m.group(part):
            skills = _review_045_rewrite(m.group("s"))
            if re.search(r"\s(?:and|&)\s", skills):
                # [96] `Strong business analysis and communication skills with 4+ years`:
                # the skills split, each keeps the context (the user's review of batch 8)
                return [clean(f"{a} ({m.group(part)})") for a in _atomise_once(skills)]
            return [clean(f"{m.group('s')} ({m.group(part)})")]
    return None


def _review_045_rewrite(segment: str) -> str:
    s = re.sub(r"^Number\s+of\s+years\s*:\s*", "", segment, flags=re.I)
    # rules 0.4.7, the review of batch 5:
    # `as a Senior, Staff or Lead Software Engineer` is one role, the seniority goes
    s = re.sub(r",?\s*\(?(?:typically|usually|ideally|preferably)\s+\d{1,2}\+?\s*(?:years?|yrs?)\)?\s*$", "", s,
               flags=re.I)
    s = re.sub(r"^(?:used|accustomed)\s+to\s+(?=\w)", "", s, flags=re.I)
    # the user's review of batch 7:
    # [0] `You study digital management, data science, ...`: a student in each field
    s = re.sub(r"^(?:you\s+(?:are\s+)?(?:currently\s+)?(?:study|studying)|currently\s+studying)\s+"
               r"(?!(?:or|and|abroad)\b)(?=\w)",
               "Student in ", s, flags=re.I)
    # [21] `People manager & customer focused`: two asks, the second an attitude
    s = re.sub(r"^([\w-]+\s+[\w-]+)\s*&\s*(?=[\w-]+[\s-](?:focused|oriented|driven|minded)\s*\.?$)", r"\1, ",
               s, flags=re.I)
    # [47] `Self-motivated with a passion for renewable energy`: the trait, and the passion
    # [38] `Good analytical and problem solving capabilities`: one per skill, the frame shared
    s = re.sub(r"\b((?:(?:strong|good|very\s+good|excellent|advanced|solid|demonstrated|proven|exceptional|"
               r"outstanding|sound)\s+)?)(analytical|organi[sz]ational|communication|interpersonal|leadership|technical|"
               r"logical)\s+and\s+(problem[- ]solving|decision[- ]making)\s+(skills|capabilities|abilities|capacities)"
               r"(?=\s*[.;]?\s*$)", r"\1\2 \4 and \1\3 \4", s, flags=re.I)
    s = re.sub(r"^((?:(?:strong|good|very\s+good|excellent|advanced|solid|demonstrated|proven|exceptional|outstanding|"
               r"sound)\s+)?)(analytical)\s+and\s+(problem[- ]solving|decision[- ]making)\s*[.;]?$", r"\1\2 skills and \1\3 skills", s,
               flags=re.I)
    # rules 0.4.9, the agents on batch 7 (about 100 degrees not read):
    # `Full degree`, `Professional degree`, `official Master`: the word says nothing the degree does not
    s = re.sub(r"\b(?:full|complete|completed|official|recogni[sz]ed|accredited|professional|formal)\s+"
               r"(?=(?:university\s+)?(?:degree|master|bachelor|diploma)\b)", "", s, flags=re.I)
    s = re.sub(r"\bmaster[- ]of[- ]science\s+degree\b", "Master's degree", s, flags=re.I)
    s = re.sub(r"\bmaster['’]?s?[- ]level\s+(?:studies|education|degree|qualification|diploma)\b", "Master's degree",
               s, flags=re.I)
    # `Diploma o Laurea a indirizzo informatico` came out `Degree at computer science address`
    s = re.sub(r"\bat\s+((?:[\w-]+\s+){0,2}[\w-]+)\s+address\b", r"in \1", s, flags=re.I)
    # students in their last year, written every way: `Students of last Degree or Master's degree
    # in X`, `final year student pursuing a Bachelor's or Master degree in X`, `Currently in the
    # final year of a Master's degree in X`: a student in X
    s = _STUDENT_FORM_RE.sub("Student in ", s)
    # `Bilingual in English and French`: both at the top level
    s = re.sub(r"^bilingual\s+(?:in\s+)?([A-Z]\w+)\s*(?:and|&|/|-)\s*([A-Z]\w+)\b", r"native-level \1, native-level \2",
               s, flags=re.I)
    # `Upper-Intermediate+ English level`
    s = re.sub(r"\b(upper-intermediate|intermediate|advanced|fluent|proficient)\+(?=\s)", r"\1", s, flags=re.I)
    # `relational and non-relational databases`: the tail is shared
    s = re.sub(r"\b([a-z][\w-]*)\s+(?:and|or|&|/)\s+(non-?\1)\s+([a-z][\w-]*)\b", r"\1 \3 and \2 \3", s, flags=re.I)
    # `RDBMS and NoSQL datastores`, `RESTful and SOAP web services`: two names over one kind
    s = re.sub(r"(?-i:\b([A-Z][\w.+#-]*[A-Z][\w.+#-]*|[A-Z]{2,}[\w.+#-]*))\s+(?:and|or|&)\s+"
               r"(?-i:([A-Z][\w.+#-]*[A-Z][\w.+#-]*|[A-Z]{2,}[\w.+#-]*))\s+"
               r"(datastores|data\s+stores|databases|web\s+services|services|APIs|environments|platforms)\b",
               r"\1 \3 and \2 \3", s)
    # the user's review of batch 8 (rules 0.4.10):
    # [1] `Expert-level SQL with experience in BigQuery and MariaDB`: the language, and the tools
    s = re.sub(r"^((?:[\w-]+\s+){0,2}(?-i:[A-Z][\w.+#/-]*))\s+with\s+(?:(?:hands-on|practical|some|solid|good)\s+)?"
               r"(experience|knowledge|exposure)\s+(in|of|with)\s+(?=\S)", r"\1; \2 \3 ", s, flags=re.I)
    # [45] `An understanding of how modern, component-based sites are built, so you design ...`
    s = re.sub(r"\bhow\s+(?:modern\s*,?\s*)?((?:[\w-]+\s+){0,3}?[\w-]+)\s+(?:are|is)\s+(?:built|designed|developed|made|"
               r"structured)\b[^,;]*", r"\1", s, flags=re.I)
    s = re.sub(r",\s*so\s+(?:that\s+)?you\b.*$", "", s, flags=re.I)
    # [78] `LLM-powered or agentic applications`: the kind is shared
    s = re.sub(r"\b([\w-]+-(?:powered|based|driven|enabled|native|first))\s+(or|and)\s+([\w-]+)\s+"
               r"(applications?|apps?|systems?|solutions?|products?|services?|tools?|platforms?|agents?)\b",
               r"\1 \4 \2 \3 \4", s, flags=re.I)
    # [96] `Strong business analysis and communication skills`: one per skill, the level shared
    s = re.sub(r"^((?:(?:strong|good|very\s+good|excellent|solid|proven|demonstrated|outstanding|exceptional)\s+)?)"
               r"(?!(?:strong|good|very|excellent|solid|proven|demonstrated|outstanding|exceptional)\b)"
               r"([a-z]+\s+[a-z]+)\s+and\s+"
               r"(communication|interpersonal|leadership|organi[sz]ational|presentation|analytical|problem[- ]solving|"
               r"stakeholder\s+management)\s+(skills|abilities|capabilities)\b", r"\1\2 \4 and \1\3 \4", s, flags=re.I)
    # [23] `Currently enrolled in a Master's program at an engineering school`: a master in engineering
    s = re.sub(r"\b(master|bachelor)['’]?s?\s+program(?:me)?\b", r"\1's degree", s, flags=re.I)
    s = re.sub(r"^(?:currently\s+)?enrolled\s+in\s+an?\s+(?=(?:master|bachelor)'s\s+degree)", "", s, flags=re.I)
    s = re.sub(r"\s+(?:at|from|in)\s+an?\s+engineering\s+school\b", " in Engineering", s, flags=re.I)
    # the agents on batch 8: `Doctor's degree` (17 rows) is a PhD
    s = re.sub(r"\bdoctor['’]?s?\s+degree\b|\bdoctoral\s+degree\b|\bdoctorate(?:\s+degree)?\b", "PhD", s, flags=re.I)
    s = re.sub(r"^(?:currently\s+)?enrolled\s+(?:\(\s*(?:full|part)[- ]time\s*\)\s+|(?:full|part)[- ]time\s+)?in\s+an?\s+"
               r"(?=(?:master|bachelor)['’]?s?\s+(?:degree|program))", "", s, flags=re.I)
    s = re.sub(r"\b(master|bachelor)s\s+(?=degree|program)", r"\1's ", s, flags=re.I)
    # [50] `Bachelor's degree +5` is how the translator writes `Bac +5`, a master
    s = re.sub(r"\bbachelor['’]?s?\s+degree\s*\+\s*[45]\b", "Master's degree", s, flags=re.I)
    s = re.sub(r"\bbachelor['’]?s?\s+degree\s*\+\s*3\b", "Bachelor's degree", s, flags=re.I)
    # rules 0.4.9, batch 7 (19 items): `Interest or experience with LLMs`, `Interest and
    # first experience with X`. The interest is an attitude and the object after it is not
    # generic, so it goes (the user's call, 2026-11-23); it was read as a second head and
    # crossed with every name (`Interest with Kubernetes`).
    s = re.sub(r"^(?:(?:a|an|strong|genuine|real|keen)\s+)*interest(?:\s+in)?\s*(?:,|or|and|and/or|&|/)\s*"
               r"(?=(?:(?:first|initial|some|practical|hands-on|prior|previous|an?)\s+)*"
               r"(?:experience|knowledge|exposure|familiarity)\b)", "", s, flags=re.I)
    s = re.sub(r"\b(with\s+an?\s+[\w-]+),\s+([\w-]+\s+(?:focus|orientation|emphasis))\b", r"\1 \2", s, flags=re.I)
    # rules 0.4.8, batch 6: `Education: Bachelor's degree in X, Y` is the degree in X and Y
    s = re.sub(r"^(?:Education|Qualifications?|Academic\s+background)\s*:\s*(?=\S)", "", s, flags=re.I)
    _sen = r"(?:Senior|Staff|Lead|Principal|Junior|Medior|Mid(?:-level)?|Sr\.?|Jr\.?)"
    s = re.sub(rf"\b{_sen}(?:\s*,\s*{_sen})*\s*,?\s+(?:or|and|/)\s+{_sen}\s+(?=[A-Z])", "", s)
    # `or have equivalent experience` is the alternative `or equivalent experience`
    s = re.sub(r"\bor\s+(?:have|possess|with|hold)\s+(?:an?\s+)?(equivalent|comparable|relevant)\s+experience",
               r"or \1 experience", s, flags=re.I)
    # `bachelor's Degree or equivalent in work experience and training`: the alternative says nothing more
    s = re.sub(r"(\b(?:degree|diploma|bachelor'?s?|master'?s?)\b)\s+or\s+equivalent\s+in\s+(?:work\s+|professional\s+)?"
               r"experience(?:\s+and\s+training)?", r"\1", s, flags=re.I)
    # `You think logically and analytically` (German `Du denkst logisch und analytisch`)
    s = re.sub(r"^(?:you\s+)?think\s+logically\s+and\s+analytically\b", "logical thinking, analytical thinking",
               s, flags=re.I)
    # `The preparation of a Bac +4 or Bac +5 degree`: preparing a degree is studying for it
    s = re.sub(r"^(?:the\s+)?preparation\s+of\s+(?:an?\s+)?", "", s, flags=re.I)
    # `(or Terraform, with willingness to learn)`: how open to learning, not a requirement
    s = re.sub(r",?\s*with\s+(?:a\s+)?willingness\s+to\s+learn(?=\s*\))", "", s, flags=re.I)
    # `with Bicep (or Terraform)`: an alternative in brackets is an alternative
    s = re.sub(r"\s*\(\s*or\s+([A-Z][^(),]*)\)", r" or \1", s)
    # the translator's Chinese `本科及以上`: a bachelor or more, in the fields that follow
    s = re.sub(r"^(?:Graduate|Bachelor(?:'s|’s)?(?:\s+degree)?|College(?:\s+degree)?|Undergraduate)\s+(?:and|or)\s+"
               r"(?:above|higher)\s*,\s*", "Bachelor's degree in ", s, flags=re.I)
    # the German `Eingeschriebenes Studium`, `Erfolgreich abgeschlossenes Studium`
    s = re.sub(r"^(?:registered|enrolled)\s+(?:university\s+)?stud(?:ies|y)\s+in\s+", "Current degree in ", s, flags=re.I)
    s = re.sub(r"^(?:successful(?:ly)?\s+)?complet(?:ion\s+of|ed)\s+(?:(?:university|your)\s+)?stud(?:ies|y)\s+in\s+",
               "Degree in ", s, flags=re.I)
    s = re.sub(r"\b(Teamwork|Team\s*spirit|Teamfähigkeit)\s*&\s*", r"\1, ", s)
    # `leading CoE / practice / large delivery teams`: two spaced slashes make a list
    outside = re.sub(r"\([^()]*\)", "", s)
    if outside.count(" / ") >= 2:
        s = re.sub(r" / (?![^()]*\))", ", ", s)
    return s


# Clauses, each with its own frame (rules 0.4.7, batch 5): `3+ years of experience
# in Python, SQL and Spark, strong knowledge of Docker and Kubernetes, and
# experience with cloud platforms (AWS, GCP, Azure)` is three asks. Split as a
# whole, the last bracket was read as the list for everything, and the line came
# back unsplit (route `llm`: 55 of the 109 `comma_in_key` flags of batch 5). A
# clause opens on a frame noun followed by its object, or on a number of years.
_CLAUSE_HEADS = r"(?:experience|knowledge|understanding|proficiency|familiarity|expertise|exposure|background|command)"
_CLAUSE_LEVEL = (r"(?:(?:strong|solid|good|excellent|deep|proven|hands-on|working|practical|basic|advanced|"
                 r"extensive|in-depth|sound|thorough|demonstrated|demonstrable|some|prior|previous|relevant|"
                 r"professional|technical|very|great|broad)\s+)*")
_CLAUSE_OPEN = (rf"(?:an?\s+)?{_CLAUSE_LEVEL}{_CLAUSE_HEADS}\s+(?:working\s+)?(?:of|in|with|on|using|across)\s+\S|"
                r"(?:at\s+least\s+|(?:a\s+)?minimum\s+(?:of\s+)?)?\d{1,2}\+?\s*(?:years?|yrs?)\b")
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\s*[,;]\s*(?:and\s+|as\s+well\s+as\s+|plus\s+)?|\s+(?:and|plus|as\s+well\s+as)\s+)"
    rf"(?=(?:{_CLAUSE_OPEN}))", re.I)
_CLAUSE_DONE_RE = re.compile(
    rf"\b{_CLAUSE_HEADS}\s+(?:of|in|with|on|using|across)\s+\S|\d{{1,2}}\+?\s*(?:years?|yrs?)\s+(?:of\s+)?\S|"
    r"(?-i:\b(?!(?i:strong|solid|good|excellent|deep|proven|hands-on|working|practical|basic|advanced|extensive|"
    r"in-depth|sound|thorough|demonstrated|demonstrable|some|prior|previous|relevant|professional|technical|very|"
    r"great|broad|active|general|fundamental|comprehensive|detailed|profound|wide|expert|specialist|"
    r"specialized|specialised|necessary|required|first|initial|further|additional)\b)"
    r"(?:[A-Z][\w.+#/-]*|[A-Z]{2,}[\w.+#/-]*))\s+(?:skills|knowledge|expertise|proficiency|experience)$",
    re.I)


# Names listed before a category that introduces more names (rules 0.4.7, batch
# 5): `HTML5, CSS3, JavaScript, and frameworks like Angular or React` came out
# as Angular and React only, the names in front dropped with the category.
# The category goes and the names join one list.
_CATEGORY_INTRO_RE = re.compile(
    # it opens after a comma or a space, never inside a word (`Java and` read as `ava and`)
    r"(?:,\s*|\s+)(?:(?:and|or|as\s+well\s+as|plus)\s+)?(?:(?:other|modern|related|common|similar|relevant)\s+)?"
    # two words of the category at most, never a preposition (`in AWS with services like`)
    r"(?:(?!(?:with|in|on|for|of|using|via|at|to)\b)[a-z][\w-]*\s+){0,2}"
    r"(?:frameworks?|tools?|librar(?:y|ies)|languages?|platforms?|technolog(?:y|ies)|databases?|"
    r"stacks?|solutions?|services?)\s*,?\s*(?:such\s+as|like|including|e\.\s?g\.,?)\s+")


def _names_before_category(segment: str) -> str:
    m = _CATEGORY_INTRO_RE.search(segment)
    if not m or m.start() == 0:
        return segment
    before = segment[:m.start()].rstrip(" ,")
    last = before.split()[-1] if before.split() else ""
    # only after a list of names: the word before is a name (`JavaScript`, `SQL`),
    # or a name with its frame word (`Strong SQL skills and analytics tools like X`)
    named_last = last[:1].isupper() or re.search(r"\d", last) or (
        last.lower() in ("skills", "knowledge", "experience", "expertise", "proficiency")
        and re.search(r"\b[A-Z][\w.+#/-]*\s+" + re.escape(last) + r"$", before))
    # and a list, not one name with its kind (`Microsoft tools such as Excel` stays)
    listy = "," in before or re.match(r"[,\s]*(?:and|or|plus|as\s+well\s+as)\b", m.group(0))
    if not named_last or not listy or last.strip("-") in ("AI", "ML", "AI/ML", "BI", "UX", "UI", "IoT", "NLP", "QA"):
        return segment
    if "," not in before and not re.match(
            r"^(?:\w+\s+){0,3}?(?:experience|knowledge|proficiency|familiarity|expertise|skills|understanding|"
            r"command)\b", before, re.I):
        return segment
    return f"{before}, {segment[m.end():]}"


# One requirement per verb (the user's call, 2026-11-23, review of batch 6,
# reversing the call of 2026-10-29): `designing and implementing complex
# solutions` is `designing complex solutions` and `implementing complex
# solutions`; the verb stays when the object is generic. With a name in the
# object the name is what is asked, and the verbs go as before
# (`building and maintaining CI/CD pipelines` is CI/CD).
_BASE_VERBS = ("design|implement|develop|build|maintain|deploy|test|communicate|deliver|manage|lead|operate|"
               "support|plan|create|review|integrate|define|document|analy[sz]e|monitor|optimi[sz]e|configure|"
               "install|troubleshoot|evaluate|train|architect|automate|secure|scale|run|own|drive|execute|"
               "coordinate|prioriti[sz]e|validate|migrate|model|write|propose|"
               # rules 0.4.9, batch 7
               "enforce|improve|establish|identify|assess|resolve|apply|adapt|guide|mentor|coach|negotiate|"
               "present|explain|research|prototype|ship|launch|refine|simplify|standardi[sz]e|govern|audit|"
               "measure|track|report|forecast|estimate|solve|debug|refactor|moderni[sz]e|influence|align")
_VERB_TOKEN = rf"(?:\w+ing|{_BASE_VERBS})"
_VERB_RUN_SPLIT_RE = re.compile(
    rf"^(?P<pre>.*?(?:^|\s))(?P<verbs>{_VERB_TOKEN}(?:\s*,\s*{_VERB_TOKEN})*\s*,?\s+(?:and/or|and|or|&)\s+"
    rf"{_VERB_TOKEN})\s+(?P<obj>(?!(?:and|or|with|in|on|for|to|of|the)\b)\S.*)$", re.I)


def _verb_split(segment: str) -> list[str] | None:
    from . import normalise_req as _nr     # it imports this module
    m = _VERB_RUN_SPLIT_RE.match(segment.strip())
    if not m:
        return None
    verbs = [v.strip() for v in re.split(r"\s*,\s*(?:(?:and/or|and|or|&)\s+)?|\s+(?:and/or|and|or|&)\s+",
                                         m.group("verbs")) if v.strip()]
    obj = m.group("obj").strip()
    # every one a verb, by the tagger or the lists; and the object no list and no name
    # the run is the first coordination of the segment (`building X and consistently
    # meeting or exceeding Y` is two clauses, P15), and `or` offers one ask, not two
    # (`meeting or exceeding revenue objectives`)
    if re.search(r",|\band\b|\bor\b|&", m.group("pre")) or (
            re.search(r"\bor\b", m.group("verbs")) and not re.search(r"\band\b|,", m.group("verbs"))):
        return None
    if len(verbs) < 2 or not all(_verb(v) or re.fullmatch(_BASE_VERBS, v, re.I) for v in verbs):
        return None
    if [r for r in _nr._name_runs(_unmasked(obj)) if r not in _nr._CATEGORY_NAMES] \
            or SPLIT_RE.search(_unmasked(obj).split(" with ")[0]):
        return None
    # `marketing and sales strategies`: nouns, not verbs, when nothing in front governs them
    if not m.group("pre").strip() and all(v.endswith("ing") for v in verbs) and not any(
            pos.tag(v)[1] == "VBG" for v in verbs):
        return None
    pre = m.group("pre")
    if pre.strip() and not re.search(r"\b(?:experience|expertise|knowledge|ability|able|capable|skills?|record|"
                                     r"success|background|track|in|of|with|to|at|for|by|on)\s*$", pre, re.I):
        return None
    return [clean(f"{pre}{v} {obj}") for v in verbs]


def _clause_split(segment: str) -> list[str] | None:
    """The clauses of a segment, when it has two or more; else None.

    A split point must be outside brackets, and the part before it must already
    hold a frame with its object: `Knowledge and experience of SQL` is one ask
    (the part before `and` has no object), `Knowledge of Python and experience
    with AWS` two.
    """
    parts, start = [], 0
    for m in _CLAUSE_SPLIT_RE.finditer(segment):
        left = segment[start:m.start()]
        before = segment[:m.start()]
        if before.count("(") != before.count(")") or not _CLAUSE_DONE_RE.search(left):
            continue
        parts.append(left.strip(" ,;"))
        start = m.end()
    if not parts:
        return None
    parts.append(segment[start:].strip(" ,;."))
    return [x for x in parts if x] if len([x for x in parts if x]) > 1 else None


def _atomise(segment: str) -> list[str]:
    if config.SPLIT_REPAIRS:
        segment = _YEARS_OR_MORE_RE.sub(r"\1+ \2", segment)
        # the translator writes `Master ' s degree` (batch 4: 13 items not read)
        segment = re.sub(r"(\w)\s+['’]\s*s\b", r"\1's", segment)
        if _DEG_ANY_RE.search(segment):
            segment = _DEGREE_SLASH_FIELDS_RE.sub(lambda m: m.group(0).replace("/", " or "), segment)
        whole = _review_045_split(segment)
        if whole is not None:
            return whole
        segment = _review_045_rewrite(segment)
        segment = _LEVEL_OR_ABOVE_RE.sub(r"\1", segment)
        # `chassis system area is given priority, and the suspension knowhow is
        # better`: two optional asks, each closed by its marker (review of batch 2)
        segment = _MARKER_AND_RE.sub(r"\1; ", segment)
        # `possibility to complete a screening`: the ask is the screening
        segment = _POSSIBILITY_RE.sub("", segment)
        m = _TRAIT_WITH_ABILITY_RE.match(segment.strip())
        if m:
            return [clean(m.group("trait")), clean(m.group("ability")[:1].upper() + m.group("ability")[1:])]
        segment = _SCHOOL_BRACKET_RE.sub("", segment)
        segment = _DUTCH_LEVEL2_RE.sub("HBO or WO level", segment)
        segment = _DUTCH_LEVEL_NL_RE.sub(" level", segment)
        segment = _DUTCH_LEVEL_RE.sub(lambda m: f"{m.group('deg')} level", segment)
        segment = _COMPARABLE_LEVEL_RE.sub("", segment)
        segment = _drop_or_similar(segment)
        segment = _prepare_degrees(segment)
        if _NOT_REQUIRED_RE.search(segment):
            rest = _NOT_REQUIRED_RE.sub("", segment)
            segment = rest if NICE_TO_HAVE_RE.search(rest) or _BARE_OPTIONAL_RE.search(rest) else f"{rest} is a plus"
        segment = _COMMA_MARK_RE.sub(lambda m: f" {m.group('m')}", segment)
        segment = _NOT_REQ_BUT_RE.sub(" is an asset", segment)
        segment = _BONUS_POINTS_RE.sub("Desirable: ", segment)
        segment = _CATEGORY_EG_RE.sub(" in ", segment)
        if _WITH_YEARS_RE.search(segment):
            first, second = _WITH_YEARS_RE.split(segment, maxsplit=1)
            return _atomise(first) + _atomise(second)
        segment = _names_before_category(segment)
        verbs = _verb_split(segment)
        if verbs:
            return [a for v in verbs for a in _atomise(v)]
        clauses = _clause_split(segment)
        if clauses:
            return [a for c in clauses for a in _atomise(c)]
    out = _atomise_once(segment)
    for _ in range(max(0, config.ATOMISE_MAX_PASSES - 1)):
        nxt: list[str] = []
        for piece in out:
            nxt.extend(_atomise_once(piece) or [piece])
        if nxt == out:
            break
        out = nxt
    if config.SPLIT_REPAIRS:
        # `... S3, DynamoDB, ... and S3.` names S3 once as a demand, however
        # many times the employer typed it.
        seen: set[str] = set()
        out = [a for a in out if not (normalise(a) in seen or seen.add(normalise(a)))]
    return out


_SHORT_NAME_RE = re.compile(r"[A-Z][A-Z#+]?|[A-Z]#|Go|5G")


def _keep_atom(a: str) -> bool:
    """Drop debris, but not a short name.

    The length floor removes fragments, and also removed `R`, `C#` and the
    `IT` in `connecting governance, IT, policy` — 135 occurrences in the
    software export, a handful of them real languages and fields.
    """
    return len(a) > 2 or bool(config.SPLIT_REPAIRS and _SHORT_NAME_RE.fullmatch(a))


def _split_outside_parens(s: str, sep: str) -> list[str]:
    """`s.split(sep)`, ignoring separators inside brackets."""
    parts, depth, cur = [], 0, []
    for ch in s:
        depth += ch == "("
        depth -= ch == ")" and depth > 0
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


# Surface evidence that a segment holds more than one requirement. Used only to
# decide whether an unsplit segment should be routed onward, never to split.
_MULTI_VERB_RE = re.compile(
    r"\b\w+(?:ing|ieren|iren)\b.{0,60}?\b(?:and|or|und|oder|et|ou|e|y)\b.{0,20}?\b\w+(?:ing|ieren)\b",
    re.I,
)
_CONJ_BETWEEN_RE = re.compile(rf"\w{{3,}}\s+(?:{_CONJ})\s+\w{{3,}}", re.I)


def needs_llm(segment: str, pieces: list[str] | None = None) -> bool:
    """True when a segment looks compound but the rules would not split it.

    ``pieces`` lets a caller that has already split the segment pass the result
    in. Splitting is the expensive part of this function, and `route` needs it
    too — recomputing it there doubled the cost of a corpus pass.

    This is the routing decision for the LLM stage, and it is deliberately a
    *detector* rather than a splitter: it says "more than one requirement is in
    here and I cannot separate them", which is a much weaker claim than knowing
    where the boundaries are, and one that surface evidence can support.

    Anything the rules already split is not routed — the point is to spend the
    expensive stage only on the residue. Scored against the labelled sample in
    `evaluate.score_llm_routing`, so the size of that residue is measured and
    not asserted.
    """
    if pieces is None:
        pieces = atomise(segment)
    if len(pieces) > 1:
        return False

    # Deliberately inclusive. Chosen on the development half from four
    # candidate rules: this one takes recall from 0.364 to 0.818 on dev (0.929
    # held out) at a precision cost of 1.000 -> 0.818, and cuts the requirement
    # mass lost in unrouted segments from 10 to 3. That trade is the right way
    # round because the two errors are not symmetric — a false positive spends
    # one call on a segment the LLM will return unchanged, while a false
    # negative drops requirements that then appear in no table at all.
    if len(segment) > config.LLM_ROUTE_MIN_CHARS:
        return True
    if _CONJ_BETWEEN_RE.search(segment):
        return True
    if "," in segment:
        return True
    if INTRODUCER_RE.search(segment):
        return True
    return _MULTI_VERB_RE.search(segment) is not None


# Surface evidence that a split went wrong, read off the output. Used to decide
# whether to keep a split, never to repair it.
LEAKED_INTRO_RE = re.compile(
    r"(?<!\w)(?:e\.\s?g\.|i\.\s?e\.|z\.\s?b\.|bzw\.\s|bijv\.|p\.\s?ex\.|ex\.\s)", re.I)
# PREP_RE alone lacks `en`, which governs Spanish and French heads
# (`práctica en metodologías DevOps (Jenkins, ...)`); TRIGGER_RE has it.
_GOVERNOR_RE = re.compile(rf"(?:{PREP_RE.pattern}|{TRIGGER_RE.pattern})", re.I)
_GOVERNS_END_RE = re.compile(
    rf"(?:{PREP_RE.pattern}|{TRIGGER_RE.pattern}|\bim Bereich\s+)$", re.I)


def damage_reason(segment: str, pieces: list[str]) -> str | None:
    """Why a split looks broken, or None when nothing visible is wrong.

    The counterpart of `needs_llm` for the rules' OWN output. `route` used to
    accept any split into two pieces as finished, so `Master's degree
    (business, engineering) or equivalent diploma` shipped as `Master's
    business` and `or equivalent diploma`. Four signs, each countable:

    * ``leading_conjunction`` — a later piece starts with `or`/`und`/`et`: the
      boundary fell on the wrong side of the conjunction;
    * ``leaked_introducer`` — `e.g.`/`z. B.` survives outside a bracket, so the
      list it introduced was split as if it were prose. Inside an intact
      bracket it is correct (`Knowledge of containers (e.g. Docker)` is one
      requirement by the guide) and does not count;
    * ``bracket_juxtaposition`` — a bracket item glued onto a head that does
      not govern it, `Familiarity with observability Datadog`. Matched on the
      LONGEST item first, or `eventual consistency` reads as `consistency`
      glued onto `eventual`;
    * ``duplicate`` — two pieces identical once normalised.
    """
    if len(pieces) < 2:
        return None
    if any(LEAD_CONJ_RE.match(p) for p in pieces[1:]):
        return "leading_conjunction"
    if any(LEAKED_INTRO_RE.search(PAREN_RE.sub("", p)) for p in pieces):
        return "leaked_introducer"
    for m in PAREN_LIST_RE.finditer(segment):
        items = sorted(_paren_items(m.group(1)), key=len, reverse=True)
        for p in pieces:
            item = next((i for i in items if p.endswith(" " + i) and p != i), None)
            if item and not _GOVERNS_END_RE.search(p[: -len(item)].rstrip() + " "):
                return "bracket_juxtaposition"
    if len({normalise(p) for p in pieces}) < len(pieces):
        return "duplicate"
    if config.SPLIT_REPAIRS and _BACK_REF_RE.search(segment) \
            and any(re.search(r"\b(?:their|its)\b", p, re.I) for p in pieces[1:]):
        # `the process of creating ML models and their life cycle`: `their`
        # points back into the first part, so the second is not a requirement
        # on its own (`the process of their life cycle`). Rules 0.3.0.
        return "back_reference"
    return None


_BACK_REF_RE = re.compile(r"\b(?:and|or|as well as)\s+(?:their|its)\b", re.I)


def route(segment: str) -> tuple[list[str], str]:
    """Split what can be split, and label how the segment was handled.

    Returns ``(atoms, route)`` where route is one of:

    * ``rules``   — the rules split it, nothing further needed;
    * ``single``  — one requirement, correctly left whole;
    * ``llm``     — compound, and the rules could not separate it;
    * ``damaged`` — only with ``config.SPLIT_REPAIRS``: the rules split it and
      the result is visibly broken, so the segment is kept whole. An unsplit
      requirement is recoverable later; a wrongly split one is not.
    """
    pieces = atomise(segment)
    if config.SPLIT_REPAIRS and not pieces and clean(segment):
        # Nothing survived the filters, so the item itself is the requirement.
        pieces = [clean(segment)]
    if len(pieces) > 1:
        if config.SPLIT_REPAIRS and damage_reason(segment, pieces):
            return [clean(segment)], "damaged"
        return pieces, "rules"
    if config.SPLIT_REPAIRS and pieces and clean(pieces[0]) in _DECIDED_ONE:
        return pieces, "single"
    if config.SPLIT_REPAIRS and pieces and "(" in segment and "(" not in pieces[0]:
        # The rules removed a bracket on purpose (`ECOSYSTEM_RE`): what is left
        # is read for compounds, not the bracket's commas.
        return pieces, "llm" if needs_llm(pieces[0], pieces) else "single"
    return pieces, "llm" if needs_llm(segment, pieces) else "single"


def segments(must_have: str) -> list[str]:
    """The pipe-separated units as delivered, before any splitting."""
    return [s.strip() for s in must_have.split("|") if s.strip()]


def atomise_posting(must_have: str) -> list[str]:
    out: list[str] = []
    for seg in segments(must_have):
        out.extend(atomise(seg))
    return out
