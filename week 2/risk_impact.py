"""What actually happened to the badly-extracted requirements in Week 2?

Week 1 ended with two flags on every requirement: `from_long_segment` (7.3%,
extracted from text where accuracy is 58% rather than 83%) and `looks_compound`
(6.7%, still reads as two requirements). The decision was to carry them rather
than drop them. This asks what that decision cost, at every stage they touched.

Five questions, each with a clean comparison against the unflagged material:

  1. did they get placed in a group at all, or fall into the noise class?
  2. do they sit as close to their group's centre, or hang off the edge?
  3. did they pool together into groups of their own — junk clusters?
  4. do the groups they dominate get named, or come back incoherent?
  5. do those groups anchor to the official catalogue at the same rate?
"""
import sys

sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 40)
OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"

reqs = pd.read_parquet(r"week 1/output/requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
dec = pd.read_csv(OUT + r"\esco_decisions.csv")

j = reqs.merge(asg[["phrase_norm", "cluster", "similarity"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j["risky"] = j["from_long_segment"] | j["looks_compound"]

print(f"requirements: {len(j):,}")
print(f"  from long text : {j['from_long_segment'].mean():.1%}")
print(f"  still compound : {j['looks_compound'].mean():.1%}")
print(f"  either (risky) : {j['risky'].mean():.1%}")
print()

# --- 1. placed, or dropped into noise? --------------------------------------
print("=" * 78)
print("1. WERE THEY PLACED IN A GROUP?")
print("=" * 78)
t = j.groupby("risky").agg(
    atoms=("phrase", "size"),
    unplaced=("cluster", lambda c: float((c == -1).mean())),
)
t["unplaced"] = (t["unplaced"] * 100).round(2)
t.index = ["clean", "risky"]
print(t.to_string())
clean_un = float((j.loc[~j["risky"], "cluster"] == -1).mean())
risky_un = float((j.loc[j["risky"], "cluster"] == -1).mean())
print(f"\n  risky atoms are {risky_un/max(clean_un,1e-9):.1f}x more likely to be left unplaced")
print("  (unplaced = the noise class, which is a feature: better out than forced in)")
print()

# --- 2. how well do they fit? ------------------------------------------------
print("=" * 78)
print("2. DO THEY FIT THEIR GROUP AS WELL?")
print("=" * 78)
placed = j[j["cluster"] != -1]
print(placed.groupby("risky")["similarity"].describe()[["count", "mean", "25%", "50%", "75%"]].round(3).to_string())
print("\n  similarity = closeness to the group centre; 1.0 is identical")
print()

# --- 3. did they form their own groups? -------------------------------------
print("=" * 78)
print("3. DID THEY POOL INTO GROUPS OF THEIR OWN?")
print("=" * 78)
per = placed.groupby("cluster").agg(
    atoms=("phrase", "size"),
    risky_pct=("risky", lambda x: round(float(x.mean()) * 100, 1)),
).reset_index().merge(named[["cluster", "label", "top_type"]], on="cluster", how="left")
base = float(placed["risky"].mean()) * 100
print(f"  corpus-wide risky share: {base:.1f}%")
print(f"  groups above 2x that share ({2*base:.0f}%): "
      f"{int((per['risky_pct'] > 2*base).sum())} of {len(per)}")
print(f"  groups above 3x ({3*base:.0f}%): {int((per['risky_pct'] > 3*base).sum())}")
print()
print("  the 10 groups most built from risky material:")
print(per.nlargest(10, "risky_pct")[["cluster", "label", "atoms", "risky_pct", "top_type"]].to_string(index=False))
print()

# --- 4. are those groups coherent (named, not MIXED)? -----------------------
print("=" * 78)
print("4. DID THE GROUPS THEY DOMINATE COME BACK COHERENT?")
print("=" * 78)
per["mixed"] = per["label"].astype(str).str.upper() == "MIXED"
hi = per[per["risky_pct"] > 2 * base]
lo = per[per["risky_pct"] <= 2 * base]
print(f"  risky-dominated groups: {len(hi)}   MIXED among them: {int(hi['mixed'].sum())}")
print(f"  the rest:               {len(lo)}   MIXED among them: {int(lo['mixed'].sum())}")
mixed_rows = per[per["mixed"]][["cluster", "atoms", "risky_pct"]]
print(f"\n  the two MIXED groups and their risky share:")
print(mixed_rows.to_string(index=False))
print(f"  (corpus-wide risky share is {base:.1f}%, so these are NOT risky-driven)")
print()

# --- 5. do they anchor to the catalogue as often? ---------------------------
print("=" * 78)
print("5. DO RISKY-DOMINATED GROUPS ANCHOR TO ESCO AS OFTEN?")
print("=" * 78)
per = per.merge(dec[["cluster", "anchored"]], on="cluster", how="left")
per["band"] = pd.cut(per["risky_pct"], [-0.1, 5, 10, 20, 100],
                     labels=["0-5%", "5-10%", "10-20%", ">20%"])
g = per.groupby("band", observed=True).agg(
    groups=("cluster", "size"),
    anchored_pct=("anchored", lambda x: round(float(x.mean()) * 100, 1)),
    mean_atoms=("atoms", "mean"),
)
print(g.round(1).to_string())
print("\n  if risky material were poisoning the catalogue matching, the anchored")
print("  share would fall as the risky share rises")
