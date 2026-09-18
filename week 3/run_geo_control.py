"""Is "changing industry" partly "changing country"? The blocking check.

The climb-versus-switch comparison found that changing industry keeps ~70% of
what you already have while climbing a level keeps 41-51%. But industries are not
spread evenly across countries — `+Swedish fluency` turned up in a software
industry comparison because one of the two cells is Saab-heavy — so part of what
was measured as an industry step is a country step.

The fix is to make both comparisons happen **inside one country**. If the overlap
figures hold, the finding survives and can be published. If the industry overlap
rises sharply once country is held constant, then changing industry costs even
less than reported and the headline understates its own conclusion. Either way
the number changes, which is why nothing built on it should ship first.

Climbing is checked the same way, as a control: seniority has no obvious reason
to be geographically confounded, so if the climb figure moves as much as the
switch figure, something other than geography is driving both.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import data

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

MIN_CELL = 120          # adverts needed on each side of a comparison

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

post = base.drop_duplicates("vacancy_id")
reqs = reqs.merge(post[["vacancy_id", "seniority"]], on="vacancy_id", how="left")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]


def shares(frame):
    n = frame["vacancy_id"].nunique()
    return (frame.groupby("cluster")["vacancy_id"].nunique() / n) if n else None, n


def overlap(a, b):
    """Share of the destination's demand that the origin already asked for."""
    sa, na = shares(a)
    sb, nb = shares(b)
    if sa is None or sb is None or na < MIN_CELL or nb < MIN_CELL:
        return None, na, nb
    d = pd.DataFrame({"a": sa, "b": sb}).fillna(0.0)
    return float(np.minimum(d["a"], d["b"]).sum() / d["b"].sum()), na, nb


print("=" * 96)
print("1. CHANGING INDUSTRY — POOLED (as first reported) vs WITHIN ONE COUNTRY")
print("=" * 96)
rows = []
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    sub = j[(j["macro_function"] == fn) & (j["seniority"] == "Mid-level")]
    inds = sub.groupby("company_industry")["vacancy_id"].nunique()
    inds = inds[inds >= MIN_CELL].index.tolist()

    pooled = []
    for i, x in enumerate(inds):
        for y in inds[i + 1:]:
            o, _, _ = overlap(sub[sub["company_industry"] == x],
                              sub[sub["company_industry"] == y])
            if o is not None:
                pooled.append(o)

    within = []
    detail = []
    for ctry, g in sub.groupby("geo_country"):
        gi = g.groupby("company_industry")["vacancy_id"].nunique()
        gi = gi[gi >= MIN_CELL].index.tolist()
        for i, x in enumerate(gi):
            for y in gi[i + 1:]:
                o, na, nb = overlap(g[g["company_industry"] == x],
                                    g[g["company_industry"] == y])
                if o is not None:
                    within.append(o)
                    detail.append((ctry, x, y, o, na, nb))

    print(f"\n  {fn}")
    print(f"    pooled across countries : {np.mean(pooled):.1%}   ({len(pooled)} industry pairs)")
    if within:
        print(f"    WITHIN one country      : {np.mean(within):.1%}   ({len(within)} pairs)")
        print(f"    difference              : {np.mean(within)-np.mean(pooled):+.1%}")
        print(f"    the within-country pairs:")
        for ctry, x, y, o, na, nb in sorted(detail, key=lambda r: -r[3])[:6]:
            print(f"      {str(ctry)[:14]:<16}{str(x)[:24]:<26} vs {str(y)[:24]:<26} {o:>6.1%}"
                  f"  ({na}/{nb})")
    else:
        print("    WITHIN one country      : no country has two industries above the floor")
    rows.append({"function": fn, "move": "change industry",
                 "pooled": np.mean(pooled) if pooled else None,
                 "within_country": np.mean(within) if within else None})

print("")
print("=" * 96)
print("2. CONTROL — IS CLIMBING CONFOUNDED THE SAME WAY?")
print("=" * 96)
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    sub = j[j["macro_function"] == fn]
    o_pool, na, nb = overlap(sub[sub["seniority"] == "Junior"],
                             sub[sub["seniority"] == "Senior"])
    within = []
    for ctry, g in sub.groupby("geo_country"):
        o, _, _ = overlap(g[g["seniority"] == "Junior"], g[g["seniority"] == "Senior"])
        if o is not None:
            within.append(o)
    print(f"\n  {fn}")
    print(f"    pooled across countries : {o_pool:.1%}")
    if within:
        print(f"    WITHIN one country      : {np.mean(within):.1%}   ({len(within)} countries)")
        print(f"    difference              : {np.mean(within)-o_pool:+.1%}")
    rows.append({"function": fn, "move": "climb a level", "pooled": o_pool,
                 "within_country": np.mean(within) if within else None})

print("")
print("=" * 96)
print("3. THE TABLE THAT GOES IN THE ARTICLE")
print("=" * 96)
d = pd.DataFrame(rows)
d["pooled"] = (d["pooled"] * 100).round(1)
d["within_country"] = (d["within_country"] * 100).round(1)
d["shift"] = (d["within_country"] - d["pooled"]).round(1)
print(d.to_string(index=False))
d.to_csv(W3 + r"\geo_control.csv", index=False, encoding="utf-8")
print("\n  'pooled' is what was first reported; 'within_country' holds geography constant.")
print(f"\ntotal {time.time()-t0:.0f}s")
