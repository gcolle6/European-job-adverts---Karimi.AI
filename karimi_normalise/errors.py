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
from collections import Counter, defaultdict

from karimi import config
from karimi.requirements import _BARE_FILLER, _RELATIONAL_HEADS, _STILL_COMPOUND_RE


# What went wrong, per stage and object.
ERRORS = {
    ("splitting", "requirement"): {
        "merged": "two or more requirements left in one",
        "over_split": "one requirement cut into more",
        "fragment": "a piece that is not a whole requirement",
    },
    ("normalisation", "requirement"): {
        "wrong_group": "placed in a group that is not the same requirement",
        "wrong_topic": "placed under a topic it does not belong to",
        "wrong_degree": "a degree read wrong",
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
# field. Detected only — a fix is a rules version (`RESOLVED_IN`).
INSPECTOR = "inspector"
DEGREE_DETECTORS = ["degree_not_read", "degree_field_odd"]
RESOLVED_IN = {"degree_not_read": "0.4.1", "degree_field_odd": "0.4.1"}
_DEGREE_OPENS_RE = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:(?:bachelor|master)(?:'s|’s|s)?(?=\s+(?:degree|in|of)\b|$)|"
    r"(?:bachelor|master)(?:'s|’s)(?!\w)|m\.?\s?sc\.?(?!\w)|b\.?\s?sc\.?(?!\w)|ph\.?\s?d\.?(?!\w)|mba(?!\w)|"
    r"doctorate(?!\w)|bac\s*\+\s*\d)", re.I)
_DEGREE_IN_FIELD_RE = re.compile(r"^(?:bachelor|master|m\.?\s?sc|b\.?\s?sc|ph\.?\s?d|mba|degree|diploma)(?!\w)",
                                 re.I)


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


def degree_suspects(postings: list[dict], examples: int = 3) -> dict:
    """Every requirement of a run, read by `degree_flag`: what the inspector agent detected."""
    count, ex = Counter(), defaultdict(list)
    reqs = 0
    for p in postings:
        for r in p.get("requirements") or []:
            reqs += 1
            f = degree_flag(r)
            if f is None:
                continue
            key = ("normalisation", "requirement", "wrong_degree", f)
            count[key] += 1
            if len(ex[key]) < examples:
                ex[key].append({"item": r.get("item", ""), "atom": r.get("atom", ""), "core": r.get("core", "")})
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
