"""Naming clusters: c-TF-IDF candidates, then an LLM, then a human check.

c-TF-IDF alone gives terms, not names. `communication, skills, excellent,
kommunikationsfahigkeiten` is a bag of words a reader has to interpret; "Written
and verbal communication" is a label. Turning one into the other is a
generative act, which is why the LLM is here and not a heuristic.

Three properties, all borrowed from `llm_split` because they were right there:

* the prompt is **versioned**, so a renaming under changed instructions is not
  silently mixed with the old names;
* results are **cached by cluster signature** — the candidate terms plus the
  sample phrases — so a rerun costs nothing and a cluster whose membership
  changed is renamed while the rest are not;
* nothing identifying is sent. Cluster labels are requirement text only.

The names are a reading aid, never evidence. Every number in Week 2 is computed
from cluster IDs; a label is what a human reads in the table. So a wrong label
is a presentation bug, not a measurement error — which is why an LLM naming
them is acceptable where an LLM classifying them would not be.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

PROMPT_VERSION = "label-v1"

SYSTEM_PROMPT = """\
You name clusters of job-requirement phrases.

For each cluster you get its distinctive terms and a sample of member phrases.
Return a short English label naming WHAT IS BEING ASKED FOR.

Rules:
1. Two to five words. A noun phrase, not a sentence.
2. Name the requirement, not the cluster: "Cloud platforms (AWS, Azure)", not
   "Cluster about cloud".
3. Be specific where the members are specific and general where they are
   general. If members name several tools, name the category and give one or
   two examples in brackets.
4. The members may be in several languages; the label is always English, and it
   must cover the members rather than translating one of them.
5. If the members have nothing in common, return "MIXED" — a label that pretends
   coherence is worse than one that admits there is none.

Return ONLY a JSON array of objects: [{"id": <int>, "label": "<string>"}].
No prose, no markdown."""


def _signature(terms: str, samples: list[str]) -> str:
    payload = f"{PROMPT_VERSION}\x00{terms}\x00" + "\x00".join(sorted(samples))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def load_cache(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                out[rec["signature"]] = rec["label"]
    return out


def append_cache(path, signature: str, cluster: int, label: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"signature": signature, "cluster": cluster,
                             "label": label, "prompt_version": PROMPT_VERSION},
                            ensure_ascii=False) + "\n")


def build_inputs(dictionary: pd.DataFrame, assigned: pd.DataFrame,
                 reqs: pd.DataFrame, n_samples: int = 8) -> pd.DataFrame:
    """Candidate terms plus representative member phrases, per cluster.

    Members are sampled by frequency rather than at random: the phrases an
    employer actually writes often are what the label should cover, and a
    random draw over a long tail of one-off wordings describes the cluster
    worse than its common members do.
    """
    joined = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    joined["cluster"] = joined["cluster"].fillna(-1).astype(int)

    rows = []
    for cid, sub in joined.groupby("cluster"):
        if cid == -1:
            continue
        top = sub["phrase"].value_counts().head(n_samples).index.tolist()
        rows.append({"cluster": int(cid), "samples": top})
    samples = pd.DataFrame(rows)
    return dictionary.merge(samples, on="cluster", how="inner")


def name_clusters(inputs: pd.DataFrame, client, cache_path,
                  model: str = "gpt-5.4-mini-2026-03-17",
                  per_request: int = 20) -> pd.DataFrame:
    """Label every cluster, using the cache for any already named."""
    cache = load_cache(cache_path)
    inputs = inputs.copy()
    inputs["signature"] = [
        _signature(r.candidate_terms or "", list(r.samples))
        for r in inputs.itertuples(index=False)
    ]
    inputs["label"] = inputs["signature"].map(cache)

    todo = inputs[inputs["label"].isna()]
    in_tok = out_tok = 0
    for start in range(0, len(todo), per_request):
        chunk = todo.iloc[start:start + per_request]
        payload = [
            {"id": int(r.cluster), "terms": r.candidate_terms,
             "members": list(r.samples)}
            for r in chunk.itertuples(index=False)
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "cluster_labels", "strict": True,
                "schema": {"type": "object", "properties": {"labels": {
                    "type": "array", "items": {"type": "object", "properties": {
                        "id": {"type": "integer"}, "label": {"type": "string"}},
                        "required": ["id", "label"], "additionalProperties": False}}},
                    "required": ["labels"], "additionalProperties": False}}},
        )
        if resp.usage:
            in_tok += resp.usage.prompt_tokens or 0
            out_tok += resp.usage.completion_tokens or 0
        try:
            got = {int(e["id"]): e["label"].strip()
                   for e in json.loads(resp.choices[0].message.content)["labels"]}
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        for r in chunk.itertuples(index=False):
            lab = got.get(int(r.cluster))
            if lab:
                append_cache(cache_path, r.signature, int(r.cluster), lab)

    cache = load_cache(cache_path)
    inputs["label"] = inputs["signature"].map(cache).fillna("(unnamed)")
    inputs.attrs["input_tokens"] = in_tok
    inputs.attrs["output_tokens"] = out_tok
    return inputs.drop(columns=["samples", "signature"])
