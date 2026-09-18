"""Week 3, step 16 — the variance index.

Runs the statistic fixed in the plan: mean pairwise Jensen-Shannon distance
between L1-normalised cell profiles, with mean pairwise cosine distance as a
companion, bootstrapped for an interval, and computed both per advert and per
employer.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import config, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
print(f"groups excluded: {len(drop)} "
      f"({int((named['boilerplate'] == True).sum())} boilerplate, "
      f"{int((named['label'].astype(str).str.upper() == 'MIXED').sum())} MIXED)")
print(f"industries in scope: {len(config.PAIRED_INDUSTRIES)}")
print("")

for unit, name in [("vacancy_id", "PER ADVERT"), ("company", "PER EMPLOYER")]:
    print("=" * 84)
    print(f"{name}")
    print("=" * 84)
    prof = var.cell_profiles(asg, reqs, exclude=drop, unit=unit)
    sizes = prof.groupby(["macro_function", "company_industry"])["total"].first()
    print(f"  cell sizes: min {int(sizes.min())}, median {int(sizes.median())}, "
          f"max {int(sizes.max())}")
    for fn in sorted(prof["macro_function"].unique()):
        r = var.index_for(prof, fn)
        print(f"  {fn:<16} cells {r['n_cells']:>2}  groups {r['n_groups']:>3}  "
              f"JS {r['js']:.4f}  cosine {r['cosine']:.4f}  "
              f"(JS range {r['js_min']:.3f}-{r['js_max']:.3f})")
    print("")

print("=" * 84)
print("BOOTSTRAP — is the difference bigger than sampling noise?")
print("=" * 84)
boot = var.bootstrap(asg, reqs, exclude=drop, unit="vacancy_id", draws=200)
print(var.summarise(boot).to_string(index=False))
print("")
for m in ("js", "cosine"):
    r = var.ratio_interval(boot, metric=m)
    print(f"  sales : software  {m:<7} {r['ratio']:.3f}  "
          f"95% [{r['lo']:.3f}, {r['hi']:.3f}]   P(ratio>1) = {r['p_ratio_above_1']:.3f}")
print("")

print("=" * 84)
print("EQUALISED CELLS — does the difference survive removing the size gap?")
print("=" * 84)
boot_eq = var.bootstrap(asg, reqs, exclude=drop, unit="vacancy_id",
                        draws=200, equalise=300)
print(var.summarise(boot_eq).to_string(index=False))
print("")
for m in ("js", "cosine"):
    r = var.ratio_interval(boot_eq, metric=m)
    print(f"  sales : software  {m:<7} {r['ratio']:.3f}  "
          f"95% [{r['lo']:.3f}, {r['hi']:.3f}]   P(ratio>1) = {r['p_ratio_above_1']:.3f}")

boot.to_csv(W3 + r"\variance_bootstrap.csv", index=False, encoding="utf-8")
boot_eq.to_csv(W3 + r"\variance_bootstrap_equalised.csv", index=False, encoding="utf-8")
print("")
print(f"total {time.time() - t0:.0f}s")
