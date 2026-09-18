"""Week 3, step 19 — split the ESCO residual by REASON, which is what H2 claims.

H2 does not claim that both families have a large residual; that is already
measured at 26.9%. It claims the residual exists **for different reasons** —
software through *novelty*, sales through *vagueness and domain specificity*.
Week 2 showed a type asymmetry, and a requirement type is not a reason: `technical`
is consistent with novelty without demonstrating it.

Reasons are therefore assigned from features of the group itself, each stated
before the run:

  **novelty** — the group NAMES something the catalogue has not listed. Testable:
    its members carry a named entity (a capitalised token that is not
    sentence-initial, or a token with a digit or symbol like `C#`, `Java 17`,
    `S/4HANA`), and they are CONSISTENT with each other — a real named thing is
    written the same way by everyone.

  **vagueness** — the group names nothing. Testable: no named entity, and its
    members are heterogeneous — `Track record of clean` and `experience in a
    similar position` do not converge because there is nothing to converge on.

  **structural** — credentials and availability, which ESCO does not model at
    all. Not evidence about the labour market either way, and already excluded
    from the headline.

Consistency is measured as the mean similarity of members to their own centre,
which Week 2 already stored — a number that exists independently of this step.
"""
import re
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

# a named entity: a capitalised token that is not the first word, or any token
# carrying a digit or a product symbol. Set before looking at the output.
ENTITY_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][A-Za-z0-9]{1,}\b|"
                       r"\b\w*[0-9#+/][\w#+./]*\b")
CONSISTENT_MIN = 0.80          # mean member-to-centre similarity
ENTITY_MIN = 0.30              # share of members carrying an entity

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
dec = pd.read_csv(OUT + r"\esco_decisions.csv")
dec["anchored"] = dec["anchored"].astype(str).str.strip().str.lower().eq("true")

reqs["type"] = reqs["phrase_norm"].map(
    dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))).fillna("unassigned")
j = reqs.merge(asg[["phrase_norm", "cluster", "similarity"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j.merge(dec[["cluster", "anchored"]], on="cluster", how="left")
# `~` on an object column is bitwise negation on integers, not boolean NOT, and
# it has produced a wrong number three times in this project. Cast, do not trust.
j["anchored"] = j["anchored"].fillna(False).astype(bool)
placed = j[j["cluster"] != -1].copy()
placed["has_entity"] = placed["phrase"].astype(str).str.contains(ENTITY_RE, na=False)

# ------------------------------------------------------- per-group features
g = placed.groupby("cluster").agg(
    occurrences=("phrase", "size"),
    entity_share=("has_entity", "mean"),
    consistency=("similarity", "mean"),
    anchored=("anchored", "first"),
).reset_index().merge(named[["cluster", "label", "top_type"]], on="cluster", how="left")
g["anchored"] = g["anchored"].astype(bool)
mode_type = placed.groupby("cluster")["type"].agg(lambda s: s.mode().iat[0])
g["type"] = g["cluster"].map(mode_type)

res = g[~g["anchored"]].copy()
res["reason"] = "other"
res.loc[res["type"].isin(["credential", "availability"]), "reason"] = "structural"
mask = res["reason"] == "other"
res.loc[mask & (res["entity_share"] >= ENTITY_MIN) &
        (res["consistency"] >= CONSISTENT_MIN), "reason"] = "novelty"
res.loc[mask & (res["entity_share"] < ENTITY_MIN) &
        (res["consistency"] < CONSISTENT_MIN), "reason"] = "vagueness"

print("=" * 92)
print("THE RESIDUAL GROUPS, SPLIT BY REASON")
print("=" * 92)
print(f"  residual groups: {len(res)} of {len(g)}")
print(res.groupby("reason").agg(groups=("cluster", "size"),
                                occurrences=("occurrences", "sum")).to_string())
print("")
for reason in ["novelty", "vagueness", "structural", "other"]:
    sub = res[res["reason"] == reason].nlargest(6, "occurrences")
    print(f"  {reason.upper()} — largest groups:")
    for r in sub.itertuples():
        print(f"    {r.occurrences:>5}  {str(r.label)[:44]:<46} "
              f"entity {r.entity_share:.2f}  consistency {r.consistency:.3f}")
    print("")

# ------------------------------------------------- reason by function (mass)
print("=" * 92)
print("H2: DOES THE REASON DIFFER BY FUNCTION?")
print("=" * 92)
rmap = dict(zip(res["cluster"], res["reason"]))
rp = placed[~placed["anchored"]].copy()
rp["reason"] = rp["cluster"].map(rmap)
tab = pd.crosstab(rp["reason"], rp["macro_function"], normalize="columns").mul(100).round(1)
tab["sw_over_sales"] = (tab["SOFTWARE_DATA"] / tab["SALES_BD"].replace(0, np.nan)).round(2)
print("share of each family's residual mass, by reason:")
print(tab.to_string())
print("")
print("excluding structural (ESCO models neither credentials nor availability):")
nb = rp[rp["reason"] != "structural"]
t2 = pd.crosstab(nb["reason"], nb["macro_function"], normalize="columns").mul(100).round(1)
t2["sw_over_sales"] = (t2["SOFTWARE_DATA"] / t2["SALES_BD"].replace(0, np.nan)).round(2)
print(t2.to_string())
print("")

# ------------------------------------------------- residual by industry
print("=" * 92)
print("RESIDUAL SHARE BY FUNCTION AND INDUSTRY")
print("=" * 92)
placed["in_res"] = ~placed["anchored"]
byi = (placed.groupby(["macro_function", "company_industry"])["in_res"].mean()
       .mul(100).round(1).unstack(0))
byi["gap_pp"] = (byi["SOFTWARE_DATA"] - byi["SALES_BD"]).round(1)
print(byi.sort_values("SOFTWARE_DATA", ascending=False).to_string())

res.to_csv(W3 + r"\residual_by_reason.csv", index=False, encoding="utf-8")
print("")
print(f"written: residual_by_reason.csv   total {time.time()-t0:.0f}s")
