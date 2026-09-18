"""Week 3, step 17 — which factor moves requirements most.

Industry is the factor this study was designed around. It is not obviously the
biggest one, and if company size or seniority moves requirements more, that
reframes the write-up.

**The comparison is only meaningful if the factors are put on equal terms**, and
two things otherwise decide the answer before the data does:

  * **number of levels.** Mean pairwise distance over 10 industries is not
    comparable with mean pairwise distance over 4 seniority bands — more levels
    means more distant pairs. Every factor is therefore cut to the SAME number
    of levels, the largest k that all powered factors can supply.
  * **cell size.** Noise inflates distance, so a factor whose levels are smaller
    scores higher for free. Every level is bootstrapped to the same n.

Without both, the ranking measures how a field was coded rather than what it
does. A factor is reported as UNPOWERED rather than estimated when it cannot
supply k levels above `MIN_CELL_SIZE` in both functions.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import config, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

FACTORS = ["company_industry", "company_size", "company_type", "seniority",
           "geo_country", "work_type"]
MIN_LEVEL = config.MIN_CELL_SIZE
DRAWS = 150

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

extra = [f for f in FACTORS if f not in reqs.columns]
reqs = reqs.merge(base[["vacancy_id"] + extra], on="vacancy_id", how="left")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
print(f"joined {extra}; {len(drop)} groups excluded; MIN_CELL_SIZE = {MIN_LEVEL}")
print("")

# ---------------------------------------------------------------- power table
print("=" * 92)
print("WHICH COMPARISONS ARE POWERED")
print("=" * 92)
post = base.drop_duplicates("vacancy_id")
powered = {}
for f in FACTORS:
    ct = pd.crosstab(post[f], post["macro_function"])
    ok = ct[(ct >= MIN_LEVEL).all(axis=1)]
    powered[f] = list(ok.index)
    print(f"{f:<18} {ct.shape[0]:>3} levels, {len(ok):>2} above {MIN_LEVEL} in BOTH functions"
          f"   -> {', '.join(map(str, ok.index[:6]))}{' ...' if len(ok) > 6 else ''}")
print("")

k = min(len(v) for v in powered.values() if len(v) >= 2)
usable = {f: v for f, v in powered.items() if len(v) >= 2}
unpowered = [f for f in FACTORS if len(powered[f]) < 2]
print(f"common number of levels, k = {k}  (every factor cut to its k largest cells)")
if unpowered:
    print(f"UNPOWERED, not estimated: {unpowered}")
print("")

# cut each factor to its k largest levels, then find a common cell size
sizes = {}
for f, lv in usable.items():
    ct = pd.crosstab(post[f], post["macro_function"]).loc[lv]
    top = ct.min(axis=1).nlargest(k).index.tolist()
    usable[f] = top
    sizes[f] = int(ct.loc[top].min().min())
n_common = min(sizes.values())
print(f"common cell size, n = {n_common}  (smallest cell across all factors at k={k})")
for f in usable:
    print(f"  {f:<18} levels {usable[f]}")
print("")

# ---------------------------------------------------------------- the ranking
print("=" * 92)
print(f"THE RANKING — k={k} levels each, bootstrapped to n={n_common} adverts per cell")
print("=" * 92)
rows = []
for f, lv in usable.items():
    boot = var.bootstrap(asg, reqs, exclude=drop, unit="vacancy_id", draws=DRAWS,
                         equalise=n_common, factor=f, levels=lv)
    s = var.summarise(boot)
    for r in s.itertuples():
        rows.append({"factor": f, "function": r.function, "levels": k,
                     "js": r.js_mean, "js_lo": r.js_lo, "js_hi": r.js_hi,
                     "cosine": r.cosine_mean})
    print(f"  {f:<18} done  [{time.time()-t0:.0f}s]", flush=True)

d = pd.DataFrame(rows)
print("")
wide = d.pivot(index="factor", columns="function", values="js").round(4)
wide["mean"] = wide.mean(axis=1).round(4)
wide = wide.sort_values("mean", ascending=False)
print("Jensen-Shannon index by factor (higher = moves requirements more):")
print(wide.to_string())
print("")
print("with intervals:")
print(d.sort_values(["function", "js"], ascending=[True, False])[
    ["function", "factor", "js", "js_lo", "js_hi", "cosine"]].to_string(index=False))

d.to_csv(W3 + r"\driver_ranking.csv", index=False, encoding="utf-8")
print("")
print(f"written: driver_ranking.csv   total {time.time()-t0:.0f}s")
