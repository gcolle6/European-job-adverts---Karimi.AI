"""Give every cluster a type from the hybrid classifier, not from the lexicon.

`cluster_dictionary_named.csv` carries `top_type`, the modal requirement type of
a cluster's members, computed when the lexicon was the only classifier. The
lexicon abstains on nearly half of everything, so 342 of 617 clusters read
`unassigned` — which makes the column useless for grouping clusters by what kind
of thing they are.

The hybrid reaches 92.6% coverage on the same atoms and has been applied to the
requirement table since `hybrid_corpus.py`. This carries it up to the cluster
level.

Written as a new column rather than in place. `top_type` is read by
`esco.py:287` to pick the positive-type clusters that calibrate the anchoring
cosine, and by six diagnostic scripts; replacing it would move those results
without anything saying so.
"""
import pathlib

import pandas as pd

OUT = pathlib.Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output")

named = pd.read_csv(OUT / "cluster_dictionary_named.csv")
asg = pd.read_parquet(OUT / "phrase_clusters.parquet")[["phrase_norm", "cluster"]]
hyb = pd.read_parquet(OUT / "req_type_hybrid.parquet")[["phrase_norm", "req_type_hybrid"]]

# modal type over occurrences, matching how top_type was built: one row per atom,
# not per unique phrase, so a common phrase counts for as much as it is asked
j = hyb.merge(asg, on="phrase_norm", how="inner")
j = j[(j["cluster"] != -1) & (j["req_type_hybrid"] != "unassigned")]

mode = (j.groupby(["cluster", "req_type_hybrid"]).size()
        .rename("n").reset_index()
        .sort_values(["cluster", "n"], ascending=[True, False])
        .drop_duplicates("cluster"))
total = j.groupby("cluster").size().rename("typed")

out = (named.merge(mode[["cluster", "req_type_hybrid", "n"]], on="cluster", how="left")
       .merge(total, on="cluster", how="left"))
out["top_type_hybrid"] = out["req_type_hybrid"].fillna("unassigned")
# how dominant that modal type is — a cluster split evenly across types is not
# described by its mode, and the share is what says so
out["top_type_share"] = (out["n"] / out["typed"]).round(3).fillna(0.0)
out = out.drop(columns=["req_type_hybrid", "n", "typed"])

before = (named["top_type"] == "unassigned").sum()
after = (out["top_type_hybrid"] == "unassigned").sum()
print(f"clusters: {len(out)}")
print(f"  unassigned, lexicon : {before:3}  ({before/len(out):.1%})")
print(f"  unassigned, hybrid  : {after:3}  ({after/len(out):.1%})")
print()
print("type mix:")
comp = pd.DataFrame({"lexicon": named["top_type"].value_counts(),
                     "hybrid": out["top_type_hybrid"].value_counts()}).fillna(0).astype(int)
print(comp.to_string())
print()
weak = (out["top_type_share"] < 0.5).sum()
print(f"clusters whose modal type is under half their typed atoms: {weak}")
print("  (their mode does not describe them; top_type_share carries that)")

out.to_csv(OUT / "cluster_dictionary_named.csv", index=False, encoding="utf-8")
print(f"\nwritten: {OUT / 'cluster_dictionary_named.csv'}  (+2 columns, none replaced)")
