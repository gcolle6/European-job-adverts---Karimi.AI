"""The errors, by kind and by likely cause: what the site's error table shows.

    from karimi_normalise import errors
    errors.split_profile(rows)                 # splitting: the hand-counted items, per version
    errors.normalise_errors(judged_pairs)      # normalisation: the judge's sample, per run

Two sources, never one number, because they are not the same kind of evidence:

* **splitting** — measured on the 115 items counted by hand, once per rules
  version (`New project/score_split_errors.py`, into the quality card). NOT
  per run, because no automatic reader of a run tells a wrong split well
  enough, and both were tried on 2026-11-07 against those counts: the shape
  rules below (`split_flags`) were right on at most 22% of what they flagged
  (`score_error_detectors.py`), and the judge counting items (`tester.count`)
  on 28% and 21% (`score_judge_counts.py`), against a 60% bar fixed before.
  `split_flags` still runs on every run, as `suspects` in the job's private
  `check.json`: where to look, never counted as errors;
* **normalisation** — the decisions the dictionary took by similarity that
  the judge called wrong (`check.py`, level 3). A sample, read with its
  denominator; never projected to the run.

Each error carries ONE cause, the first that applies, in this order: what
the employer's text looked like (`lowercase`, `translation`,
`long_item`), then what kind of mistake it is. The order is a reading
convention, fixed 2026-11-07: a cause in the input is named before the
mechanism it went through, so a lower-case item that lost its head counts
under `lowercase`. "Likely": a condition that applies is not proof it caused
the error.

Nothing here holds requirement text except `examples`, which goes to the
job's private `check.json` and never to the history or the site.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict

from karimi import config
from karimi.requirements import _BARE_FILLER, _RELATIONAL_HEADS, _STILL_COMPOUND_RE


# What went wrong, per stage and object.
ERRORS = {
    ("splitting", "requirement"): {
        "merged": "two or more requirements left in one",
        "over_split": "one requirement cut into more",
        "fragment": "a piece that is not a whole requirement",
        # rules 0.4.7, batch 5
        "dropped": "a requirement of the item left out",
    },
    ("normalisation", "requirement"): {
        "wrong_group": "placed in a group that is not the same requirement",
        "wrong_topic": "placed under a topic it does not belong to",
        "wrong_degree": "a degree read wrong",
        "optional_kept": "how much it is wanted left in the requirement",
        "word_kept": "a word that adds nothing left in the requirement",
        # rules 0.4.7, batch 5
        "object_lost": "what is asked set aside, the requirement left empty",
    },
    ("translation", "requirement"): {
        "not_translated": "a requirement left in another language",
    },
    ("normalisation", "role"): {
        "wrong_role": "matched to a different role",
    },
}

# Why, in the order the first that applies is taken.
CAUSES = {
    "lowercase": "the item had no capital letters",
    "translation": "the item was translated to English first",
    "long_item": f"a long item (over {config.LONG_SEGMENT_CHARS} characters)",
    "list_not_separated": "a list the rules saw but could not separate",
    "split_looked_broken": "the split looked broken, so the item was kept whole",
    "joined_by_and_or": "two requirements joined by and / or",
    "head_not_repeated": "the shared head ('experience with') was not carried to this item",
    "complement_lost": "a word like 'ability' or 'knowledge' left without its object",
    "filler": "a filler word left on its own",
    "optional_part": "a part marked optional ('is a plus', 'ideally') counted as its own",
    "alternatives": "alternatives where any one will do, counted one each",
    "narrower_or_broader": "one is a narrower version of the other",
    "share_a_word": "different things that share a word",
    "no_shared_word": "different things with no word in common",
    "same_job_word": "same job word, different specialty",
    "different_job_word": "a different job word",
    "degree_not_read": "it names a degree, and the rules did not read it as one",
    "degree_field_odd": "the degree's field holds another degree, an experience or a language",
    "optional_head": "it opens on 'desirable' or 'preferably', and only that word was kept",
    "optional_tail": "it still closes on 'is a plus', 'preferred' or the like",
    "untranslated": "not English, and kept as written",
    "translation_failed": "translated, and still not English",
    "degree_higher_education": "'Higher education' with its fields, not read as a degree",
    "optional_marker_unknown": "it closes on 'as a plus', 'an added advantage' or another phrase the rules do not know",
    "required_left": "'required', 'mandatory' or 'a must' left in the requirement",
    "or_similar_left": "'or similar role', 'or equivalent' left in the requirement",
    "level_left": "a level ('Advanced', 'Intermediate') left in the requirement",
    "lead_punctuation": "it starts with a comma: a list cut on the wrong side",
    "comma_in_key": "a list of names left in one requirement",
    "duplicate_key": "two parts of one item read as the same requirement: a name or an object lost",
    "edge_preposition": "a preposition left at its edge ('on CPaaS', 'development for')",
    "frame_left": "a frame left in front of what is asked ('Interest in', 'programming with', 'popular')",
    "language_as_skill": "a language read as its level or as a skill ('C1', 'English understanding')",
    "context_left": "where or what for left in the requirement ('within a mission-critical environment')",
    "name_not_taken": "a name kept with a word that adds nothing ('SQL Domain')",
    "bare_verb": "a verb alone, its object lost ('take')",
    "names_in_extra": "named examples set aside while the requirement names nothing",
    "shared_tail_lost": "a word cut from the noun it shared ('national' beside 'EU financing mechanisms')",
    "head_glued": "the item's first requirement glued in front of the others ('AI literacy automation')",
    "verb_run_left": "activities left in front of the object ('training and evaluating ML models')",
    "roles_in_key": "several roles left in one requirement ('Data Engineer or Data Scientist')",
    # rules 0.4.7, from our reading of batch 5
    "object_in_extra": "the requirement left empty, what is asked set aside after a word the rules did not know",
    "names_dropped": "names written before a category ('and frameworks like') left out",
    # rules 0.4.7, from the user's review of batch 5
    "level_as_core": "a level or kind word ('recent', 'extensive') read as what is asked",
    "years_left": "years written in a way the rules did not read ('1 year minimum')",
    "availability_lost": "a willingness to travel or relocate reduced to the place",
    "role_cut": "a role cut to its job word, seniority words read as roles ('Senior, Staff or Lead')",
    "other": "no rule names it",
}



def input_cause(item: str, translated: bool) -> str | None:
    """What the employer's text looked like, when it is a known cause of errors."""
    if item and not any(ch.isupper() for ch in item) and any(ch.isalpha() for ch in item):
        return "lowercase"
    # Not punctuation: since rules 0.2.0 a bullet, a closing mark or doubled
    # spaces change no output (`invariance.py`: 0.0% of 1,070 items), so they
    # cannot be why an output is wrong.
    if translated:
        return "translation"
    if len(item) > config.LONG_SEGMENT_CHARS:
        return "long_item"
    return None


