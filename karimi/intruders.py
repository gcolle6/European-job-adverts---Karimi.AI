"""Finding members that do not belong in their group, when geometry cannot.

**Why this is not a geometry problem.** A group forms because its members sit
close together in the embedding space, so a member that "does not belong"
is, by construction, one the embedding thought belonged. Two detectors were built
on that space and both failed: splitting each group in two put the worst known
case at the 23rd percentile of separation, and cross-checking the group's label
against its members' types missed it because the label was typed with the same
embedding that caused the error. **You cannot find an embedding's mistake with
that embedding's own geometry.**

What the failures have in common is a word with two senses. Measured on a random
draw of 40 groups, **3 contained an intruder of this kind** — roughly one group
in thirteen:

    Logistics experience      <- "Comfortable shipping code"   (release vs freight)
    Multicultural environment <- "Familiarity with DevOps culture"
    Writing skills            <- "A track record of publications in AI/ML"

None is a product name, so a product-name list would have caught none of them.

**Which error to prefer.** A flagged member that turns out fine costs a reader
seconds to dismiss; a missed one stays in the published atlas. So the prompt is
told to flag on suspicion, and the output is a **shortlist for a person**, never
a decision applied automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROMPT_VERSION = "intruder-v1"

SYSTEM_PROMPT = """\
You check whether a group of job-advert requirements is really about ONE thing.

Each group has a name and a list of numbered example phrases taken from real
adverts. The name was written by a model and can be wrong — judge by the phrases.

Find phrases that do NOT belong with the majority of the others.

What you are looking for, above all, is **a word with two senses** pulling an
unrelated phrase into the group. Real examples that were missed:

  - "Comfortable shipping code" inside a LOGISTICS group — shipping means
    releasing software here, not freight.
  - "Familiarity with DevOps culture" inside a group about working in a
    MULTICULTURAL environment — culture means engineering practice, not nation.
  - "A track record of publications" inside a group about WRITING SKILLS —
    publishing research is not drafting documents.

Other things worth flagging: a named product or tool sitting among soft skills,
an occupation among attributes, a qualification among competences.

Do NOT flag a phrase merely for being in another language, for being short, or
for being a different wording of the same demand. `SQL knowledge` and
`Kenntnisse in SQL` belong together.

Flag on suspicion: a human reviews everything you return, so a wrong flag is
cheap and a missed intruder is not.

Return ONLY: {"groups": [{"id": <int>, "intruders": [<phrase numbers>]}]}
Use an empty list when the group is coherent."""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "intruder_report",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "intruders": {"type": "array", "items": {"type": "integer"}},
                        },
                        "required": ["id", "intruders"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["groups"],
            "additionalProperties": False,
        },
    },
}


def _load_cache(path) -> dict:
    cache = {}
    p = Path(path)
    if not p.exists():
        return cache
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("prompt_version") == PROMPT_VERSION:
                cache[int(rec["cluster"])] = rec
    return cache


def scan(groups: pd.DataFrame, members: dict, client, cache_path,
         model: str = "gpt-5.4-mini-2026-03-17", per_request: int = 8,
         n_members: int = 12) -> pd.DataFrame:
    """Flag members that look out of place, group by group.

    ``groups`` needs `cluster` and `label`; ``members`` maps a cluster id to its
    example phrases. Cached per group, so a re-run costs nothing and a changed
    prompt version invalidates cleanly.
    """
    cache = _load_cache(cache_path)
    todo = [r for r in groups.itertuples(index=False) if int(r.cluster) not in cache]
    in_tok = out_tok = failures = 0
    cp = Path(cache_path)
    cp.parent.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(todo), per_request):
        chunk = todo[start:start + per_request]
        payload = []
        for r in chunk:
            mem = list(members.get(int(r.cluster), []))[:n_members]
            payload.append({
                "id": int(r.cluster),
                "group_name": str(r.label),
                "phrases": {str(i): m for i, m in enumerate(mem)},
            })

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            response_format=RESPONSE_SCHEMA,
        )
        if resp.usage:
            in_tok += resp.usage.prompt_tokens or 0
            out_tok += resp.usage.completion_tokens or 0

        try:
            got = {int(g["id"]): list(g["intruders"])
                   for g in json.loads(resp.choices[0].message.content)["groups"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            failures += 1
            continue

        with open(cp, "a", encoding="utf-8") as fh:
            for r in chunk:
                cid = int(r.cluster)
                if cid not in got:
                    continue
                mem = list(members.get(cid, []))[:n_members]
                flagged = [mem[i] for i in got[cid] if isinstance(i, int) and 0 <= i < len(mem)]
                rec = {"cluster": cid, "prompt_version": PROMPT_VERSION,
                       "label": str(r.label), "intruders": flagged,
                       "n_members_shown": len(mem)}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cache[cid] = rec

    rows = [cache.get(int(c), {"cluster": int(c), "intruders": None})
            for c in groups["cluster"]]
    out = pd.DataFrame(rows)
    out.attrs["input_tokens"] = in_tok
    out.attrs["output_tokens"] = out_tok
    out.attrs["chunk_failures"] = failures
    out.attrs["from_cache"] = len(groups) - len(todo)
    return out


# --- second pass: why, if at all --------------------------------------------
#
# The first pass is told to flag on suspicion and it does: 536 of 617 groups
# come back with something, against the 3-in-40 rate a human review measured.
# As a shortlist that is useless — it asks a person to read almost everything.
#
# Re-asking the same question more strictly would just be the same judgement
# with a different temperature. This pass is structurally different: it asks for
# the **mechanism**, and gives "nothing wrong, the first pass over-flagged" as an
# explicit option rather than something the model has to volunteer. Naming a
# cause is a harder claim than expressing a doubt, and only one cause — a word
# with two senses — is the defect this project is hunting.

CONFIRM_VERSION = "intruder-confirm-v1"

CONFIRM_PROMPT = """A first pass flagged phrases as possibly not belonging in their group. It was
told to flag on suspicion, so most of its flags are wrong. Your job is to say
which are real and why.

