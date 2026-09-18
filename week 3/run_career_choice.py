"""Two moves, compared: climb a level, or change industry?

Week 3 measured how MUCH each factor moves the requirement profile. For someone
deciding between the two, that is only half an answer — the other half is WHAT
moves, because a step that adds management duties and a step that adds domain
knowledge are not the same experience even at the same distance.

So: the same person, the same job family, one variable at a time.

  * climb  — Junior to Senior, industry held constant
  * switch — industry to industry, seniority held constant

For each, which requirement groups appear and which disappear, and what KIND of
requirement they are. Cells are matched on size so the two deltas are comparable,
and the comparison runs inside each job family rather than across them.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")
lab = dict(zip(named["cluster"], named["label"]))
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

post = base.drop_duplicates("vacancy_id")
reqs = reqs.merge(post[["vacancy_id", "seniority"]], on="vacancy_id", how="left")
reqs["type"] = reqs["phrase_norm"].map(
    dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))).fillna("unassigned")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]

ctype = j.groupby("cluster")["type"].agg(lambda s: s.mode().iat[0]).to_dict()


def shares(frame):
    n = frame["vacancy_id"].nunique()
    return frame.groupby("cluster")["vacancy_id"].nunique() / n, n


def delta(a, b, label_a, label_b, top=8):
    sa, na = shares(a)
    sb, nb = shares(b)
    d = pd.DataFrame({"a": sa, "b": sb}).fillna(0.0)
    d["gap"] = d["b"] - d["a"]
    d["label"] = [str(lab.get(c, "?")) for c in d.index]
    d["type"] = [ctype.get(c, "?") for c in d.index]
    print(f"\n  {label_a} ({na:,} adverts)  ->  {label_b} ({nb:,} adverts)")
    print(f"    total movement, summed over all groups: {d['gap'].abs().sum():.2f}")
    print(f"    what you are asked for MORE:")
    for _, r in d.nlargest(top, "gap").iterrows():
        print(f"      +{r['gap']*100:>5.1f}pp  {r['label'][:38]:<40} [{r['type']}]")
    print(f"    what you are asked for LESS:")
    for _, r in d.nsmallest(4, "gap").iterrows():
        print(f"      {r['gap']*100:>6.1f}pp  {r['label'][:38]:<40} [{r['type']}]")
    return d


print("=" * 92)
print("MOVE 1 — CLIMB A LEVEL, STAYING PUT")
print("=" * 92)
climbs = {}
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    sub = j[j["macro_function"] == fn]
    jr = sub[sub["seniority"] == "Junior"]
    sr = sub[sub["seniority"] == "Senior"]
    climbs[fn] = delta(jr, sr, f"{fn} Junior", "Senior")

print("")
print("=" * 92)
print("MOVE 2 — CHANGE INDUSTRY, STAYING AT THE SAME LEVEL")
print("=" * 92)
switches = {}
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    sub = j[(j["macro_function"] == fn) & (j["seniority"] == "Mid-level")]
    top2 = sub.groupby("company_industry")["vacancy_id"].nunique().nlargest(2).index.tolist()
    a = sub[sub["company_industry"] == top2[0]]
    b = sub[sub["company_industry"] == top2[1]]
    switches[fn] = delta(a, b, f"{fn} {top2[0]}", top2[1])

print("")
print("=" * 92)
print("WHAT KIND OF THING CHANGES, IN EACH MOVE")
print("=" * 92)
print(f"{'':<34}{'climb a level':>18}{'change industry':>18}")
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    c = climbs[fn].copy(); s = switches[fn].copy()
    print(f"  {fn}")
    for ty in ("soft", "technical", "domain", "credential", "language"):
        cm = c.loc[c["type"] == ty, "gap"].abs().sum()
        sm = s.loc[s["type"] == ty, "gap"].abs().sum()
        print(f"    {ty:<30}{cm:>18.2f}{sm:>18.2f}")

print("")
print("=" * 92)
print("HOW MUCH OF WHAT YOU ALREADY HAVE STILL COUNTS")
print("=" * 92)
for fn in ("SOFTWARE_DATA", "SALES_BD"):
    c, s = climbs[fn], switches[fn]
    for nm, d in (("climbing a level", c), ("changing industry", s)):
        # share of the destination's demand that the origin already asked for
        overlap = np.minimum(d["a"], d["b"]).sum() / d["b"].sum()
        print(f"  {fn:<16} {nm:<20} {overlap:.1%} of what the new role asks for, "
              f"the old one already asked for")

print(f"\ntotal {time.time()-t0:.0f}s")
