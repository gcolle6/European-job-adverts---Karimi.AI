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
    return bool(ADJECTIVAL_RE.match(word)) and not NOMINAL_RE.search(word)


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
    return clean(head[: m.end()]) if m else clean(head)


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
        head = ""
        for prior in reversed(out):
            preps = list(PREP_RE.finditer(prior))
            if not preps:
                continue
            cand = clean(prior[: preps[-1].end()])
            if cand and len(cand) <= config.MAX_HEAD_CHARS \
                    and prior[preps[-1].end():].strip():
                head = cand
                break
        out.append(clean(f"{head} {item}") if head else item)
    return out


def _cut(s: str) -> list[str]:
    parts = (clean(p) for p in SPLIT_RE.split(s))
    parts = (clean(LEAD_CONJ_RE.sub("", p)) for p in parts if p)
    return [p for p in parts if p and not STOP_RE.match(p)]


def _split_list(s: str) -> list[str]:
    """Split one clause, either as head + list or as a bare coordinated list."""
    head, rest = "", s
    lead: list[str] = []

    # An explicit introducer (`such as`, `including`, `:`) is a stronger signal
    # than a bare preposition, and it tells us where the filler ends. Preferred
    # over the preposition search, and the head is trimmed back past the filler.
    intro = INTRODUCER_RE.search(s)
    if intro:
        pre = clean(s[: intro.start()])
        head, rest = _trim_head(pre), s[intro.end():]
        if pre and not GENERIC_TAIL_RE.search(pre) and len(pre.split()) > 1:
            lead = [pre]
    else:
        matches = list(TRIGGER_RE.finditer(s))
        if matches:
            head, rest = s[: matches[-1].end()], s[matches[-1].end():]

    if CORREL_LEAD_RE.match(rest.strip()):
        return [s]

    items = _cut(rest)
    resolved = _resolve_elision(items) if items else items
    if resolved is None:
        return [s]
    items = resolved

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
        return lead + [clean(f"{h} {i}") for h in _head_alternatives(head) for i in items]

    # No usable head + list reading. Fall back to reading the whole clause as a
    # coordinated list — `Sales experience and comfort with targeting new
    # business` is two requirements, but a late preposition inside the second
    # one used to capture the head and suppress the split entirely.
    bare = _cut(s)
    resolved = _resolve_elision(bare) if bare else bare
    if resolved is not None and _is_list(resolved):
        return _distribute_shared_head(resolved)
    return [s]


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

# Generic nouns a bracket typically exemplifies. Kept separate from
# GENERIC_TAIL_RE on purpose: widening that one changed head trimming on every
# other path and cost 8 points of overall recovery, so this list applies only
# where a bracketed list is being expanded.
PAREN_GENERIC_RE = re.compile(
    r"(?:platforms?|systems?|concepts?|solutions?|products?|providers?|"
    r"vendors?|suites?|stacks?|frameworks?|plateformes?|syst[eè]mes?|"
    r"sprache|sprachen|werkzeuge)\s*$", re.I)
_PAREN_LEAD_RE = re.compile(
    r"^(?:e\.?g\.?|i\.?e\.?|z\.?b\.?|such as|like|etwa|ex\.?|par exemple|"
    r"come|p\.?ej\.?|bijv\.?)[\s:,]*", re.I)


def _paren_items(inner: str) -> list[str]:
    """The bracket's contents as list items, or [] if it is not a list."""
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
    m_generic = GENERIC_TAIL_RE.search(before) or PAREN_GENERIC_RE.search(before)
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
    heads = _head_alternatives(head)

    out = [clean(f"{h} {i}") for h in heads for i in items]
    # The phrase before the bracket is usually a requirement in its own right,
    # exactly as with an unbracketed introducer.
    if not GENERIC_TAIL_RE.search(before) and len(before.split()) > 1:
        out.insert(0, before)
    if after and len(after.split()) > 2:
        out.extend(_atomise_once(after))
    return [a for a in out if len(a) > 2] or None


def _atomise_once(segment: str) -> list[str]:
    """One splitting pass over a segment."""
    if config.EXPAND_PAREN_LISTS:
        paren = _split_paren_list(segment)
        if paren and len(paren) > 1:
            return paren

    store: list[str] = []

    def _mask(m: re.Match) -> str:
        store.append(m.group(0))
        return f"@@{len(store) - 1}##"

    masked = PAREN_RE.sub(_mask, segment)

    out: list[str] = []
    for part in masked.split(";"):
        part = clean(part)
        if part:
            out.extend(_split_list(part))

    def _unmask(s: str) -> str:
        return PLACEHOLDER_RE.sub(lambda m: store[int(m.group(1))], s)

    return [a for a in (clean(_unmask(x)) for x in out) if len(a) > 2]


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
    out = _atomise_once(segment)
    for _ in range(max(0, config.ATOMISE_MAX_PASSES - 1)):
        nxt: list[str] = []
        for piece in out:
            nxt.extend(_atomise_once(piece) or [piece])
        if nxt == out:
            break
        out = nxt
    return out


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


def route(segment: str) -> tuple[list[str], str]:
    """Split what can be split, and label how the segment was handled.

    Returns ``(atoms, route)`` where route is one of:

    * ``rules``   — the rules split it, nothing further needed;
    * ``single``  — one requirement, correctly left whole;
    * ``llm``     — compound, and the rules could not separate it.
    """
    pieces = atomise(segment)
    if len(pieces) > 1:
        return pieces, "rules"
    return pieces, "llm" if needs_llm(segment, pieces) else "single"


def segments(must_have: str) -> list[str]:
    """The pipe-separated units as delivered, before any splitting."""
    return [s.strip() for s in must_have.split("|") if s.strip()]


def atomise_posting(must_have: str) -> list[str]:
    out: list[str] = []
    for seg in segments(must_have):
        out.extend(atomise(seg))
    return out