def _words(s: str) -> list[str]:
    return re.findall(r"[^\W\d_][\w'-]*", s.lower())


def split_flags(reqs: list[dict]) -> list[tuple[str, str]]:
    """(error, mechanism) for each requirement of ONE item that looks damaged.

    `DETECTORS`, in order; a requirement takes the first that fires:

    * ``list_not_separated`` — route `llm`: the rules saw more than one
      requirement and could not separate them;
    * ``split_looked_broken`` — route `damaged`: kept whole on purpose;
    * ``joined_by_and_or`` — the atom still reads `X and Y` (`looks_compound`);
    * ``filler`` / ``complement_lost`` — a one-word atom that is filler, or
      a relational noun with nothing after it (`flag_bare_head`);
    * ``head_not_repeated`` — the item split into several, a sibling carries
      a head (`experience`, `knowledge`), this one has none and is at most
      two words long: `Experience with AWS` beside a bare `Azure`.
    """
    out = []
    headed = any(r.get("head_group") for r in reqs) and len(reqs) > 1
    for r in reqs:
        atom, words = r.get("atom", ""), _words(r.get("atom", ""))
        if r.get("route") == "llm":
            out.append(("merged", "list_not_separated"))
        elif r.get("route") == "damaged":
            out.append(("merged", "split_looked_broken"))
        elif _STILL_COMPOUND_RE.search(atom) and len(words) > 3:
            out.append(("merged", "joined_by_and_or"))
        elif len(words) == 1 and words[0] in _BARE_FILLER:
            out.append(("fragment", "filler"))
        elif len(words) == 1 and words[0] in _RELATIONAL_HEADS:
            out.append(("fragment", "complement_lost"))
        elif headed and not r.get("head_group") and len(words) <= 2:
            out.append(("fragment", "head_not_repeated"))
        else:
            out.append(None)
    return out


DETECTORS = ["list_not_separated", "split_looked_broken", "joined_by_and_or", "filler",
             "complement_lost", "head_not_repeated"]


def split_suspects(postings: list[dict], examples: int = 3) -> dict:
    """Every requirement of a run, read by `split_flags`: where to look, NOT errors (see the module)."""
    count, ex = Counter(), defaultdict(list)
    items = reqs = 0
    for p in postings:
        by_item = defaultdict(list)
        for r in p.get("requirements") or []:
            by_item[r.get("item_idx")].append(r)
        for rs in by_item.values():
            items += 1
            reqs += len(rs)
            item = rs[0].get("item", "")
            why = input_cause(item, bool(rs[0].get("translated")))
            for r, f in zip(rs, split_flags(rs)):
                if f is None:
                    continue
                key = ("splitting", "requirement", f[0], why or f[1])
                count[key] += 1
                if len(ex[key]) < examples:
                    ex[key].append({"item": item, "atom": r.get("atom", ""), "mechanism": f[1]})
    return {"of": {"items": items, "requirements": reqs}, "counts": count, "examples": ex}


