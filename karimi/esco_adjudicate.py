"""Deciding whether ESCO actually covers a requirement, when cosine cannot.

**Why this module exists.** Anchoring by cosine similarity was built, run, and
found unusable — not by argument but by inspection. Genuine anchors do score
high with a clear margin:

    TensorFlow experience  ->  tensorflow                      margin 0.429
    Root cause analysis    ->  root cause analysis             margin 0.422
    Git                    ->  GIT                             margin 0.313

But so do accidents, and the accidents are systematically **polysemous**:

    Sound judgment         ->  configurar un equipo de sonido  (sound = audio)
    SonarQube experience   ->  asistir en la maniobra de barcos (sonar = ships)
    Spring Boot Java dev   ->  oversee spring making machine   (spring = coil)
    Personal attributes    ->  Mengenlehre                     (set theory)

The decisive measurement: `Spring Boot`'s **wrong** match scores a 0.148 margin
while `Google Cloud Platform`'s **correct** one scores 0.151. No threshold
separates them, so no residual computed this way means anything.

The reason is structural rather than a tuning failure. Two independently
embedded short phrases are compared by direction alone, and a sentence
embedding has no way to know that "Spring" is a Java framework and not a metal
coil. Deciding *sameness* is a judgement.

So the work is split the way this project splits every other judgement: the
cheap deterministic layer narrows 14,359 concepts to five candidates, and an LLM
decides which — if any — is the same concept. Cosine keeps the job it is good
at and loses the one it is not.

A note on which error to prefer. This measures what the taxonomy **lacks**, so a
false match hides a real gap while a missed match merely overstates one. The
prompt is therefore instructed to prefer `null` when doubtful, and the residual
this produces should be read as an upper bound.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROMPT_VERSION = "anchor-v1"

SYSTEM_PROMPT = """\
You decide whether an official taxonomy already contains a job requirement.

For each item you get a requirement cluster (its name and example phrases) and
up to 5 candidate ESCO skill concepts retrieved by semantic similarity.

Answer with the candidate that means THE SAME THING as the requirement, or null
if none does.

Rules:
1. Same CONCEPT, not merely the same topic. "Experience at an Open Source
   company" is not "open source software". Being near a subject is not being it.
2. Beware words with two senses — retrieval confuses these constantly: Spring
   (Java framework vs metal coil), Sonar/SonarQube (code analysis vs ships),
   Airflow (Apache tool vs aerodynamics), Juniper (networking vs plant), sound
   (audio vs judgement), Ruby, Rust, Go, Puppet, Chef, Sage, Oracle. If the
   candidate uses the other sense, it is NOT a match.
3. Candidates may be in any language; judge the meaning, not the language.
4. A narrower or broader concept matches if it is clearly the same skill —
   "Python" and "Python (computer programming)" match. A merely related skill
   does not: "teach chemistry" is not "chemistry degree".
5. Prefer null over a doubtful match. This measures what the taxonomy LACKS, so
   a false match hides a real gap, which is the more damaging error.

Return ONLY: {"decisions": [{"id": <int>, "match": <candidate index 0-4 or null>}]}"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "anchor_decisions",
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
                            "match": {"type": ["integer", "null"]},
                        },
                        "required": ["id", "match"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["decisions"],
            "additionalProperties": False,
        },
    },
}


def shortlist(centroids: np.ndarray, cluster_ids: list[int], skill_vectors: np.ndarray,
              skill_uris: list[str], skill_labels: list[str], k: int = 5) -> dict:
    """Top-k ESCO candidates per cluster, deduplicated by concept.

    Cosine is kept for the one thing it does well — narrowing 14,359 concepts to
    five — and nothing more. Deduplicating by concept URI matters because a
    single concept carries up to six alternative labels in English, and five
    slots filled by five spellings of the same concept would waste the shortlist.
    """
    unit = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12, None)
    sims = unit @ skill_vectors.T
    out = {}
    for row, cid in enumerate(cluster_ids):
        order = np.argsort(-sims[row])[: k * 10]
        seen, picks = set(), []
        for j in order:
            uri = skill_uris[j]
            if uri in seen:
                continue
            seen.add(uri)
            picks.append((uri, skill_labels[j], round(float(sims[row, j]), 4)))
            if len(picks) >= k:
                break
        out[int(cid)] = picks
    return out


