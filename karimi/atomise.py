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
    r"come|par exemple|entre autres)[\s,:]+|\s*:\s*",
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
    r"^(?:and|or|etc\.?|ecc\.?|usw\.?|others?|altri|more|"
    r"(?:a|an|the)?\s*(?:closely\s+)?(?:related|similar|equivalent|relevant|comparable)"
    r"(?:\s+(?:technical|scientific|academic|professional))?"
    r"(?:\s+(?:field|fields|area|areas|discipline|disciplines|subject|subjects|"
    r"experience|qualification|qualifications|degree|role|roles|studies))?|"
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
        out.append(i if i.lower().endswith(tail.lower()) else clean(f"{i} {tail}"))
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
    r"\b(?:is|are|would be|will be|considered)\s+(?:an?\s+)?(?:(?:big|strong|real|huge|definite|"
    r"great|significant|distinct|nice|clear)\s+)?(?:plus|advantage|asset|bonus|benefit)\b|"
    r"\bnice[- ]to[- ]have\b|\b(?:is|are|would be)\s+(?:highly\s+)?(?:desirable|preferred|"
    r"beneficial|welcome|appreciated|valued)\b", re.I)


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
    return bool(m)


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

_LEAD_PUNCT = re.compile(r"^[\s\-–—•*·]+")
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
                  and not (x.group().strip().lower() == "to" and _infinitive(head[x.end():]))), None)
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
            preps = list(PREP_RE.finditer(prior))
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
}


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


def _trait(word: str) -> bool:
    """A one-word adjective that is a trait on its own (`Reliable`, `self-motivated`).
    Not an adverb: `independently and collaboratively` qualify one verb."""
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


def _split_list(s: str) -> list[str]:
    """Split one clause, either as head + list or as a bare coordinated list."""
    if config.SPLIT_REPAIRS:
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
        if pre and not GENERIC_TAIL_RE.search(pre) and len(pre.split()) > 1 \
                and not (config.SPLIT_REPAIRS and LEAD_CATEGORY_RE.search(pre)):
            lead = [pre]
    else:
        matches = list(TRIGGER_RE.finditer(s))
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
            # convention for equivalent alternatives (rules 0.3.0).
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
        if alt and _ALT_PATH_RE.search(alt) and clean(segment[: m.start()]):
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
        return PLACEHOLDER_RE.sub(lambda m: store[int(m.group(1))], s)

    atoms = [a for a in (clean(_unmask(x)) for x in out) if _keep_atom(a)]
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


def _atomise(segment: str) -> list[str]:
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
