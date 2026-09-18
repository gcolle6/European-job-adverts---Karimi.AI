"""Volume or repetition — which one actually distorts?

The first pass found these are not the same thing, and the gap is wide enough to
matter. Inetum posts 975 adverts, more than anyone, and its adverts resemble each
other no more than random adverts do (excess +0.007): 975 genuine observations.
Worten posts 86 that are 92% identical: closer to one observation repeated.

So "large employer" is the wrong variable. This tests the right one directly —
drop the most REPETITIVE employers and, as a control, drop the same number of the
LARGEST, and see which treatment moves the headline.
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
tpl = pd.read_csv(W3 + r"\employer_templates.csv")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

post = base.drop_duplicates("vacancy_id")
counts = post["company"].value_counts()


def h1(frame, unit="vacancy_id"):
    prof = var.cell_profiles(asg, frame, exclude=drop, unit=unit)
    a = var.index_for(prof, "SALES_BD")["js"]
    b = var.index_for(prof, "SOFTWARE_DATA")["js"]
    return a / b


base_r = h1(reqs)
print("=" * 92)
print("VOLUME OR REPETITION — WHICH ONE DISTORTS?")
print("=" * 92)
print(f"  headline with everyone: {base_r:.3f}")
print("")
print(f"{'treatment':<46}{'adverts lost':>14}{'ratio':>9}{'shift':>9}")
for n in (10, 20, 40):
    rep = set(tpl.nlargest(n, "excess")["company"])
    vol = set(counts.head(n).index)
    for label, drop_set in [(f"drop the {n} most REPETITIVE employers", rep),
                            (f"drop the {n} LARGEST employers", vol)]:
        f = reqs[~reqs["company"].isin(drop_set)]
        lost = reqs["vacancy_id"].nunique() - f["vacancy_id"].nunique()
        r = h1(f)
        print(f"  {label:<44}{lost:>14,}{r:>9.3f}{r-base_r:>+9.3f}")
    print("")

print("=" * 92)
print("HOW MUCH OF THE CORPUS IS EFFECTIVELY DUPLICATE?")
print("=" * 92)
# an employer's adverts are worth, in effect, somewhere between 1 and n
# observations; excess self-similarity is the crude discount
t = tpl.copy()
t["effective"] = t["adverts"] * (1 - t["own_similarity"].clip(0, 1))
covered = int(t["adverts"].sum())
print(f"  employers with 20+ adverts hold {covered:,} adverts "
      f"({covered/len(post):.1%} of the corpus)")
print(f"  discounting each by how much it repeats itself leaves "
      f"{t['effective'].sum():,.0f} effective adverts")
print(f"  so this slice is worth about {t['effective'].sum()/covered:.0%} of its nominal size")
print("")
heavy = t[t["own_similarity"] >= 0.40]
print(f"  employers whose adverts are 40%+ identical: {len(heavy)} firms, "
      f"{int(heavy['adverts'].sum()):,} adverts ({heavy['adverts'].sum()/len(post):.1%} of corpus)")
print(f"  the rest of the 20+ group: {len(t)-len(heavy)} firms, "
      f"{int(t['adverts'].sum()-heavy['adverts'].sum()):,} adverts — barely repetitive at all")
print("")
print("  those heavy repeaters, by function:")
hv = post[post["company"].isin(set(heavy["company"]))]
print("    " + "  ".join(f"{k}: {v:,}" for k, v in hv["macro_function"].value_counts().items()))
print("    " + ", ".join(f"{k[:24]} {v}" for k, v in
                         hv["company_industry"].value_counts().head(5).items()))

print("")
print("=" * 92)
print("AND THE STATISTIC THAT ACTUALLY COLLAPSED")
print("=" * 92)
print("  Week 2 counted GROUPS above a shell threshold; Week 3 measures distance.")
print("  The same employer treatment does very different things to them:")
print("")
print(f"    count-based shell ratio   1.50  ->  1.06   (-29%)")
print(f"    continuous variance index {base_r:.2f}  ->  {h1(reqs, 'company'):.2f}   "
       f"({(h1(reqs,'company')/base_r-1):+.0%})")
print("")
print("  A count flips whenever a group crosses the threshold, so re-weighting")
print("  moves it hard. The distance measure has no threshold to cross.")
print(f"\ntotal {time.time()-t0:.0f}s")
