"""What the merge actually changes in the atlas — the reason for doing it.

Merging groups is not an end in itself. It matters if and only if it changes what
a reader of the dashboard sees: the elevated requirements per cell, their lift,
and the headline the whole grid sits under. So this compares the published
structure against the merged one on exactly those three things.

A merge can move a lift in either direction, which is worth stating before the
numbers: pooling two groups raises the share asked in every cell, but it raises
the family baseline too, and the lift is the ratio between them. A group that was
distinctive only because it was small can lose its lift entirely.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
alias = pd.read_csv(W3 + r"\alias_table_shell.csv")
amap = dict(zip(alias["cluster"], alias["merged_into"]))
lab = dict(zip(named["cluster"], named["label"]))
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

asg_m = asg.copy()
asg_m["cluster"] = asg_m["cluster"].map(lambda c: amap.get(c, c))
drop_m = {amap.get(c, c) for c in drop}

print("=" * 96)
print("1. THE HEADLINE")
print("=" * 96)
for nm, a, d in [("as published", asg, drop), ("after merging", asg_m, drop_m)]:
    prof = var.cell_profiles(a, reqs, exclude=d)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    print(f"  {nm:<16} sales {s:.4f}  software {w:.4f}  ratio {s/w:.3f}")

print("")
print("=" * 96)
print("2. THE ATLAS — how many elevated requirements each cell shows")
print("=" * 96)
res = {}
for nm, a, d in [("published", asg, drop), ("merged", asg_m, drop_m)]:
    cs = cl.core_shell(a, reqs, boilerplate=d)
    sh = cs[cs["verdict"] == "shell"]
    res[nm] = (cs, sh)
    per = sh.groupby("macro_function")["cluster"].size() / \
        cs.groupby("macro_function")["company_industry"].nunique()
    print(f"  {nm:<10} shell entries per cell — "
          + "   ".join(f"{k} {v:.1f}" for k, v in per.items())
          + f"   (total {len(sh)})")

print("")
print("=" * 96)
print("3. THE HEADLINE SHELL FINDINGS — do they survive?")
print("=" * 96)
csp, shp = res["published"]
csm, shm = res["merged"]
top = shp.nlargest(8, "lift")
print(f"{'requirement':<34}{'cell':<30}{'published':>11}{'merged':>9}")
for r in top.itertuples():
    root = amap.get(int(r.cluster), int(r.cluster))
    m = csm[(csm["cluster"] == root) &
            (csm["macro_function"] == r.macro_function) &
            (csm["company_industry"] == r.company_industry)]
    after = f"{m['lift'].iat[0]:.1f}x" if len(m) else "—"
    merged_note = " *" if root != int(r.cluster) else ""
    print(f"  {str(lab.get(int(r.cluster),'?'))[:30]:<32}"
          f"{(r.macro_function[:3] + ' / ' + r.company_industry)[:28]:<30}"
          f"{r.lift:>10.1f}x{after:>9}{merged_note}")
print("\n  * = this group was merged into a family")

print("")
print("=" * 96)
print("4. WHERE THE MERGE ACTUALLY SHOWS UP")
print("=" * 96)
gained = []
for root in set(amap.values()):
    fam = [c for c, r in amap.items() if r == root]
    bef = shp[shp["cluster"].isin(fam)]
    aft = shm[shm["cluster"] == root]
    gained.append({
        "family": " + ".join(str(lab.get(c, c))[:22] for c in fam),
        "groups": len(fam),
        "shell_entries_before": len(bef),
        "shell_entries_after": len(aft),
        "max_lift_before": round(float(bef["lift"].max()), 2) if len(bef) else None,
        "max_lift_after": round(float(aft["lift"].max()), 2) if len(aft) else None,
    })
g = pd.DataFrame(gained).sort_values("shell_entries_after", ascending=False)
print(g.to_string(index=False))

csm.to_csv(W3 + r"\core_shell_merged_final.csv", index=False, encoding="utf-8")
print(f"\nwritten: core_shell_merged_final.csv")
print(f"total {time.time()-t0:.0f}s")