# The inspector agent (2026-11-13). Reading the API test of that day by hand
# found degrees read wrong in six ways that no check looked for; each was
# fixed in rules 0.4.1, and these two tests watch every later run for the
# same kinds. Unlike the shape rules above they test a property, not a
# guess: an atom that opens on a degree and is not education was not read,
# and a field that is itself a degree, an experience or a language is not a
# field. Detected only — a fix is a rules version (the archivist's catalogue).
INSPECTOR = "inspector"
DEGREE_DETECTORS = ["degree_not_read", "degree_field_odd"]
# Since rules 0.4.2 also the degree names and the words in front that the
# first batch of new postings showed unread (`BA/BS Degree in STEM`, `HBO or
# WO degree`, `B.E. in X`, `Relevant bachelor's or master's degree ...`): the
# detector named only the spellings the rules knew, so it could not see what
# they missed.
_DEGREE_OPENS_RE = re.compile(
    r"^(?:(?:a|an|the|relevant|related|completed|finished|university|academic|technical|recognised|recognized|"
    r"accredited|formal|appropriate|suitable|advanced|higher)\s+)*"
    r"(?:(?:bachelor|master)(?:'s|’s|s)?(?=\s+(?:degree|in|of)\b|$)|"
    r"(?:bachelor|master)(?:'s|’s)(?!\w)|m\.?\s?sc\.?(?!\w)|b\.?\s?sc\.?(?!\w)|ph\.?\s?d\.?(?!\w)|mba(?!\w)|"
    r"doctorate(?!\w)|bac\s*\+\s*\d|(?-i:B\.?[AS]\.?|M\.?[AS]\.?)(?=\s*(?:/|degree\b|in\b|or\b|$))|"
    r"b\.\s?e\.|[bm]\.?\s?tech\b|bba(?!\w)|mca(?!\w)|hbo(?!\w)|(?-i:WO)(?=[\s/-]+(?:degree|level|niveau)\b)|"
    r"associate(?:'s|’s)?\s+degree|(?:under|post)graduate\s+degree)", re.I)
_DEGREE_IN_FIELD_RE = re.compile(r"^(?:bachelor|master|m\.?\s?sc|b\.?\s?sc|ph\.?\s?d|mba|degree|diploma)(?!\w)|"
                                 r"^(?:or|and|with)\b", re.I)


def degree_flag(r: dict) -> str | None:
    """The inspector's two tests on one requirement; the first that fires, or None."""
    atom = r.get("atom") or ""
    if r.get("space") != "education":
        return "degree_not_read" if _DEGREE_OPENS_RE.match(atom) else None
    core = r.get("core") or ""
    field = core.split(" in ", 1)[1] if " in " in core else ""
    if not field:
        return None
    from karimi import normalise_req
    if _DEGREE_IN_FIELD_RE.match(field) or re.search(r"\bexperiences?\b", field, re.I) \
            or normalise_req.decompose(field).get("space") == "language":
        return "degree_field_odd"
    return None


# Since 2026-11-16 the inspector also watches the kinds batch 1 showed and no
# agent caught, found by hand: how much it is wanted left in the requirement
# (`Python is a plus`; `Desirable experience in design` read as `Desirable`)
# and items left in another language. Each detector has its entry in the
# archivist's catalogue (`error_catalogue.json`), which says what it is, why,
# and whether a rules version fixed it.
_MARK = (r"desirable|advantageous|preferred|preferable|preferably|optional|optionally|beneficial|"
         r"nice[\s-]to[\s-]have|a\s+(?:big\s+|huge\s+)?plus|plus|bonus|ideally|an?\s+advantage")
_MARK_ONLY_RE = re.compile(rf"^(?:{_MARK})(?:\s+to\s+have)?\s*(?::.*)?$", re.I)
_MARK_OPENS_RE = re.compile(rf"^(?:{_MARK})\b", re.I)


def optional_flag(r: dict) -> str | None:
    """`optional_head`: the atom opens on how much it is wanted and the core kept
    only that; `optional_tail`: the core still closes on it."""
    from karimi import normalise_req

    core = (r.get("core") or "").strip()
    if not core:
        return None
    if _MARK_OPENS_RE.match(r.get("atom") or "") and _MARK_ONLY_RE.match(core):
        return "optional_head"
    if normalise_req.strip_optional(core) != core:
        return "optional_tail"
    return None