For each flagged phrase choose exactly one reason:

  "two_senses"  a word in the phrase is being read in a different sense from the
                rest of the group. "Comfortable shipping code" in a logistics
                group: shipping means releasing software, not freight. This is
                the one that matters most.
  "wrong_kind"  it is a different KIND of thing from the group: a named product
                among soft skills, an occupation among personal attributes, a
                qualification among competences.
  "fine"        nothing is wrong — the first pass over-flagged. A phrase in
                another language, a longer or shorter wording, or a near
                synonym is FINE.

Default to "fine". Most flags are wrong and saying so is the useful answer.

Return ONLY:
{"groups": [{"id": <int>, "verdicts": [{"phrase": "<exact text>", "reason": "two_senses|wrong_kind|fine"}]}]}"""

CONFIRM_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "intruder_confirmation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "verdicts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "phrase": {"type": "string"},
                                        "reason": {"type": "string",
                                                   "enum": ["two_senses", "wrong_kind", "fine"]},
                                    },
                                    "required": ["phrase", "reason"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["id", "verdicts"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["groups"],
            "additionalProperties": False,
        },
    },
}


def confirm(flagged: pd.DataFrame, client, cache_path,
            model: str = "gpt-5.4-mini-2026-03-17", per_request: int = 8) -> pd.DataFrame:
    """Second pass over the first pass's flags: which are real, and why.

    ``flagged`` needs `cluster`, `label` and `intruders` (a list of phrases).
    Returns one row per flagged phrase with its reason.
    """
    cache = {}
    cp = Path(cache_path)
    if cp.exists():
        with open(cp, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("prompt_version") == CONFIRM_VERSION:
                    cache[int(rec["cluster"])] = rec["verdicts"]

    todo = [r for r in flagged.itertuples(index=False) if int(r.cluster) not in cache]
    in_tok = out_tok = failures = 0
    cp.parent.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(todo), per_request):
        chunk = todo[start:start + per_request]
        payload = [{"id": int(r.cluster), "group_name": str(r.label),
                    "flagged_phrases": list(r.intruders)} for r in chunk]
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": CONFIRM_PROMPT},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            response_format=CONFIRM_SCHEMA,
        )
        if resp.usage:
            in_tok += resp.usage.prompt_tokens or 0
            out_tok += resp.usage.completion_tokens or 0
        try:
            got = {int(g["id"]): g["verdicts"]
                   for g in json.loads(resp.choices[0].message.content)["groups"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            failures += 1
            continue
        with open(cp, "a", encoding="utf-8") as fh:
            for r in chunk:
                cid = int(r.cluster)
                if cid not in got:
                    continue
                rec = {"cluster": cid, "prompt_version": CONFIRM_VERSION,
                       "label": str(r.label), "verdicts": got[cid]}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cache[cid] = got[cid]

    rows = []
    for r in flagged.itertuples(index=False):
        for v in cache.get(int(r.cluster), []):
            rows.append({"cluster": int(r.cluster), "label": str(r.label),
                         "phrase": v.get("phrase"), "reason": v.get("reason")})
    out = pd.DataFrame(rows)
    out.attrs["input_tokens"] = in_tok
    out.attrs["output_tokens"] = out_tok
    out.attrs["chunk_failures"] = failures
    return out
