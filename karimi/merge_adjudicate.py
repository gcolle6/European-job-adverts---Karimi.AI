"""Deciding whether two requirement groups are one demand, when nothing else can.

**Why this module exists.** Three independent signals were built for this
question and each fails on a different family, which is documented in
`cluster.merge_aliases` and in the defect register:

  * **centroid distance** merges `Microsoft Office` with `Microsoft Azure`, and
    at a looser threshold pulls 457 of 617 groups into one component;
  * **shared label names** cannot see past a shared frame — it rejects
    `Engineering degree` against itself, because `degree` is a descriptive word;
  * **member vocabulary** has no discrimination inside a frame family: run
    without guards it merged `German proficiency` with `Swedish fluency` and
    `Computer Science degree` with `Electronics degree`, since every language
    requirement is written out of the same words and so is every degree.

What remains after the guarded passes is exactly the set those signals cannot
judge: credential families, language families, and chains through hub groups such
as `Software development experience`. Deciding sameness there is a judgement, and
this project has already established where judgement belongs — the same split
used for ESCO anchoring, where cosine matched `Personal attributes` to *set
theory* at 0.975 confidence and an LLM reading the members fixed it.

**Which error to prefer, and why it is the opposite of the ESCO case.** Merging
two groups is **unrecoverable**: once pooled, nothing downstream can separate
them again, and the atlas silently loses a distinction it existed to show.
Leaving two fragments unmerged is recoverable and merely understates a group's
size — a cost already measured at 55–62% for named technologies. So the prompt is
instructed to prefer **different** when doubtful, and the merge set this produces
should be read as a lower bound.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROMPT_VERSION = "merge-v1"

SYSTEM_PROMPT = """\
You decide whether two groups of job-advert requirements describe THE SAME
demand from an employer, or two different demands.

For each item you get two groups, each with a name and example phrases taken
from real adverts. The names were written by a model and can be wrong — judge by
the example phrases, not by the names.

Answer true only when an employer asking for one would mean the same thing as an
employer asking for the other.

Rules:
1. Same DEMAND, not the same topic. `Leadership skills` and `Teamwork skills`
   are both about working with people and are different demands. `SQL knowledge`
   and `SQL skills` are one demand written twice.
2. A qualification is not experience. `Finance degree` and `Financial services
   experience` are different: one is a credential, the other is sector exposure.
3. Two different qualifications are different, however adjacent.
   `Computer Science degree` and `Electronics degree` are NOT the same, and
   neither are `Telecommunications degree` and `Electronics degree`. Do not merge
   degrees just because both are degrees.
4. Two different languages are different. `German proficiency` and `Swedish
   fluency` are NOT the same demand.
5. A generic group and a specific one are different when the specific one names
   something: `Relevant experience` is not `Software development experience`.
   But two phrasings of the same specific thing ARE the same:
   `AWS experience` and `AWS knowledge`.
6. Groups may be in any language; judge the meaning, not the language.
7. **Prefer false when doubtful.** Merging two different demands cannot be
   undone and destroys a distinction; leaving one demand split in two merely
   understates it. When you are unsure, answer false.

Return ONLY: {"decisions": [{"id": <int>, "same": <true|false>}]}"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "merge_decisions",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "same": {"type": "boolean"},
                        },
                        "required": ["id", "same"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["decisions"],
            "additionalProperties": False,
        },
    },
}


def _load_cache(path) -> dict:
    """Decisions already paid for, keyed by pair and prompt version."""
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
                cache[int(rec["pair_id"])] = rec
    return cache


def adjudicate(pairs: pd.DataFrame, members: dict, client, cache_path,
               model: str = "gpt-5.4-mini-2026-03-17",
               per_request: int = 10) -> pd.DataFrame:
    """Ask, pair by pair, whether two groups are one demand.

    ``pairs`` needs `cluster_a`, `cluster_b`, `label_a`, `label_b`; ``members``
    maps a cluster id to its example phrases, which carry far more signal than
    the labels — the labels are themselves model output and are what went wrong
    in `Messaging systems`.

    Cached by pair, so a re-run costs nothing and a changed prompt version
    invalidates cleanly rather than silently reusing old answers.
    """
    cache = _load_cache(cache_path)
    work = pairs.reset_index(drop=True).copy()
    work["pair_id"] = work.index
    todo = [r for r in work.itertuples(index=False) if int(r.pair_id) not in cache]

    in_tok = out_tok = failures = 0
    cp = Path(cache_path)
    cp.parent.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(todo), per_request):
        chunk = todo[start:start + per_request]
        payload = [{
            "id": int(r.pair_id),
            "group_a": {"name": str(r.label_a),
                        "examples": list(members.get(int(r.cluster_a), []))[:6]},
            "group_b": {"name": str(r.label_b),
                        "examples": list(members.get(int(r.cluster_b), []))[:6]},
        } for r in chunk]

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
            got = {int(d["id"]): bool(d["same"])
                   for d in json.loads(resp.choices[0].message.content)["decisions"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            failures += 1
            continue

        with open(cp, "a", encoding="utf-8") as fh:
            for r in chunk:
                pid = int(r.pair_id)
                if pid not in got:
                    continue
                rec = {"pair_id": pid, "prompt_version": PROMPT_VERSION,
                       "cluster_a": int(r.cluster_a), "cluster_b": int(r.cluster_b),
                       "label_a": str(r.label_a), "label_b": str(r.label_b),
                       "same": got[pid]}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cache[pid] = rec

    out = work.copy()
    out["same"] = [cache.get(int(p), {}).get("same") for p in out["pair_id"]]
    out.attrs["input_tokens"] = in_tok
    out.attrs["output_tokens"] = out_tok
    out.attrs["chunk_failures"] = failures
    out.attrs["from_cache"] = len(work) - len(todo)
    return out