# Found by the explorer on batch 1 (Gemini, 2026-11-16): words that add
# nothing left in the requirement, which no rule takes off. Its own marker
# list, wider than `strip_optional`'s: a detector built on the fix would be
# blind exactly where the fix is. Each read on batch 1 under rules 0.4.2.
# `plus`, `bonus` and `asset` only after an article or a verb: `Basic Plus` is a
# course's name (read on batch 2, 2026-11-17); a bare `advantage` is the German
# `von Vorteil`.
_WANT = (r"(?:(?:is|are|as|will\s+be|would\s+be|being|considered|seen\s+as|also)\s+)*an?\s+"
         r"(?:(?:big|huge|strong|added|great|real|definite|clear|additional|distinct|significant|express)\s+)?"
         r"(?:plus|advantage|bonus|asset)|(?:is|are|as)\s+(?:a\s+)?plus|(?:of\s+)?advantage|"
         r"preferred|preferable|desirable|advantageous|beneficial|"
         r"nice[\s-]to[\s-]have|welcome|appreciated|valued|desired")
_WANT_TAIL_RE = re.compile(rf"[\s,;:(–—-]+(?:{_WANT})\s*\)?\s*[.!]?$", re.I)
# `if required`, `when required` are a condition, not a marker
_REQUIRED_TAIL_RE = re.compile(r"(?<!\bif)(?<!\bwhen)(?<!\bas)(?<!\bwhere)[\s,;:(–—-]+(?:is\s+|are\s+)?"
                               r"(?:required|mandatory|a\s+must|must)\s*\)?\s*[.!]?$", re.I)
_SIMILAR_TAIL_RE = re.compile(r"\s+or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:similar|equivalent|comparable|related|"
                              r"relevant)(?:\s+\w+)?\s*$", re.I)
# not `expert` (`domain expert` is a role) and not `Visual Basic`
_LEVEL_TAIL_RE = re.compile(r"(?<=\w)(?<!\bvisual)[\s,(–-]+(?:beginner|basic|intermediate|advanced|proficient|"
                            r"elementary|upper[\s-]intermediate)\s*\)?$", re.I)
_HIGHER_EDUCATION_RE = re.compile(r"^(?:completed\s+)?(?:higher|tertiary|university)\s+education\b", re.I)


def word_kept_flag(r: dict) -> str | None:
    """A word that adds nothing left at the end of the core: how much it is
    wanted in words the rules do not know, `required`, `or similar role`, a level."""
    from karimi import normalise_req

    core = (r.get("core") or "").strip()
    if not core:
        return None
    if _WANT_TAIL_RE.search(core) and normalise_req.strip_optional(core) == core:
        return "optional_marker_unknown"
    if _REQUIRED_TAIL_RE.search(core):
        return "required_left"
    if r.get("space") != "language" and _SIMILAR_TAIL_RE.search(core):
        return "or_similar_left"
    if r.get("space") != "language" and _LEVEL_TAIL_RE.search(core):
        return "level_left"
    return None


def _foreign(text: str) -> bool:
    """Not English, read off the text itself: a non-Latin letter, the word lists
    deciding another language, or two words with letters outside ASCII. Not the
    translator's own test (`translate.item_code`): a detector sharing it would
    be blind exactly where the translator is."""
    from karimi import language

    if any(ch.isalpha() and "LATIN" not in unicodedata.name(ch, "") for ch in text):
        return True
    lang = language.detect(text)[0]
    if lang and lang != "English":
        return True
    return sum(any(ord(c) > 127 for c in w) for w in re.findall(r"[^\W\d_]+", text)) >= 2


def translation_flag(r: dict) -> str | None:
    """`untranslated`: kept as written although not English; `translation_failed`:
    translated, and what came out is still not English."""
    from . import translate

    atom = r.get("atom") or ""
    if r.get("translated"):
        return "translation_failed" if _foreign(atom) else None
    if _foreign(atom) or translate.item_code(r.get("item") or "") is not None:
        return "untranslated"
    return None


# Rules 0.4.4, from the user's review of batch 2 (25 of 100 wrong, and the
# inspector had caught none): the SHAPES those errors had, read off the result
# alone, so they are found without a person next time.
_EDGE_PREP_RE = re.compile(r"^(?:on|for|with|in|of|at|as|to|by|from)\s+\S|\s(?:on|for|with|in|of|at|as|to|by|from)$",
                           re.I)


def shape_flag(r: dict) -> str | None:
    """`lead_punctuation`: an atom cut on the wrong side of a comma; `comma_in_key`:
    a list left in one requirement; `edge_preposition`: a preposition that names
    nothing at either edge of the core (`on CPaaS`, `development for`)."""
    atom = (r.get("atom") or "").strip()
    core = (r.get("core") or "").strip()
    if re.match(r"^[,;:]", atom):
        return "lead_punctuation"
    outside = re.sub(r"\([^()]*\)", "", core)
    if r.get("space") != "education" and ("," in outside or re.search(r"\s(?:and|&)\s", outside)):
        # only a list of NAMES: coordinated verbs and adjectives before one
        # noun are one ask by the count conventions (2026-10-29, 2026-10-30),
        # and flagging them made 3 of 4 flags wrong on batch 3
        from karimi import normalise_req
        if len(normalise_req._name_runs(outside)) >= 2:
            return "comma_in_key"
    if r.get("space") != "education" and _EDGE_PREP_RE.search(core):
        return "edge_preposition"
    if r.get("space") != "education" and _FRAME_LEFT_RE.match(core):
        return "frame_left"
    return None


