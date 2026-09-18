"""Resume the cased refit from the saved embeddings.

The encode step completed and wrote `embeddings_cased.npz` (37 minutes); only the
clustering call failed, on swapped arguments to `reference_phrases`. Nothing
about the comparison changes — this picks up where it stopped rather than paying
for the encoding twice.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()


def log(m):
    print(f"[{time.time()-t0:6.0f}s] {m}", flush=True)


reqs = pd.read_parquet(W1 + r"\requirements.parquet")
base = data.build_analysis_base().df
z = np.load(W3 + r"\embeddings_cased.npz", allow_pickle=True)
norms = [str(p) for p in z["phrases"]]
vecs = z["vectors"]
log(f"loaded cased embeddings {vecs.shape}")

ref = cl.reference_phrases(reqs, base)          # (reqs, base) — not the other way
log(f"reference phrases {len(ref):,}")

fit = cl.fit_reference(norms, vecs, ref)
log(f"fit: {fit['n_clusters']} clusters, HDBSCAN noise {fit['noise_share']:.1%}")
asg_new = cl.assign(norms, vecs, fit)
log(f"assigned: {(asg_new['cluster'] != -1).mean():.1%} placed")
asg_new.to_parquet(W3 + r"\phrase_clusters_cased.parquet", index=False)
np.savez_compressed(W3 + r"\cluster_centroids_cased.npz",
                    cluster_ids=np.array(fit["cluster_ids"]), centroids=fit["centroids"])

asg_old = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))

print("")
print("=" * 92)
print("1. STRUCTURE")
print("=" * 92)
old_placed = (asg_old["cluster"] != -1).mean()
new_placed = (asg_new["cluster"] != -1).mean()
print(f"{'':<30}{'published (lowercased)':>24}{'refit (cased)':>18}")
print(f"{'clusters':<30}{len(named):>24}{fit['n_clusters']:>18}")
print(f"{'HDBSCAN noise on the fit':<30}{'34.7%':>24}{fit['noise_share']:>17.1%}")
print(f"{'phrases placed':<30}{old_placed:>23.1%}{new_placed:>17.1%}")
print(f"{'median similarity':<30}"
      f"{asg_old.loc[asg_old['cluster'] != -1, 'similarity'].median():>24.3f}"
      f"{asg_new.loc[asg_new['cluster'] != -1, 'similarity'].median():>18.3f}")
delta_clusters = (fit["n_clusters"] - len(named)) / len(named)
print(f"\n  cluster-count change: {delta_clusters:+.1%}   "
      f"(rebuild trigger: more than +/-15%)")

print("")
print("=" * 92)
print("2. GRANULARITY — do the grab-bags shrink?")
print("=" * 92)
j_old = reqs.merge(asg_old[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j_new = reqs.merge(asg_new[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
stats = {}
for nm, jj in [("published", j_old), ("refit", j_new)]:
    s = (jj[jj["cluster"].notna() & (jj["cluster"] != -1)]
         .groupby("cluster").size().sort_values(ascending=False))
    stats[nm] = {"largest": int(s.iloc[0]), "top5": float(s.head(5).sum() / s.sum()),
                 "over2000": int((s > 2000).sum()), "total": int(s.sum())}
    print(f"  {nm:<10} largest group {s.iloc[0]:>6} reqs ({s.iloc[0]/s.sum():.2%})   "
          f"top 5 hold {s.head(5).sum()/s.sum():.2%}   groups over 2,000: {int((s > 2000).sum())}")
d_largest = (stats["refit"]["largest"] - stats["published"]["largest"]) / stats["published"]["largest"]
d_top5 = (stats["refit"]["top5"] - stats["published"]["top5"]) / stats["published"]["top5"]
print(f"\n  largest group change {d_largest:+.1%}  (trigger: shrinks more than 25%)")
print(f"  top-5 mass change    {d_top5:+.1%}  (trigger: falls more than 20% relative)")

print("")
print("=" * 92)
print("3. THE MOTIVATING CASE")
print("=" * 92)
azure = reqs.loc[reqs["phrase"].str.strip().eq("Experience with Azure"), "phrase_norm"].iloc[0]
oc = int(asg_old.loc[asg_old["phrase_norm"] == azure, "cluster"].iloc[0])
nc = int(asg_new.loc[asg_new["phrase_norm"] == azure, "cluster"].iloc[0])
print(f"  published -> cluster {oc} '{lab.get(oc, '?')}'")
print(f"  refit     -> cluster {nc} (new numbering); its most common members:")
for p, n in j_new[j_new["cluster"] == nc]["phrase"].value_counts().head(8).items():
    print(f"      {n:>4}  {str(p)[:66]}")

print("")
print("=" * 92)
print("4. DOES H1 MOVE?")
print("=" * 92)
drop_old = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
           set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
res = {}
for nm, a, dr in [("published", asg_old, drop_old), ("refit (cased)", asg_new, set())]:
    prof = var.cell_profiles(a, reqs, exclude=dr)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    res[nm] = s / w
    print(f"  {nm:<16} sales {s:.4f}  software {w:.4f}  ratio {s/w:.3f}")
print(f"\n  H1 ratio change: {res['refit (cased)'] - res['published']:+.3f}  "
      f"(trigger: more than +/-0.15, or outside 1.13-1.43)")
print("  note: the refit has no boilerplate/MIXED list yet, so its exclusions differ;")
print("        the published run excludes 10 groups and the refit none.")
log("done")
