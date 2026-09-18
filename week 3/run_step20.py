"""Week 3, step 20 — vary every threshold.

A headline that holds at exactly one threshold is not a finding, it is a
coincidence that survived one arbitrary choice. Every knob that could have been
set differently is swept, and each headline is reported as stable, as moving in
magnitude, or as flipping.

Swept here:

  * assignment cut-off — how close a requirement must sit to a group's centre;
  * minimum cell size — which cells are admitted at all;
  * shell lift cut-off — how distinctive a group must be to count as shell;
  * boilerplate definition — both the share and the flatness rule;
  * classifier — lexicon against hybrid, which changes every type-dependent number.

The H2 novelty/vagueness thresholds were already swept in step 19 (a 5x5 grid,
direction held in all 25) and are not repeated.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, config, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
base = data.build_analysis_base().df
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
dec = pd.read_csv(OUT + r"\esco_decisions.csv")
dec["anchored"] = dec["anchored"].astype(str).str.strip().str.lower().eq("true")
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")

from karimi import embed as emb
phrases, vecs = emb.load_corpus(W1 + r"\embeddings.npz")
store = {p: i for i, p in enumerate(phrases)}
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
cids, C = np.array(z["cluster_ids"]), z["centroids"]
C = C / np.clip(np.linalg.norm(C, axis=1, keepdims=True), 1e-12, None)

uniq = reqs["phrase_norm"].astype(str).unique()
idx = np.array([store[p] for p in uniq])
V = vecs[idx]
V = V / np.clip(np.linalg.norm(V, axis=1, keepdims=True), 1e-12, None)
S = V @ C.T
best_i = S.argmax(axis=1)
best_s = S[np.arange(len(S)), best_i]
best_c = cids[best_i]
print(f"[{time.time()-t0:.0f}s] scored {len(uniq):,} phrases against {len(cids)} centroids")

drop_default = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
               set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])


def h1_ratio(assign_df, exclude, industries=None):
    prof = var.cell_profiles(assign_df, reqs, exclude=exclude, levels=industries)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    return s / w


print("")
print("=" * 84)
print("1. ASSIGNMENT CUT-OFF")
print("=" * 84)
rows = []
for thr in [0.50, 0.55, 0.60, 0.65, 0.70]:
    a = pd.DataFrame({"phrase_norm": uniq,
                      "cluster": np.where(best_s >= thr, best_c, -1),
                      "similarity": best_s})
    rows.append({"cut_off": thr, "placed": f"{(a['cluster'] != -1).mean():.1%}",
                 "H1_ratio": round(h1_ratio(a, drop_default), 3)})
d1 = pd.DataFrame(rows)
print(d1.to_string(index=False))
print(f"  default is {cl.MIN_ASSIGN_COSINE}; H1 range "
      f"{d1['H1_ratio'].min():.3f}-{d1['H1_ratio'].max():.3f}, "
      f"always > 1: {bool((d1['H1_ratio'] > 1).all())}")

asg = pd.DataFrame({"phrase_norm": uniq,
                    "cluster": np.where(best_s >= cl.MIN_ASSIGN_COSINE, best_c, -1),
                    "similarity": best_s})

print("")
print("=" * 84)
print("2. MINIMUM CELL SIZE — which industries are admitted")
print("=" * 84)
post = base.drop_duplicates("vacancy_id")
ct = pd.crosstab(post["company_industry"], post["macro_function"])
rows = []
for m in [200, 300, 400, 500, 700]:
    inds = ct[(ct >= m).all(axis=1)].index.tolist()
    if len(inds) < 3:
        rows.append({"min_cell": m, "industries": len(inds), "H1_ratio": None})
        continue
    rows.append({"min_cell": m, "industries": len(inds),
                 "H1_ratio": round(h1_ratio(asg, drop_default, industries=inds), 3)})
d2 = pd.DataFrame(rows)
print(d2.to_string(index=False))
v = d2["H1_ratio"].dropna()
print(f"  default is {config.MIN_CELL_SIZE}; H1 range {v.min():.3f}-{v.max():.3f}, "
      f"always > 1: {bool((v > 1).all())}")

print("")
print("=" * 84)
print("3. BOILERPLATE DEFINITION — what gets set aside")
print("=" * 84)
shares = cl.cell_shares(asg, reqs)
rows = []
for ms in [0.08, 0.10, 0.12]:
    for cv in [0.30, 0.40, 0.50]:
        bp = cl.classify_boilerplate(shares)
        keep = set(bp.loc[(bp["mean_share"] >= ms) & (bp["cv"] <= cv), "cluster"])
        ex = keep | set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
        rows.append({"min_share": ms, "max_cv": cv, "boilerplate": len(keep),
                     "H1_ratio": round(h1_ratio(asg, ex), 3)})
d3 = pd.DataFrame(rows)
print(d3.to_string(index=False))
print(f"  default {cl.BOILERPLATE_MIN_MEAN_SHARE}/{cl.BOILERPLATE_MAX_CV}; "
      f"H1 range {d3['H1_ratio'].min():.3f}-{d3['H1_ratio'].max():.3f}, "
      f"always > 1: {bool((d3['H1_ratio'] > 1).all())}")

print("")
print("=" * 84)
print("4. SHELL LIFT CUT-OFF — the Week 2 count-based H1, for comparison")
print("=" * 84)
rows = []
for lift in [1.5, 1.75, 2.0, 2.5]:
    cs = cl.core_shell(asg, reqs, boilerplate=drop_default)
    sh = cs[(cs["lift"] >= lift) & (cs["share"] >= cl.SHELL_MIN_SHARE) & cs["reliable"]]
    per = sh.groupby("macro_function")["cluster"].size() / \
        cs.groupby("macro_function")["company_industry"].nunique()
    if len(per) < 2:
        continue
    rows.append({"min_lift": lift, "shell_sales": round(per.get("SALES_BD", np.nan), 1),
                 "shell_software": round(per.get("SOFTWARE_DATA", np.nan), 1),
                 "ratio": round(per.get("SALES_BD", np.nan) / per.get("SOFTWARE_DATA", np.nan), 3)})
d4 = pd.DataFrame(rows)
print(d4.to_string(index=False))
print(f"  default is {cl.SHELL_MIN_LIFT}; ratio range "
      f"{d4['ratio'].min():.3f}-{d4['ratio'].max():.3f}, "
      f"always > 1: {bool((d4['ratio'] > 1).all())}")

print("")
print("=" * 84)
print("5. CLASSIFIER — every type-dependent number, both ways")
print("=" * 84)
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j.merge(dec[["cluster", "anchored"]], on="cluster", how="left")
j["anchored"] = j["anchored"].fillna(False).astype(bool)
j["hybrid"] = j["phrase_norm"].map(
    dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))).fillna("unassigned")
pl = j[j["cluster"] != -1]
res = pl[~pl["anchored"]]
for col, nm in [("req_type", "lexicon"), ("hybrid", "hybrid")]:
    tb = pd.crosstab(res[col], res["macro_function"], normalize="columns").mul(100)
    tech = tb.loc["technical"]["SOFTWARE_DATA"] / tb.loc["technical"]["SALES_BD"]
    dom = tb.loc["domain"]["SALES_BD"] / tb.loc["domain"]["SOFTWARE_DATA"]
    un = tb.loc["unassigned"].mean() if "unassigned" in tb.index else 0
    print(f"  {nm:<8} residual: software {tech:.2f}x more technical, "
          f"sales {dom:.2f}x more domain, uncharacterised {un:.0f}%")
print(f"  overall residual (type-independent): {res['phrase'].size / pl['phrase'].size:.1%}")

d1.to_csv(W3 + r"\sweep_assignment.csv", index=False)
d2.to_csv(W3 + r"\sweep_cellsize.csv", index=False)
d3.to_csv(W3 + r"\sweep_boilerplate.csv", index=False)
d4.to_csv(W3 + r"\sweep_shell.csv", index=False)
print(f"\ntotal {time.time()-t0:.0f}s")
