"""Two defects from the register that cost machine time only: E3 and C3.

E3 — the threshold sweep had two stated deviations. The boilerplate CV default
is 0.60 and only 0.30-0.50 was swept, so the default itself sat outside the
tested range; and the bootstrap ran 200 draws against a configured 1,000.

C3 — `work_type` carries an empty-string level, which appeared as one of the
three levels in the driver ranking. It is a data-quality problem in the field
rather than a category, and it has never been quantified.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import cluster as cl, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 250)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
base = data.build_analysis_base().df
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
mixed = set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])


def h1(exclude):
    prof = var.cell_profiles(asg, reqs, exclude=exclude)
    return (var.index_for(prof, "SALES_BD")["js"] /
            var.index_for(prof, "SOFTWARE_DATA")["js"])


print("=" * 84)
print("C3. THE EMPTY work_type LEVEL")
print("=" * 84)
post = base.drop_duplicates("vacancy_id")
wt = post["work_type"].fillna("").astype(str).str.strip()
print(post.assign(wt=wt).groupby("wt").size().rename("adverts").to_frame()
      .assign(share=lambda d: (d["adverts"] / len(post) * 100).round(1)).to_string())
empty = wt.eq("")
print(f"\n  empty: {int(empty.sum()):,} adverts ({empty.mean():.1%})")
print(f"  by function: " + ", ".join(
    f"{k} {v:.1%}" for k, v in post.assign(e=empty).groupby("macro_function")["e"].mean().items()))
levels_all = ["on-site", "hybrid", ""]
levels_clean = [w for w in wt.value_counts().index if w][:3]
print(f"\n  driver-ranking levels as run : {levels_all}")
print(f"  with the empty level dropped : {levels_clean}")

reqs_wt = reqs.merge(post[["vacancy_id", "work_type"]], on="vacancy_id", how="left")
reqs_wt["work_type"] = reqs_wt["work_type"].fillna("").astype(str).str.strip()
for label, lv in [("as run (includes empty)", levels_all),
                  ("empty level dropped", levels_clean)]:
    boot = var.bootstrap(asg, reqs_wt, exclude=mixed, unit="vacancy_id", draws=60,
                         equalise=578, factor="work_type", levels=lv)
    s = var.summarise(boot)
    vals = {r.function: r.js_mean for r in s.itertuples()}
    print(f"  {label:<26} sales {vals.get('SALES_BD', float('nan')):.4f}  "
          f"software {vals.get('SOFTWARE_DATA', float('nan')):.4f}  "
          f"mean {sum(vals.values())/len(vals):.4f}")
print("  (work_type ranked last or second-last at 0.2542-0.2666; compare against that)")

print("")
print("=" * 84)
print("E3a. BOILERPLATE CV — sweeping ABOVE the default this time")
print("=" * 84)
shares = cl.cell_shares(asg, reqs)
bp = cl.classify_boilerplate(shares)
rows = []
for ms in [0.08, 0.10, 0.12]:
    for cv in [0.50, 0.60, 0.70, 0.80]:
        keep = set(bp.loc[(bp["mean_share"] >= ms) & (bp["cv"] <= cv), "cluster"])
        rows.append({"min_share": ms, "max_cv": cv, "boilerplate_groups": len(keep),
                     "H1_ratio": round(h1(keep | mixed), 3)})
d = pd.DataFrame(rows)
print(d.to_string(index=False))
print(f"  default {cl.BOILERPLATE_MIN_MEAN_SHARE}/{cl.BOILERPLATE_MAX_CV} now inside the range; "
      f"H1 {d['H1_ratio'].min():.3f}-{d['H1_ratio'].max():.3f}, "
      f"always > 1: {bool((d['H1_ratio'] > 1).all())}")

print("")
print("=" * 84)
print("E3b. BOOTSTRAP AT THE CONFIGURED 1,000 DRAWS")
print("=" * 84)
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | mixed
boot = var.bootstrap(asg, reqs, exclude=drop, unit="vacancy_id", draws=1000)
print(var.summarise(boot).to_string(index=False))
for m in ("js", "cosine"):
    r = var.ratio_interval(boot, metric=m)
    print(f"  sales:software {m:<7} {r['ratio']:.3f}  95% [{r['lo']:.3f}, {r['hi']:.3f}]  "
          f"P(>1)={r['p_ratio_above_1']:.3f}")
print("  compare with 200 draws: js 1.182 [1.159, 1.205]")
print(f"\ntotal {time.time()-t0:.0f}s")
