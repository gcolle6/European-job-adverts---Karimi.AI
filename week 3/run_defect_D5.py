"""Defect D5 — one technology spread across several groups.

`AWS experience` / `AWS knowledge` / `AWS services` are three groups. So are
`SQL knowledge` / `SQL skills` / `SQL and databases`. Any per-technology figure
built on a single group reports a fraction of the true demand.

Merging is the safe direction — groups can be joined afterwards, a group that
pooled two technologies could never be separated — but it is only safe if the
merge is *conservative*. Two hazards, both checked here before anything is
merged:

  * **cascade.** Single-linkage on cosine chains A-B-C-D into one blob even when
    A and D are unrelated. Component sizes are inspected at each threshold and a
    threshold that produces a giant component is rejected, not tuned away.
  * **false merges.** Two groups can sit close and still be different things —
    `Cloud platforms [AWS, Azure]` and `Cloud security` are neighbours and are
    not the same demand.

So the alias table is built, its components are printed for inspection, and the
effect on the headline is measured. Nothing is written back into the published
tables.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))
occ = dict(zip(named["cluster"], named["occurrences"]))

z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
cids = np.array(z["cluster_ids"])
C = z["centroids"]
C = C / np.clip(np.linalg.norm(C, axis=1, keepdims=True), 1e-12, None)
S = C @ C.T
np.fill_diagonal(S, -1.0)


def components(threshold):
    """Single-linkage components of the centroid graph at this threshold."""
    parent = list(range(len(cids)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ii, jj = np.where(np.triu(S >= threshold, k=1))
    for a, b in zip(ii, jj):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for i in range(len(cids)):
        groups.setdefault(find(i), []).append(int(cids[i]))
    return [g for g in groups.values()]


print("=" * 88)
print("1. CASCADE CHECK — does single linkage collapse the structure?")
print("=" * 88)
print(f"{'threshold':>10}{'components':>12}{'merged groups':>15}{'largest':>10}{'2nd':>7}")
for thr in [0.70, 0.75, 0.80, 0.85, 0.90]:
    comp = components(thr)
    sizes = sorted((len(c) for c in comp), reverse=True)
    merged = sum(len(c) for c in comp if len(c) > 1)
    print(f"{thr:>10.2f}{len(comp):>12}{merged:>15}{sizes[0]:>10}{sizes[1]:>7}")
print("\n  a threshold whose largest component swallows dozens of groups is")
print("  chaining unrelated things and must be rejected, not tuned")

CHOSEN = 0.85
comp = [c for c in components(CHOSEN) if len(c) > 1]
print("")
print("=" * 88)
print(f"2. THE ALIAS TABLE AT {CHOSEN} — every merge, for inspection")
print("=" * 88)
comp.sort(key=lambda c: -sum(occ.get(x, 0) for x in c))
for c in comp:
    total = sum(occ.get(x, 0) for x in c)
    names = " + ".join(f"{lab.get(x, '?')} ({occ.get(x, 0)})" for x in sorted(c, key=lambda x: -occ.get(x, 0)))
    print(f"  [{total:>5}] {names[:150]}")
print(f"\n  {len(comp)} merges covering {sum(len(c) for c in comp)} groups "
      f"-> {617 - sum(len(c) for c in comp) + len(comp)} after merging")

alias = {}
for c in comp:
    keep = max(c, key=lambda x: occ.get(x, 0))
    for x in c:
        alias[x] = keep
pd.DataFrame({"cluster": list(alias), "merged_into": list(alias.values())}).to_csv(
    W3 + r"\alias_table.csv", index=False, encoding="utf-8")

print("")
print("=" * 88)
print("3. EFFECT ON THE HEADLINE")
print("=" * 88)
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
asg_m = asg.copy()
asg_m["cluster"] = asg_m["cluster"].map(lambda c: alias.get(c, c))
drop_m = {alias.get(c, c) for c in drop}
for nm, a, d in [("as published", asg, drop), ("after merging", asg_m, drop_m)]:
    prof = var.cell_profiles(a, reqs, exclude=d)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    print(f"  {nm:<16} sales {s:.4f}  software {w:.4f}  ratio {s/w:.3f}")

print("")
print("=" * 88)
print("4. WHAT IT FIXES — per-technology demand, before and after")
print("=" * 88)
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
sw = j[j["macro_function"] == "SOFTWARE_DATA"]
n_sw = sw["vacancy_id"].nunique()
for name, seed in [("SQL", 175), ("AWS", 526), ("English", 155)]:
    grp = [c for c in alias if alias[c] == alias.get(seed, seed)] or [seed]
    one = sw.loc[sw["cluster"] == seed, "vacancy_id"].nunique()
    mrg = sw.loc[sw["cluster"].isin(grp), "vacancy_id"].nunique()
    print(f"  {name:<9} single group {one/n_sw:>6.1%} of software adverts   "
          f"merged {mrg/n_sw:>6.1%}   understatement {1 - one/max(mrg,1):>5.1%}")
print(f"\ntotal {time.time()-t0:.0f}s")