# Rules 0.4.5, from the user's review of batch 3: a frame left in front of what
# is asked. Written apart from the rules' own patterns so that a variant they
# miss is still seen (`Keen interest towards`, `coding in`, `leveraging`).
_FRAME_LEFT_RE = re.compile(
    r"^(?:(?:demonstrated|strong|genuine|keen)\s+)?interest\s+(?:in|for|towards?)\b|"
    r"^(?:programming|coding|scripting)\s+(?:with|in|using)\b|"
    r"^(?:using|leveraging|applying|utili[sz]ing|exhibit|demonstrate|possess)\s|"
    r"^(?:popular|modern|scalable|robust|cutting-edge|state-of-the-art|latest)\s|"
    r"^(?:the\s+)?concepts?\s+of\b|"
    r"^(?:registered|enrolled|successful(?:ly)?)\s+(?:completion\s+of\s+)?stud|"
    # batch 4's review: `Spirit of analysis`, `Easy contact with colleagues`, `Wide range of knowledge`
    r"^(?:spirit|sense|wide\s+range|breadth)\s+(?:of|to)\b|^easy\s+\w+\s+with\b", re.I)


INSPECTOR_DETECTORS = {
    # detector -> (stage, error kind), in the order the first that fires is taken
    "lead_punctuation": ("splitting", "fragment"),
    "comma_in_key": ("splitting", "merged"),
    "duplicate_key": ("normalisation", "wrong_group"),
    "edge_preposition": ("normalisation", "word_kept"),
    "frame_left": ("normalisation", "word_kept"),
    "language_as_skill": ("normalisation", "wrong_group"),
    "context_left": ("normalisation", "word_kept"),
    "name_not_taken": ("normalisation", "word_kept"),
    "bare_verb": ("splitting", "fragment"),
    "names_in_extra": ("splitting", "merged"),
    "shared_tail_lost": ("splitting", "fragment"),
    "head_glued": ("splitting", "over_split"),
    "verb_run_left": ("normalisation", "word_kept"),
    "roles_in_key": ("splitting", "merged"),
    "degree_not_read": ("normalisation", "wrong_degree"),
    "degree_field_odd": ("normalisation", "wrong_degree"),
    "optional_head": ("normalisation", "optional_kept"),
    "optional_tail": ("normalisation", "optional_kept"),
    "untranslated": ("translation", "not_translated"),
    "translation_failed": ("translation", "not_translated"),
    "degree_higher_education": ("normalisation", "wrong_degree"),
    "optional_marker_unknown": ("normalisation", "optional_kept"),
    "required_left": ("normalisation", "word_kept"),
    "or_similar_left": ("normalisation", "word_kept"),
    "level_left": ("normalisation", "word_kept"),
    # rules 0.4.7, from our reading of batch 5 (`New project/PIANO_SVILUPPO.md`)
    "object_in_extra": ("normalisation", "object_lost"),
    "names_dropped": ("splitting", "dropped"),
    # rules 0.4.7, from the user's review of batch 5
    "level_as_core": ("normalisation", "word_kept"),
    "years_left": ("normalisation", "word_kept"),
    "availability_lost": ("normalisation", "object_lost"),
    "role_cut": ("normalisation", "object_lost"),
}


# Rules 0.4.6, from the user's review of batch 4 (2026-11-18): 37 of 100 wrong,
# and the inspector had flagged 2 of them. Each shape below is one kind of
# those 37, read off the result alone. Written apart from the rules that fix
# them, so a variant the rules miss is still seen. Each was measured on that
# review before it entered the colour (`New project/score_review_detectors.py`).
_CEFR_ONLY_RE = re.compile(r"^(?:[ABC][12](?:\s*[/+–-]\s*[ABC]?[12])?|native|fluent|sufficient|intermediate)$", re.I)
_CONTEXT_RE = re.compile(
    r"\s(?:within\s|in\s+(?:an?|the)\s+[\w\s/-]{0,40}?environments?\b|with\s+(?:large|complex)\s|"
    r"to\s+(?:interact|work|communicate|collaborate|enhance|ensure|support|drive|deliver)\b|"
    r"for\s+(?:large|complex)\s|in\s+the\s+field\s+of\s)|"
    # `testing domain, with a minimum of 3 years in test automation`: a second ask
    r",\s*with\s+(?:a\s+)?(?:minimum|at\s+least)\b|"
    # `SonarQube for CI/CD and code quality`: a name and what it is for
    r"(?-i:^\s(?!(?:Eye|Bias|Appetite|Desire|Passion|Love|Flair|Talent|Feel|Nose|Knack|Hunger|Drive|Taste)\b)"
    r"[A-Z][\w./+#-]*\s+for\s)", re.I)
