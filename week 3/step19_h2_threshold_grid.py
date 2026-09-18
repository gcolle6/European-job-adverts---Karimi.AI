"""Does the H2 novelty/vagueness DIRECTION survive threshold movement?

The counts do not: moving both thresholds by 0.05 changes the novelty group
count sevenfold, because 70% of groups sit within 0.05 of the consistency
cut-off. But H2 is a COMPARISON between functions at the same thresholds, which
is a different quantity and can survive what the classification does not.
"""
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 220)

res = pd.read_csv(W3 + r"\residual_by_reason.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j[j["cluster"].isin(res["cluster"])]
tot = j.groupby("macro_function").size()

rows = []
for ent in [0.20, 0.25, 0.30, 0.35, 0.40]:
    for con in [0.74, 0.77, 0.80, 0.83, 0.86]:
        r = res[res["reason"] != "structural"].copy()
        r["lab"] = "other"
        r.loc[(r["entity_share"] >= ent) & (r["consistency"] >= con), "lab"] = "novelty"
        r.loc[(r["entity_share"] < ent) & (r["consistency"] < con), "lab"] = "vagueness"
        m = dict(zip(r["cluster"], r["lab"]))
        s = j[j["cluster"].isin(m)].copy()
        s["lab"] = s["cluster"].map(m)
        p = s.groupby(["lab", "macro_function"]).size().unstack(fill_value=0) / tot * 100
        if "novelty" not in p.index or "vagueness" not in p.index:
            continue
        rows.append({
            "entity": ent, "consistency": con,
            "nov_ratio": round(p.loc["novelty", "SOFTWARE_DATA"] / p.loc["novelty", "SALES_BD"], 2),
            "vag_ratio_sales": round(p.loc["vagueness", "SALES_BD"] / p.loc["vagueness", "SOFTWARE_DATA"], 2)})
d = pd.DataFrame(rows)
print(d.to_string(index=False))
print(f"\nnovelty  software:sales   median {d['nov_ratio'].median():.2f}  "
      f"always > 1: {bool((d['nov_ratio'] > 1).all())}")
print(f"vagueness sales:software  median {d['vag_ratio_sales'].median():.2f}  "
      f"always > 1: {bool((d['vag_ratio_sales'] > 1).all())}")
