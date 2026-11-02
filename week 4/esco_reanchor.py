"""Re-anchor the 617 groups with a lexical channel beside the cosine shortlist.

**What this fixes.** The 2026-10-04 audit (`week 4/esco-audit.md`) found nine
groups sitting in the ESCO residual although ESCO carries their concept under
that very wording — `interpersonal skills`, `communication skills`,
`information security`, `data analysis`, `writing skills`, `Adobe Creative
Suite`, `knowledge of GDPR`, `DevOps`. The adjudicator was not wrong; it was
never shown the right answer. The shortlist is the top five by cosine between a
cluster centroid and an ESCO label, and a centroid averaged over a few hundred
multilingual phrases can sit far from the concept's exact words.

So `esco_adjudicate.lexical_candidates` puts an exact-label hit on the ballot
before the cosine picks, and the adjudicator still decides. Nothing fuzzy: a
fuzzy channel would re-import the polysemy that made cosine unusable in the
first place.

**All 617 are re-run, not just the 193.** Two procedures producing one published
number is worse than one procedure producing a different number, and re-running
everything gives a straight v1-against-v2 comparison. Decisions are cached under
`anchor-v2` in a new file, so the v1 run stays intact and reproducible.

    python "week 4/esco_reanchor.py"          # dry run: what the ballot gains
    python "week 4/esco_reanchor.py" --run    # adjudicate and write
"""
from __future__ import annotations

import json
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
# `--tag x` runs the same procedure again under a fresh cache, which is how the
# repeat draws are taken. The adjudicator agrees with itself on only 90.8% of
# groups (`week 4/esco_stability.py`), so one pass is a sample, not an answer.
TAG = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--tag=")),
           adj.PROMPT_VERSION.replace("anchor-", ""))
adj.PROMPT_VERSION = f"anchor-{TAG}"
CACHE = OUT / f"esco_adjudication_{TAG}.jsonl"
MODEL = "gpt-5.4-mini-2026-03-17"

RUN = "--run" in sys.argv

# ---------------------------------------------------------------- the material
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
top25 = {c: g["phrase"].tolist() for c, g in members.groupby("cluster").head(25).groupby("cluster")}

lab = dict(zip(named["cluster"], named["label"]))
texts = {c: [lab.get(c, "")] + top25.get(c, []) for c in cluster_ids}
lex = adj.lexical_candidates(texts, uris, labels)
short = adj.shortlist(centroids, cluster_ids, vectors, uris, labels, k=5, lexical=lex)

# ------------------------------------------------------------------- dry run
was_un = set(old.loc[old["esco_uri"].isna(), "cluster"])
gained = {c for c, v in lex.items() if v}
print("=" * 86)
print("WHAT THE LEXICAL CHANNEL PUTS ON THE BALLOT")
print("=" * 86)
print(f"groups with an exact ESCO label among their own strings  {len(gained)} of {len(cluster_ids)}")
print(f"  of which were UNANCHORED under v1                      {len(gained & was_un)} of {len(was_un)}")
mass = j["cluster"].isin(gained & was_un).mean()
print(f"  requirement mass they carry                            {mass:.2%}")
print("\nthe unanchored groups that now have a literal candidate:")
rows = []
for c in sorted(gained & was_un, key=lambda c: -j["cluster"].eq(c).sum()):
    rows.append({"cluster": c, "our label": str(lab.get(c, ""))[:28],
                 "now on the ballot": lex[c][0][1][:38],
                 "atoms": int(j["cluster"].eq(c).sum()),
                 "v1 top candidate": str(old.loc[old["cluster"] == c, "top_candidate"].iloc[0])[:26]})
pd.set_option("display.width", 210)
pd.set_option("display.max_colwidth", 40)
print(pd.DataFrame(rows).to_string(index=False))

if not RUN:
    print(f"\nDry run. {len(cluster_ids)} groups would be adjudicated at "
          f"{adj.PROMPT_VERSION}, ~{len(cluster_ids)//12 + 1} requests.")
    print("Re-run with --run to spend it.")
    raise SystemExit(0)

# ----------------------------------------------------------------- adjudicate
from karimi import llm_split

client = llm_split.load_openai_client(str(ROOT / ".env"))
samples = {c: top25.get(c, [])[:5] for c in cluster_ids}
clusters = pd.DataFrame({"cluster": cluster_ids,
                         "label": [lab.get(c, "") for c in cluster_ids],
                         "samples": [samples.get(c, []) for c in cluster_ids]})
new = adj.adjudicate(clusters, short, client, CACHE, model=MODEL)
print(f"\nadjudicated {len(new)}, failures {new.attrs.get('chunk_failures')}, "
      f"tokens {new.attrs.get('input_tokens'):,} in / "
      f"{new.attrs.get('output_tokens'):,} out")

# -------------------------------------------------------------- what changed
m = new.merge(old[["cluster", "esco_uri"]], on="cluster", how="left",
              suffixes=("", "_v1"))
m["v1"] = m["esco_uri_v1"].notna()
m["v2"] = m["esco_uri"].notna()
print("\n" + "=" * 86)
print("V1 AGAINST V2")
print("=" * 86)
print(pd.crosstab(m["v1"].map({True: "anchored v1", False: "residual v1"}),
                  m["v2"].map({True: "anchored v2", False: "residual v2"})).to_string())
moved = m[m["v1"] != m["v2"]]
print(f"\n{len(moved)} groups changed side:")
print(moved.assign(atoms=moved["cluster"].map(lambda c: int(j['cluster'].eq(c).sum())))
      .sort_values("atoms", ascending=False)
      [["cluster", "label", "esco_label", "v1", "v2", "atoms"]].head(30).to_string(index=False))

res = adj.residual(asg, reqs, new)
print("\n" + "=" * 86)
print("THE RESIDUAL")
print("=" * 86)
print(f"v1  26.44%  software 27.45%  sales 24.43%   (published)")
print(f"v2  {res['all_atoms']['overall']:.2%}  "
      f"software {res['all_atoms']['by_function']['SOFTWARE_DATA']:.2%}  "
      f"sales {res['all_atoms']['by_function']['SALES_BD']:.2%}")
print(f"    excluding compounds {res['excluding_compounds']['overall']:.2%}")

new.to_csv(OUT / f"esco_decisions_{TAG}.csv", index=False, encoding="utf-8")
payload = {"esco_version": "v1.2.0", "esco_released": "2024-05",
           "prompt_version": adj.PROMPT_VERSION, "model": MODEL,
           "method": "cosine shortlist k=5 + exact-label channel + LLM adjudication",
           "pillar": "skills only; occupations and qualifications not searched",
           "anchor_set": {"skills": 13939, "hierarchy_headings": 420,
                          "labels": len(labels), "languages": 6},
           "residual": res}
(OUT / f"esco_residual_{TAG}.json").write_text(
    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwritten: esco_decisions_{TAG}.csv, esco_residual_{TAG}.json, {CACHE.name}")