# coordinated gerunds before one object, or a second activity glued on
_VERB_RUN_RE = re.compile(r"^\w+ing\s+(?:and|or|&)\s+\w+ing\b|\sand\s+the\s+\w+(?:ion|ment|ery)$", re.I)
_VAGUE_HOLDER_RE = re.compile(r"\b(?:affinity|savvy|literacy|exposure)\b", re.I)
_GENERIC_TAIL_RE = re.compile(
    r"\s(?:domain|methodolog(?:y|ies)|affinity|software\s+development|development\s+experience|"
    r"environments?|landscape|ecosystem|stack|world|universe)$", re.I)
_BARE_VERBS = {"take", "understand", "maintain", "evaluate", "validate", "improve", "manage", "develop", "build",
               "design", "create", "lead", "drive", "deliver", "implement", "support", "ensure", "work",
               "handle", "perform", "analyse", "analyze", "solve", "write", "train", "test", "run", "own"}


def review_flag(r: dict) -> str | None:
    """`language_as_skill`: a language requirement read as its level or as a skill;
    `context_left`: where or what for, left in the key; `roles_in_key`: roles in
    alternative left in one key; `name_not_taken`: a name
    with a generic word that adds nothing (`SQL Domain`); `bare_verb`: a verb
    alone (`take`); `names_in_extra`: a bracket of names set aside while the
    core names nothing."""
    from karimi import atomise as atom, normalise_req

    core = (r.get("core") or "").strip()
    extra = r.get("extra") or ""
    space = r.get("space")
    if space == "language":
        return None
    if core and _CEFR_ONLY_RE.match(core):
        return "language_as_skill"
    if core and re.search(rf"\b(?:{atom._LANGS})\b", core, re.I) and re.search(
            r"\b(?:understanding|level|proficiency|command|knowledge|fluency)\b", core, re.I):
        return "language_as_skill"
    if not core or space == "education":
        return None
    if _CONTEXT_RE.search(f" {core}"):
        return "context_left"
    if re.search(r"\b(?:degree(?!\s+of\b)|diploma|bachelor'?s?|ph\.?d)\b|"
                 r"(?<!scrum\s)(?<!agile\s)\bmaster'?s?\b(?!\s+(?:data|production|planning|scheduling|schedules?|file|record))",
                 core, re.I):
        return "degree_not_read"
    tail = _GENERIC_TAIL_RE.search(core)
    if tail and normalise_req._name_runs(core[: tail.start()]):
        return "name_not_taken"
    words = core.split()
    first = words[0].lower()
    if len(words) <= 2 and (first in _BARE_VERBS and (len(words) == 1 or words[1].lower() in ("and", "on"))
                            or (first.endswith("ly") and len(words) == 2 and words[1].lower() in _BARE_VERBS)):
        return "bare_verb"
    if _VERB_RUN_RE.search(core):
        return "verb_run_left"
    # Roles in alternative left in one key (the user's call, 2026-11-18): the
    # same role is one requirement, different roles are separate ones
    if re.search(r",|\bor\b|\band/or\b", core) and len(atom.role_alternatives(core)) > 1:
        return "roles_in_key"
    held = normalise_req._name_runs(re.sub(r"[()]", " ", extra).replace(" / ", ", "))
    if not normalise_req._name_runs(core) and (len(held) >= 2 or (held and _VAGUE_HOLDER_RE.search(core))):
        return "names_in_extra"
    return None


def item_flags(reqs: list[dict]) -> dict[int, str]:
    """Shapes seen only across the atoms of ONE item, by atom position:
    `shared_tail_lost` — one atom is a lone word that the next atom's last noun
    completes (`national` beside `EU financing mechanisms`); `head_glued` — the
    item's first key glued in front of three or more others (`AI literacy
    prompt engineering`, `AI literacy automation`)."""
    out: dict[int, str] = {}
    keys = [(r.get("core") or "").strip() for r in reqs]
    for i, k in enumerate(keys):
        if r_space(reqs[i]) or not k:
            continue
        # an adjective alone, never a noun: `documentation`, `governance` stand by themselves
        if len(k.split()) == 1 and k[:1].islower() and i + 1 < len(keys) and len(keys[i + 1].split()) >= 2 \
                and k.lower() not in _SOFT_SINGLE \
                and re.search(r"(?:al|ic|ive|ary|ous|ar)$", k):
            out[i] = "shared_tail_lost"
    # `names_dropped` (rules 0.4.7, batch 5): names written before a category that
    # lists more (`HTML5, CSS3, JavaScript, and frameworks like Angular`) in no atom
    item = (reqs[0].get("item_split") or reqs[0].get("item") or "") if reqs else ""
    from karimi import atomise as _atom
    m = _atom._CATEGORY_INTRO_RE.search(item)
    if m and m.start() > 0:
        said = " ".join((r.get("atom") or "") for r in reqs)
        before = item[:m.start()]
        names = [x.group() for x in re.finditer(r"(?<![\w-])[A-Z][\w.+#/-]*[\w+#]", before) if x.start() > 0]
        # the name right before the category is its kind (`ML frameworks such as`),
        # unless a comma or `and` stands between them
        if names and not re.match(r"[,\s]*(?:,|and\b|or\b|plus\b)", m.group(0)) and before.rstrip().endswith(names[-1]):
            names = names[:-1]
        lost = [n for n in names if n not in said and n.lower() not in ("experience", "knowledge", "proficiency",
                                                                          "strong", "good", "solid", "excellent")]
        if lost:
            out.setdefault(0, "names_dropped")
    first = keys[0] if keys else ""
    if first and len(first.split()) >= 2:
        glued = [i for i, k in enumerate(keys[1:], 1) if k.startswith(first + " ")]
        if len(glued) >= 3:
            for i in glued:
                out.setdefault(i, "head_glued")
    return out


