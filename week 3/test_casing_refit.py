"""Option (c): refit the clusters on CASED text and measure what changes.

Nothing is replaced. This produces a parallel clustering from raw text and
compares it against the published one, so the cost of fixing the casing defect
is known before it is paid.

The vocabulary is held identical: one **representative raw spelling** per
`phrase_norm` — the most frequent one — so both runs cluster exactly 210,195
items and any difference is the casing, not a different unit.

Everything else is held fixed too: the same reference months, the same UMAP and
HDBSCAN parameters, the same assignment threshold, the same random seed.

Decision rule, stated before the run: if the granularity measures and the H1
ratio barely move, the defect is a declared limitation and Week 3 continues. If
they move materially, Week 2 is re-run on cased text.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, config, data, embed as emb, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()


def log(m):
    print(f"[{time.time()-t0:6.0f}s] {m}", flush=True)


reqs = pd.read_parquet(W1 + r"\requirements.parquet")
base = data.build_analysis_base().df
log(f"requirements {len(reqs):,}")

# one representative raw spelling per phrase_norm — keeps the vocabulary identical
rep = (reqs.groupby(["phrase_norm", "phrase"]).size().rename("n").reset_index()
       .sort_values("n", ascending=False).drop_duplicates("phrase_norm"))
norms = rep["phrase_norm"].astype(str).tolist()
raws = rep["phrase"].astype(str).tolist()
log(f"vocabulary {len(norms):,} (cased forms selected by frequency)")

model = emb.load_model()
vecs = emb.encode(model, raws)
log(f"encoded cased text: {vecs.shape}")
np.savez_compressed(W3 + r"\embeddings_cased.npz",
                    phrases=np.array(norms, dtype=object), vectors=vecs.astype(np.float32))
log("saved embeddings_cased.npz")

ref = cl.reference_phrases(base, reqs) if hasattr(cl, "reference_phrases") else None
if ref is None:
    months = pd.to_datetime(base["created_at"], errors="coerce").dt.strftime("%Y-%m")
    ref_ids = set(base.loc[months.isin(cl.REFERENCE_MONTHS), "vacancy_id"])
    ref = set(reqs.loc[reqs["vacancy_id"].isin(ref_ids), "phrase_norm"].dropna())
log(f"reference phrases {len(ref):,}")

fit = cl.fit_reference(norms, vecs, ref)
log(f"fit: {fit['n_clusters']} clusters, noise {fit['noise_share']:.1%}")
asg_new = cl.assign(norms, vecs, fit)
log(f"assigned: {(asg_new['cluster'] != -1).mean():.1%} placed")
asg_new.to_parquet(W3 + r"\phrase_clusters_cased.parquet", index=False)
np.savez_compressed(W3 + r"\cluster_centroids_cased.npz",
                    cluster_ids=np.array(fit["cluster_ids"]), centroids=fit["centroids"])

# ------------------------------------------------------------------ compare
asg_old = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
print("")
print("=" * 92)
print("STRUCTURE")
print("=" * 92)
print(f"{'':<28}{'published (lowercased)':>24}{'refit (cased)':>18}")
print(f"{'clusters':<28}{len(named):>24}{fit['n_clusters']:>18}")
print(f"{'HDBSCAN noise on the fit':<28}"
      f"{'34.7%':>24}{fit['noise_share']:>17.1%}")
print(f"{'phrases placed':<28}"
      f"{(asg_old['cluster'] != -1).mean():>23.1%}{(asg_new['cluster'] != -1).mean():>17.1%}")
print(f"{'median similarity':<28}"
      f"{asg_old.loc[asg_old['cluster'] != -1, 'similarity'].median():>24.3f}"
      f"{asg_new.loc[asg_new['cluster'] != -1, 'similarity'].median():>18.3f}")

# granularity: how concentrated is the mass in the biggest groups?
print("")
print("=" * 92)
print("GRANULARITY — do the grab-bags shrink?")
print("=" * 92)
j_old = reqs.merge(asg_old[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j_new = reqs.merge(asg_new[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
for nm, jj in [("published", j_old), ("refit", j_new)]:
    s = jj[jj["cluster"].notna() & (jj["cluster"] != -1)].groupby("cluster").size().sort_values(ascending=False)
    print(f"  {nm:<10} largest group {int(s.iloc[0]):>6} reqs "
          f"({s.iloc[0]/s.sum():.2%})   top 5 hold {s.head(5).sum()/s.sum():.2%}   "
          f"groups over 2,000 reqs: {int((s > 2000).sum())}")

# the decisive example
print("")
azure = reqs[reqs["phrase"].str.strip().eq("Experience with Azure")]["phrase_norm"].iloc[0]
old_c = asg_old.loc[asg_old["phrase_norm"] == azure, "cluster"]
new_c = asg_new.loc[asg_new["phrase_norm"] == azure, "cluster"]
lab = dict(zip(named["cluster"], named["label"]))
print(f"  'Experience with Azure' published -> cluster {int(old_c.iloc[0])} "
      f"({lab.get(int(old_c.iloc[0]), '?')})")
print(f"  'Experience with Azure' refit     -> cluster {int(new_c.iloc[0])} "
      f"(unnamed; members below)")
mem = j_new[j_new["cluster"] == new_c.iloc[0]]["phrase"].value_counts().head(8)
print("      " + " | ".join(str(p)[:30] for p in mem.index))

# ------------------------------------------------------------------ H1
print("")
print("=" * 92)
print("DOES H1 MOVE?")
print("=" * 92)
drop_old = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
           set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
for nm, a, dr in [("published", asg_old, drop_old), ("refit (cased)", asg_new, set())]:
    prof = var.cell_profiles(a.rename(columns={"cluster": "cluster"}), reqs, exclude=dr)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    print(f"  {nm:<16} sales {s:.4f}  software {w:.4f}  ratio {s/w:.3f}")
print("  (the refit has no boilerplate or MIXED list yet, so its exclusions differ —")
print("   the ratio is the comparable quantity, not the levels)")
log("done")
