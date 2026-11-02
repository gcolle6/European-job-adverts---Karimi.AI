"""Does the adjudicator agree with itself? A control for the re-anchoring run.

**Why this exists.** Adding a lexical channel to the shortlist moved 87 of 617
groups across the anchored/residual line - 43 in the intended direction and 44
in the opposite one. The first explanation was a defect I had introduced: with a
fixed ballot of five, two literal candidates displaced the two weakest cosine
picks, so a group whose right answer sat fifth lost it. That was real and it was
fixed. It changed almost nothing: 87 moved before the fix and 87 after.

Which leaves one hypothesis that has to be tested rather than argued. The
residual is produced by 617 judgements from a language model, and nobody has
ever asked whether the same question asked twice gets the same answer. If it
does not, run-to-run variance is a larger source of error than anything else in
the ESCO audit, and the published figure needs an interval rather than three
decimal places.

So this re-runs **the original procedure, unchanged** - the v1 prompt text, the
v1 shortlist, no lexical channel - under a fresh cache tag so nothing is served
from the previous run. Any movement is the instrument talking to itself.

The v1 prompt is pinned here rather than imported, because the module's copy has
since been edited and a control that drifts with the thing it controls is not a
control.

    python "week 4/esco_stability.py"          # dry run
    python "week 4/esco_stability.py" --run    # spend one pass
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from karimi import esco, esco_adjudicate as adj

ROOT = pathlib.Path(__file__).resolve().parent.parent
W1 = ROOT / "week 1" / "output"
W2 = ROOT / "week 2"
OUT = W2 / "output"
MODEL = "gpt-5.4-mini-2026-03-17"

PROMPT_V1 = """\
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

adj.SYSTEM_PROMPT = PROMPT_V1
adj.PROMPT_VERSION = "anchor-v1-replica"
CACHE = OUT / "esco_adjudication_v1replica.jsonl"

labels, uris, vectors = esco.load_skill_vectors(W2 / "esco" / "esco_vectors.npz")
z = np.load(OUT / "cluster_centroids.npz", allow_pickle=True)
centroids, cluster_ids = z["centroids"], [int(c) for c in z["cluster_ids"]]
named = pd.read_csv(OUT / "cluster_dictionary_named.csv")
old = pd.read_csv(OUT / "esco_decisions.csv")
asg = pd.read_parquet(OUT / "phrase_clusters.parquet")
reqs = pd.read_parquet(W1 / "requirements.parquet")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
members = (j.groupby(["cluster", "phrase"]).size().rename("n").reset_index()
           .sort_values("n", ascending=False))
top5 = {c: g["phrase"].tolist()[:5]
        for c, g in members.groupby("cluster").head(5).groupby("cluster")}
lab = dict(zip(named["cluster"], named["label"]))

# v1 exactly: cosine only, five candidates, no lexical channel.
short = adj.shortlist(centroids, cluster_ids, vectors, uris, labels, k=5)

if "--run" not in sys.argv:
    print(f"Dry run. Would re-ask all {len(cluster_ids)} groups the ORIGINAL "
          f"question under tag {adj.PROMPT_VERSION}.")
    print(f"~{len(cluster_ids)//12 + 1} requests. Re-run with --run.")
    raise SystemExit(0)

from karimi import llm_split

client = llm_split.load_openai_client(str(ROOT / ".env"))
clusters = pd.DataFrame({"cluster": cluster_ids,
                         "label": [lab.get(c, "") for c in cluster_ids],
                         "samples": [top5.get(c, []) for c in cluster_ids]})
rep = adj.adjudicate(clusters, short, client, CACHE, model=MODEL)

m = rep.merge(old[["cluster", "esco_uri"]], on="cluster", how="left",
              suffixes=("", "_first"))
m["first"] = m["esco_uri_first"].notna()
m["again"] = m["esco_uri"].notna()
agree = (m["first"] == m["again"]).mean()
same_uri = (m["esco_uri"] == m["esco_uri_first"]).mean()

print("\n" + "=" * 84)
print("THE SAME QUESTION, ASKED TWICE")
print("=" * 84)
print(pd.crosstab(m["first"].map({True: "anchored run 1", False: "residual run 1"}),
                  m["again"].map({True: "anchored run 2", False: "residual run 2"})).to_string())
print(f"\nagreement on anchored-or-not   {agree:.1%}  "
      f"({int((m['first'] != m['again']).sum())} of {len(m)} flipped)")
print(f"agreement on the exact concept {same_uri:.1%}")

un1 = set(old.loc[old["esco_uri"].isna(), "cluster"])
un2 = set(rep.loc[rep["esco_uri"].isna(), "cluster"])
for name, s in (("run 1 (published)", un1), ("run 2 (replica)", un2)):
    by = j.groupby("macro_function")["cluster"].apply(lambda c: c.isin(s).mean())
    print(f"\nresidual, {name:18} {j['cluster'].isin(s).mean():.2%}   "
          + "  ".join(f"{k} {v:.2%}" for k, v in by.items()))

rep.to_csv(OUT / "esco_decisions_v1replica.csv", index=False, encoding="utf-8")
print(f"\nwritten: esco_decisions_v1replica.csv, {CACHE.name}")