_SOFT_SINGLE = {"communication", "teamwork", "autonomy", "collaboration", "leadership", "creativity", "flexibility",
                "curiosity", "reliability", "analytical", "organized", "proactive", "motivated", "responsibility",
                "writing", "programming", "troubleshoot", "integration", "architecture", "security", "testing"}


def r_space(r: dict) -> bool:
    return r.get("space") in ("language", "education")


def inspector_flag(r: dict) -> str | None:
    """The first of the inspector's tests that fires on one requirement, or None."""
    if r.get("space") != "education" and _HIGHER_EDUCATION_RE.match(r.get("atom") or ""):
        hit = "degree_higher_education"
    else:
        hit = None
    return translation_flag(r) or degree_flag(r) or hit or optional_flag(r) or word_kept_flag(r) \
        or shape_flag(r) or review_flag(r) or object_flag(r) or review5_flag(r)


_LEVEL_AS_CORE_RE = re.compile(
    r"^(?:recent|extensive|proven|solid|deep|strong|good|basic|excellent|confirmed|specific|actual|additional|"
    r"academic|implementation|production|significant|considerable|practical|previous|prior)$", re.I)
_JOB_WORDS = {"engineer", "developer", "architect", "manager", "analyst", "consultant", "scientist", "designer",
              "administrator", "specialist", "lead"}


def review5_flag(r: dict) -> str | None:
    """Shapes of the user's review of batch 5 (2026-11-23), read off the result alone."""
    core = (r.get("core") or "").strip()
    atom = r.get("atom") or ""
    if not core or r_space(r):
        return None
    if _LEVEL_AS_CORE_RE.match(core):
        return "level_as_core"
    if re.match(r"^(?:minimum|maximum|min\.?|max\.?|at\s+least)\b", core, re.I) \
            or re.search(r"\b\d+\+?\s*(?:years?|yrs?)\b", core, re.I):
        return "years_left"
    if re.search(r"\swith\s+(?:an?\s+)?(?:(?:strong|particular|special|clear)\s+)?focus\s+on\s", f" {core}", re.I):
        return "context_left"
    if re.match(r"^(?:willing(?:ness)?|ready|readiness|availability)\s+to\s+(?:travel|relocate)\b", atom, re.I) \
            and not re.search(r"\b(?:travel|relocat)", core, re.I):
        return "availability_lost"
    if core.lower() in _JOB_WORDS and re.search(rf"\b[A-Z][\w/-]*\s+{re.escape(core)}\b", atom):
        return "role_cut"
    return None


def object_flag(r: dict) -> str | None:
    """`object_in_extra` (rules 0.4.7, batch 5): a counted requirement whose key is
    empty while `extra` still holds what is asked (`High proficiency in Python`
    came out empty, Python in `extra`; 50 of 137 empty keys). `equivalent
    experience` is empty on purpose and has nothing in `extra`."""
    if r.get("counted") is False or (r.get("core") or "").strip() or r_space(r):
        return None
    extra = (r.get("extra") or "").strip()
    if re.match(r"^(?:of|in|with|on|about)\s+\S", extra, re.I) or re.search(r"(?<![\w-])[A-Z][\w.+#/-]+", extra):
        return "object_in_extra"
    return None


