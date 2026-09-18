"""Weight by CONTENT duplication instead of by employer.

Both weightings used so far are blunt. Counting every advert lets one template
vote fifty times; counting each employer once throws away the 975 genuinely
different adverts Inetum wrote to avoid the 86 near-identical ones Worten wrote.

A third scheme does neither: collapse an employer's adverts only where they are
actually the same advert. Distinct postings keep their weight, duplicates
collapse to one. It is the weighting the volume-versus-repetition result implies,
and it is what the advert-unit and employer-unit figures bracket.

Near-duplicates are found greedily inside each employer — an advert joins an
existing group when it overlaps its leader at `thr`, otherwise it starts one.
Greedy leader clustering is order-dependent, so adverts are sorted by id first
and the run is deterministic; at these thresholds the groups are tight enough
that ordering barely matters, which the exact-duplicate row (thr = 1.0) shows.
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
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

post = base.drop_duplicates("vacancy_id")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
jj = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]
profile = jj.groupby("vacancy_id")["cluster"].apply(frozenset)
company = dict(zip(post["vacancy_id"], post["company"]))


def keepers(thr):
    """One representative advert per distinct posting, within each employer."""
    by_emp = {}
    for vid, s in profile.items():
        by_emp.setdefault(company.get(vid), []).append((vid, s))
    keep = []
    for emp, items in by_emp.items():
        items.sort(key=lambda x: str(x[0]))
        leaders = []
        for vid, s in items:
            if not s:
                keep.append(vid)
                continue
            hit = False
            for lvid, ls in leaders:
                u = len(s | ls)
                if u and len(s & ls) / u >= thr:
                    hit = True
                    break
            if not hit:
                leaders.append((vid, s))
                keep.append(vid)
    return set(keep)


def h1(frame, unit="vacancy_id"):
    prof = var.cell_profiles(asg, frame, exclude=drop, unit=unit)
    a = var.index_for(prof, "SALES_BD")["js"]
    b = var.index_for(prof, "SOFTWARE_DATA")["js"]
    return a, b, a / b

n_all = reqs["vacancy_id"].nunique()
print("=" * 96)
print("WEIGHTING BY CONTENT DUPLICATION")
print("=" * 96)
print(f"{'scheme':<44}{'adverts kept':>14}{'lost':>8}{'ratio':>9}")
a, b, r = h1(reqs)
print(f"{'every advert counts':<44}{n_all:>14,}{'—':>8}{r:>9.3f}")

rows = []
for thr in (1.00, 0.95, 0.90, 0.80, 0.60):
    keep = keepers(thr)
    f = reqs[reqs["vacancy_id"].isin(keep)]
    a, b, r = h1(f)
    lost = n_all - len(keep)
    label = ("exact duplicates only" if thr == 1.0
             else f"adverts {thr:.0%}+ identical collapsed")
    print(f"  {label:<42}{len(keep):>14,}{lost:>8,}{r:>9.3f}")
    rows.append({"threshold": thr, "kept": len(keep), "lost": lost,
                 "sales": round(a, 4), "software": round(b, 4), "ratio": round(r, 3)})

a, b, r = h1(reqs, "company")
print(f"{'each employer counts once':<44}{post['company'].nunique():>14,}"
      f"{n_all - post['company'].nunique():>8,}{r:>9.3f}")

print("")
print("=" * 96)
print("WHO ACTUALLY LOSES ADVERTS AT 0.90")
print("=" * 96)
keep90 = keepers(0.90)
lostc = (post[~post["vacancy_id"].isin(keep90)]
         .groupby("company").size().sort_values(ascending=False))
tot = post.groupby("company").size()
print(f"  {int(lostc.sum()):,} adverts collapse, from {len(lostc)} employers "
      f"({int(lostc.sum())/n_all:.1%} of the corpus)")
print("")
print(f"  {'employer':<26}{'adverts':>9}{'collapsed':>11}{'kept':>7}")
for name in lostc.head(10).index:
    print(f"  {str(name)[:24]:<26}{tot[name]:>9}{lostc[name]:>11}{tot[name]-lostc[name]:>7}")
big = ["Inetum", "Saab", "Netcompany"]
print("\n  and the large posters that lose almost nothing:")
for name in big:
    if name in tot.index:
        print(f"  {str(name)[:24]:<26}{tot[name]:>9}{int(lostc.get(name,0)):>11}"
              f"{tot[name]-int(lostc.get(name,0)):>7}")

print("")
print("=" * 96)
print("WHAT IT COSTS, AND WHAT IT BUYS")
print("=" * 96)
print(f"  employer-as-unit discards {n_all - post['company'].nunique():,} adverts "
      f"({(n_all - post['company'].nunique())/n_all:.0%} of the corpus)")
print(f"  content dedup at 0.90 discards {n_all - len(keep90):,} "
      f"({(n_all - len(keep90))/n_all:.0%})")
print("  — the same distortion removed, roughly a tenth of the data spent instead of nine tenths")

pd.DataFrame(rows).to_csv(W3 + r"\content_dedup.csv", index=False, encoding="utf-8")
print(f"\ntotal {time.time()-t0:.0f}s")
