"""Two countermeasures owed on the variance index before Week 3 goes further.

Both are required by decisions already recorded, and neither was applied when
steps 16-18 ran. Running them late is worse than running them first; not running
them at all would be indefensible.

**1. Repeat postings.** `COLLAPSE_REPEAT_POSTINGS = False` keeps repeat adverts
because repeat advertising is itself demand signal — but the recorded rule is
that *count* questions use rows while *requirement-profile* questions use
`repeat_weight`. The variance index is a requirement-profile question. Repeat
groups reach 41 adverts, so an unweighted template can carry 41x the weight
inside a cell and **deflate within-cell variance** — which is the exact quantity
H1 turns on.

**2. B2B-only sales scope.** Shop-floor work is 10.1% of SALES_BD overall but
**53.0% of Commerce & Retail / SALES_BD**. It therefore sits in one cell and
*inflates* between-industry variance for sales — again the exact quantity H1
turns on, and in the direction that flatters the hypothesis. The recorded
decision is that every headline estimate is reported on all of SALES_BD and on
B2B only, and that **the B2B-only run is the conservative one**.

If H1's direction survives both, it is not an artefact of either. If it does not,
that is the finding.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 250)
t0 = time.time()

DRAWS = 150

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

flags = base[["vacancy_id", "is_repeat_first", "b2b", "shop_floor", "repeat_group_size"]]
reqs = reqs.merge(flags, on="vacancy_id", how="left")

print(f"adverts in repeat groups: "
      f"{int((base['repeat_group_size'] > 1).sum()):,} of {len(base):,} "
      f"({(base['repeat_group_size'] > 1).mean():.1%}), largest group "
      f"{int(base['repeat_group_size'].max())}")
sales = base[base["macro_function"] == "SALES_BD"]
print(f"SALES_BD shop-floor: {sales['shop_floor'].mean():.1%} overall")
cr = sales[sales["company_industry"] == "Commerce & Retail"]
print(f"  Commerce & Retail / sales: {cr['shop_floor'].mean():.1%}")
print("")


def run(frame, label):
    prof = var.cell_profiles(asg, frame, exclude=drop, unit="vacancy_id")
    out = {}
    for fn in ("SALES_BD", "SOFTWARE_DATA"):
        r = var.index_for(prof, fn)
        out[fn] = r["js"]
    ratio = out["SALES_BD"] / out["SOFTWARE_DATA"]
    boot = var.bootstrap(asg, frame, exclude=drop, unit="vacancy_id", draws=DRAWS)
    ri = var.ratio_interval(boot, metric="js")
    print(f"  {label:<34} sales {out['SALES_BD']:.4f}  software {out['SOFTWARE_DATA']:.4f}  "
          f"ratio {ratio:.3f}   bootstrap {ri['ratio']:.3f} "
          f"[{ri['lo']:.3f}, {ri['hi']:.3f}]  P(>1)={ri['p_ratio_above_1']:.3f}",
          flush=True)
    return ratio


print("=" * 100)
print("THE TWO COUNTERMEASURES")
print("=" * 100)
run(reqs, "headline (as run in step 16)")
run(reqs[reqs["is_repeat_first"] == True], "repeat groups collapsed to one")

# B2B applies to sales only; software is untouched and must stay in the frame
b2b_only = reqs[(reqs["macro_function"] == "SOFTWARE_DATA") | (reqs["b2b"] == True)]
run(b2b_only, "sales restricted to B2B")

both = b2b_only[b2b_only["is_repeat_first"] == True]
run(both, "both at once (most conservative)")

print("")
print(f"total {time.time()-t0:.0f}s")