def inspect(postings: list[dict], examples: int = 3) -> dict:
    """Every requirement of a run, read by `inspector_flag`: what the inspector agent detected."""
    count, ex = Counter(), defaultdict(list)
    reqs = 0
    for p in postings:
        seen = set()
        by_item: dict[int, list[int]] = defaultdict(list)
        rs = p.get("requirements") or []
        for j, r in enumerate(rs):
            by_item[r.get("item_idx", 0)].append(j)
        across = {}
        for idx in by_item.values():
            for pos_, f in item_flags([rs[j] for j in idx]).items():
                across[idx[pos_]] = f
        for j, r in enumerate(rs):
            reqs += 1
            f = inspector_flag(r) or across.get(j)
            # one key twice in one item: the rules keep it once since 0.4.4
            k = (r.get("item_idx"), r.get("key"))
            if f is None and r.get("key") and k in seen:
                f = "duplicate_key"
            seen.add(k)
            if f is None:
                continue
            stage, error = INSPECTOR_DETECTORS[f]
            key = (stage, "requirement", error, f)
            count[key] += 1
            if len(ex[key]) < examples:
                ex[key].append({"item": r.get("item", ""), "atom": r.get("atom", ""), "core": r.get("core", ""),
                                "key": r.get("key", "")})
    return {"of": {"requirements": reqs}, "counts": count, "examples": ex}


# A part marked optional the splitter did not recognise as one (an atom it
# recognises is already left uncounted: `atomise.counted`).
_OPTIONAL = re.compile(r"\b(?:ideally|preferably|preferred|optionally|idealerweise|vorzugsweise|"
                       r"wünschenswert|von vorteil|idéalement|de préférence|un plus|"
                       r"preferibilmente|idealmente|gradit[oa]|bij voorkeur|pluspunt)\b", re.I)
_ALTERNATIVE = re.compile(r"\b(?:or|oder|ou|o|of|eller)\b|/", re.I)


def split_profile(rows: list[dict]) -> dict:
    """Splitting errors on hand-counted items: the library's count against the human's.

    ``rows``: one per item, with `item`, `translated`, `human` (the hand
    count) and `requirements` (the library's, as dicts). An item counted
    FEWER than by hand is `merged`, MORE is `over_split`; its cause is the
    input's, else the shape rule that fired (`split_flags`), else for an
    over-split the part counted against the guide (`optional_part`,
    `alternatives`), else `other`.
    """
    from karimi import atomise as atom

    count, n = Counter(), 0
    for r in rows:
        n += 1
        reqs = r["requirements"]
        lib = sum(bool(q.get("counted", True)) for q in reqs)
        if lib == r["human"]:
            continue
        error = "merged" if lib < r["human"] else "over_split"
        why = input_cause(r["item"], r["translated"])
        if why is None:
            flags = [f for f in split_flags(reqs) if f]
            if error == "merged":
                why = next((f[1] for f in flags if f[0] == "merged"), "other")
            elif any(f[0] == "fragment" for f in flags):
                why = next(f[1] for f in flags if f[0] == "fragment")
            elif atom.nice_to_have(r["item"]) or _OPTIONAL.search(r["item"]):
                why = "optional_part"
            elif _ALTERNATIVE.search(r["item"]):
                why = "alternatives"
            else:
                why = "other"
        count[("splitting", "requirement", error, why)] += 1
    return {"of": {"items_hand_counted": n}, "counts": count}


def normalise_errors(judged, examples: int = 3) -> dict:
    """The judge's flags (`check.judge`), by kind and cause; ``judged`` needs `item`, `translated`."""
    from . import tester

    count, ex, of = Counter(), defaultdict(list), Counter()
    for r in judged.itertuples():
        if r.judge_same is None or r.judge_same != r.judge_same:      # unanswered (None or NaN)
            continue
        obj = "role" if r.kind == "role" else "requirement"
        of[obj] += 1
        if bool(r.judge_same):
            continue
        error = {"group": "wrong_group", "topic": "wrong_topic", "variant": "wrong_role"}[r.sample]
        g = tester.group(r.kind, r.a, r.b)
        mech = {"narrower_broader": "narrower_or_broader"}.get(g, g)
        why = input_cause(getattr(r, "item", "") or "", bool(getattr(r, "translated", False))) or (
            mech if mech in CAUSES else "other")
        key = ("normalisation", obj, error, why)
        count[key] += 1
        if len(ex[key]) < examples:
            ex[key].append({"a": r.a, "b": r.b, "item": getattr(r, "item", ""), "mechanism": mech})
    return {"of": {"judged_requirements": of["requirement"], "judged_roles": of["role"]},
            "counts": count, "examples": ex}


def table(*parts: dict | None) -> dict:
    """Error rows with what they are out of, from `split_profile` or `normalise_errors`. No text."""
    rows, of = [], {}
    for part in parts:
        of.update((part or {}).get("of") or {})
        for (stage, obj, error, cause), n in sorted((part or {}).get("counts", {}).items(),
                                                     key=lambda x: -x[1]):
            rows.append({"stage": stage, "object": obj, "error": error, "cause": cause, "count": n})
    return {"of": of, "rows": rows}


def examples(*parts: dict | None) -> list[dict]:
    """The private side: a few cases per row, for the job's own `check.json`."""
    out = []
    for part in parts:
        for (stage, obj, error, cause), xs in (part or {}).get("examples", {}).items():
            out.append({"stage": stage, "object": obj, "error": error, "cause": cause, "cases": xs})
    return out
