"""What would each factor's distance read if that factor changed nothing?

The driver chart plots a Jensen-Shannon distance, and a distance between two
finite samples is never 0: part of what it shows is sampling, not the labour
market. How much depends on how many adverts are in each cell, so the answer
cannot be borrowed from another measurement — it has to be computed for these
factors, at these sizes.

The permutation gives it. Keep the same three levels and the same equalised cell
size, then shuffle which advert belongs to which level. The levels are now
identical by construction, so whatever distance comes back is what this
instrument reads when the factor makes no difference at all.

Levels and sizes are selected exactly as run_language_control_all.py selects
them, or the floor would not be the floor for the numbers it is drawn under.
"""
import itertools
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import data, language as lang, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"

FACTORS = ["geo_country", "seniority", "company_industry", "company_type",
           "company_size", "work_type"]
MIN_LEVEL = 120          # the floor run_language_control_all.py uses
PERMS = 40
SEED = 20260925
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(W3 + r"\phrase_clusters_corrected.parquet")
alias = pd.read_csv(W3 + r"\alias_table_final.csv")
amap = dict(zip(alias["cluster"], alias["merged_into"]))
asg["cluster"] = asg["cluster"].map(lambda c: amap.get(c, c))
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = {amap.get(c, c) for c in
        set(named.loc[named["boilerplate"] == True, "cluster"]) |
        set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])}

# which groups each advert asks for, once, as integer codes — the permutation
# runs thousands of profiles and a groupby per profile would dominate the cost
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]
codes, uniq = pd.factorize(j["cluster"])
j = j.assign(code=codes).drop_duplicates(["vacancy_id", "code"])
K = len(uniq)
by_advert = j.groupby("vacancy_id")["code"].apply(np.array).to_dict()

base = data.build_analysis_base().df
det = lang.detect_series(base["must_have"])
base["text_lang"] = det["detected"].where(det["hits"] >= 1, base["language"])
post = base.drop_duplicates("vacancy_id")
eng = post[post["text_lang"] == "English"]
print(f"prepared in {time.time()-t0:.0f}s: {K} groups, {len(by_advert):,} adverts")
print("")


def profile(ids):
    out = np.zeros(K)
    n = 0
    for i in ids:
        a = by_advert.get(i)
        if a is not None:
            out[a] += 1
            n += 1
    return out / n if n else out


def mean_pairwise(groups):
    return float(np.mean([var._js_distance(a, b)
                          for a, b in itertools.combinations(groups, 2)]))


rng = np.random.default_rng(SEED)
rows = []
for f in FACTORS:
    ct_all = pd.crosstab(post[f], post["macro_function"])
    ct_en = pd.crosstab(eng[f], eng["macro_function"])
    ok = [lv for lv in ct_all.index
          if lv in ct_en.index
          and (ct_all.loc[lv] >= MIN_LEVEL).all() and (ct_en.loc[lv] >= MIN_LEVEL).all()]
    if len(ok) < 3:
        print(f"  {f:<18} UNPOWERED")
        continue
    top = ct_en.loc[ok].min(axis=1).nlargest(3).index.tolist()
    n = int(min(ct_en.loc[top].min().min(), ct_all.loc[top].min().min()))

    per_fn = []
    for fn in ("SOFTWARE_DATA", "SALES_BD"):
        sub = post[(post["macro_function"] == fn) & (post[f].isin(top))]
        pool = sub["vacancy_id"].to_numpy()
        draws = []
        for _ in range(PERMS):
            # three groups of n drawn from a pool where the level no longer means
            # anything — same sizes, same number of levels, no real difference.
            # Drawn WITH replacement because variance.bootstrap does (line 143):
            # replacement makes a draw noisier, so a null drawn without it would
            # be measured on a cleaner sample than the figure it anchors and the
            # gap between them would be an artefact of the two draw styles.
            draws.append(mean_pairwise(
                [profile(rng.choice(pool, size=n, replace=True)) for _ in range(3)]))
        per_fn.append(float(np.mean(draws)))
    rows.append({"factor": f, "levels": 3, "n": n, "null": float(np.mean(per_fn))})
    print(f"  {f:<18} n={n:<5} null {rows[-1]['null']:.4f}   "
          f"{', '.join(str(x)[:16] for x in top)}")

d = pd.DataFrame(rows)
d.to_csv(W3 + r"\driver_null.csv", index=False, encoding="utf-8")

dd = pd.read_csv(W3 + r"\driver_dumbbell.csv", index_col=0)
m = d.set_index("factor").join(dd)
m["excess_raw"] = (m["raw"] - m["null"]).round(4)
m["excess_ctrl"] = (m["controlled"] - m["null"]).round(4)
print("")
print(m[["null", "raw", "controlled", "excess_raw", "excess_ctrl"]].round(4).to_string())
print(f"\nwritten: driver_null.csv   total {time.time()-t0:.0f}s")
