"""Week 3, step 18 — employer robustness.

Employer deduplication moved the Week 2 H1 headline from 1.50x to 1.06x. It is
the single largest source of movement found anywhere in this project — larger
than the extraction weakness, larger than scope choices — so it is a primary
result rather than a robustness check, and every Week 3 estimate is computed
twice.

Three things here:

  1. the **driver ranking** recomputed with the employer as the unit. If the
     ordering changes, the advert-unit ranking was partly counting templates;
  2. the **named check** the procedure asks for by name — Commerce & Retail /
     sales, 1,753 adverts from 113 employers with one supplying 27%. It is where
     a single template most easily reads as an industry pattern;
  3. a **leave-one-cell-out** pass on the industry index, which answers a
     question weighting cannot: how much of the headline rests on any single
     cell.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import config, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

DRAWS = 150

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
extra = [c for c in ("company_size", "company_type", "seniority", "work_type")
         if c not in reqs.columns]
reqs = reqs.merge(base[["vacancy_id"] + extra], on="vacancy_id", how="left")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

# ------------------------------------------------------------------ 1. ranking
print("=" * 92)
print("1. THE DRIVER RANKING, PER EMPLOYER INSTEAD OF PER ADVERT")
print("=" * 92)
post = base.drop_duplicates("vacancy_id")
FACTORS = ["company_industry", "company_size", "company_type", "seniority",
           "geo_country", "work_type"]

# levels must clear the threshold in EMPLOYERS, not adverts, for this unit
emp = post.groupby(["macro_function"]).size()
levels = {}
for f in FACTORS:
    ct = post.groupby([f, "macro_function"])["company"].nunique().unstack(fill_value=0)
    ok = ct[(ct >= 30).all(axis=1)]
    levels[f] = ok.min(axis=1).nlargest(3).index.tolist()
    print(f"  {f:<18} {len(ok):>2} levels with >=30 employers in both -> {levels[f]}")
n_emp = min(
    int(post.groupby([f, "macro_function"])["company"].nunique().unstack(fill_value=0)
        .loc[levels[f]].min().min())
    for f in FACTORS)
print(f"\n  common cell size, n = {n_emp} employers")
print("")

rows = []
for f in FACTORS:
    boot = var.bootstrap(asg, reqs, exclude=drop, unit="company", draws=DRAWS,
                         equalise=n_emp, factor=f, levels=levels[f])
    for r in var.summarise(boot).itertuples():
        rows.append({"factor": f, "function": r.function, "js": r.js_mean,
                     "lo": r.js_lo, "hi": r.js_hi})
    print(f"  {f:<18} done [{time.time()-t0:.0f}s]", flush=True)

d = pd.DataFrame(rows)
w = d.pivot(index="factor", columns="function", values="js").round(4)
w["mean"] = w.mean(axis=1).round(4)
print("")
print("per-EMPLOYER ranking:")
print(w.sort_values("mean", ascending=False).to_string())
d.to_csv(W3 + r"\driver_ranking_employer.csv", index=False, encoding="utf-8")
print("")

# ------------------------------------------------- 2. the named cell check
print("=" * 92)
print("2. COMMERCE & RETAIL / SALES — the cell most at risk, checked explicitly")
print("=" * 92)
cell = post[(post["macro_function"] == "SALES_BD") &
            (post["company_industry"] == "Commerce & Retail")]
top = cell["company"].value_counts()
print(f"  {len(cell):,} adverts, {cell['company'].nunique()} employers")
print(f"  largest employer {top.index[0]} = {top.iloc[0]} adverts ({top.iloc[0]/len(cell):.1%})")
print(f"  top 3 = {top.head(3).sum()/len(cell):.1%} of the cell")
print("")

prof_a = var.cell_profiles(asg, reqs, exclude=drop, unit="vacancy_id")
prof_e = var.cell_profiles(asg, reqs, exclude=drop, unit="company")


def profile_vector(prof, fn, level, clusters):
    s = prof[(prof["macro_function"] == fn) & (prof["level"] == level)]
    return s.set_index("cluster")["share"].reindex(clusters, fill_value=0.0).to_numpy()


clusters = sorted(set(prof_a["cluster"]) | set(prof_e["cluster"]))
va = profile_vector(prof_a, "SALES_BD", "Commerce & Retail", clusters)
ve = profile_vector(prof_e, "SALES_BD", "Commerce & Retail", clusters)
print(f"  distance between this cell's ADVERT profile and its EMPLOYER profile:")
print(f"    JS {var._js_distance(va, ve):.4f}   cosine {var._cosine_distance(va, ve):.4f}")
others = [i for i in config.PAIRED_INDUSTRIES if i != "Commerce & Retail"]
ds = [var._js_distance(profile_vector(prof_a, "SALES_BD", i, clusters),
                       profile_vector(prof_e, "SALES_BD", i, clusters)) for i in others]
print(f"    the other 9 sales cells move {np.mean(ds):.4f} on average "
      f"(range {np.min(ds):.4f}-{np.max(ds):.4f})")
print("")

# ------------------------------------------------- 3. leave one cell out
print("=" * 92)
print("3. LEAVE ONE CELL OUT — how much rests on any single industry?")
print("=" * 92)
full = {fn: var.index_for(prof_a, fn)["js"] for fn in ("SALES_BD", "SOFTWARE_DATA")}
print(f"  full index: sales {full['SALES_BD']:.4f}, software {full['SOFTWARE_DATA']:.4f}, "
      f"ratio {full['SALES_BD']/full['SOFTWARE_DATA']:.3f}")
print("")
loo = []
for ind in config.PAIRED_INDUSTRIES:
    keep = [i for i in config.PAIRED_INDUSTRIES if i != ind]
    p = var.cell_profiles(asg, reqs, exclude=drop, unit="vacancy_id", levels=keep)
    s = var.index_for(p, "SALES_BD")["js"]
    w_ = var.index_for(p, "SOFTWARE_DATA")["js"]
    loo.append({"dropped": ind, "sales": round(s, 4), "software": round(w_, 4),
                "ratio": round(s / w_, 3)})
loo = pd.DataFrame(loo).sort_values("ratio")
print(loo.to_string(index=False))
print("")
print(f"  ratio range across all leave-one-out runs: "
      f"{loo['ratio'].min():.3f} to {loo['ratio'].max():.3f}")
loo.to_csv(W3 + r"\leave_one_out.csv", index=False, encoding="utf-8")
print(f"\ntotal {time.time()-t0:.0f}s")