def _load_cache(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("prompt_version") == PROMPT_VERSION:
                out[int(rec["cluster"])] = rec
    return out


def adjudicate(clusters: pd.DataFrame, candidates: dict, client, cache_path,
               model: str = "gpt-5.4-mini-2026-03-17", per_request: int = 12) -> pd.DataFrame:
    """Ask which shortlisted concept, if any, is genuinely the same requirement.

    `clusters` needs `cluster` and `label`, and optionally `samples` (member
    phrases, which help the model far more than the label alone). `candidates`
    maps cluster id to the shortlist. Cached by cluster and prompt version.
    """
    cache = _load_cache(cache_path)
    todo = [r for r in clusters.itertuples(index=False) if int(r.cluster) not in cache]
    in_tok = out_tok = 0
    failures = 0

    for start in range(0, len(todo), per_request):
        chunk = todo[start:start + per_request]
        payload = []
        for r in chunk:
            cands = candidates.get(int(r.cluster), [])
            samples = list(getattr(r, "samples", []) or [])[:5]
            payload.append({
                "id": int(r.cluster),
                "requirement": r.label,
                "examples": samples,
                "candidates": [{"index": i, "concept": c[1]} for i, c in enumerate(cands)],
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
            decisions = json.loads(resp.choices[0].message.content)["decisions"]
            got = {int(d["id"]): d["match"] for d in decisions}
        except (json.JSONDecodeError, KeyError, TypeError):
            failures += 1
            continue

        cp = Path(cache_path)
        cp.parent.mkdir(parents=True, exist_ok=True)
        with open(cp, "a", encoding="utf-8") as fh:
            for r in chunk:
                cid = int(r.cluster)
                if cid not in got:
                    continue
                idx = got[cid]
                cands = candidates.get(cid, [])
                chosen = cands[idx] if isinstance(idx, int) and 0 <= idx < len(cands) else None
                rec = {"cluster": cid, "prompt_version": PROMPT_VERSION,
                       "esco_uri": chosen[0] if chosen else None,
                       "esco_label": chosen[1] if chosen else None,
                       "cosine": chosen[2] if chosen else None}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cache[cid] = rec

    rows = []
    for r in clusters.itertuples(index=False):
        rec = cache.get(int(r.cluster), {})
        cands = candidates.get(int(r.cluster), [])
        rows.append({
            "cluster": int(r.cluster),
            "label": r.label,
            "esco_uri": rec.get("esco_uri"),
            "esco_label": rec.get("esco_label"),
            "cosine": rec.get("cosine"),
            "anchored": rec.get("esco_uri") is not None,
            "decided": int(r.cluster) in cache,
            "top_cosine": cands[0][2] if cands else None,
            "top_candidate": cands[0][1] if cands else None,
        })
    out = pd.DataFrame(rows)
    out.attrs["input_tokens"] = in_tok
    out.attrs["output_tokens"] = out_tok
    out.attrs["chunk_failures"] = failures
    return out


def residual(assigned: pd.DataFrame, reqs: pd.DataFrame, decisions: pd.DataFrame) -> dict:
    """Requirement mass sitting in clusters ESCO has no concept for.

    Reported three ways because each answers a different question, and the
    project's convention is to publish the range rather than the flattering end:

    * **by function** — Hypothesis 2's actual claim is about both functions;
    * **excluding compound atoms** — an atom holding two requirements may anchor
      spuriously or not at all, and the direction was not predictable;
    * **by requirement type** — credentials are the known confound. ESCO models
      qualifications in a separate pillar that was not downloaded, so a
      credential cluster may be unanchored for a mechanical reason rather than a
      real gap.
    """
    unanchored = set(decisions.loc[~decisions["anchored"], "cluster"])

    def measure(sub: pd.DataFrame) -> dict:
        j = sub.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
        j["cluster"] = j["cluster"].fillna(-1).astype(int)
        j["in_residual"] = j["cluster"].isin(unanchored)
        by_fn = j.groupby("macro_function")["in_residual"].mean()
        by_type = j.groupby("req_type")["in_residual"].mean()
        return {
            "overall": round(float(j["in_residual"].mean()), 4),
            "by_function": {k: round(float(v), 4) for k, v in by_fn.items()},
            "by_type": {k: round(float(v), 4) for k, v in by_type.items()},
        }

    return {
        "n_unanchored_clusters": len(unanchored),
        "n_clusters": len(decisions),
        "all_atoms": measure(reqs),
        "excluding_compounds": measure(reqs[~reqs["looks_compound"]]),
    }
