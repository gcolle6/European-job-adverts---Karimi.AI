"""D5, second attempt: merge only groups that NAME THE SAME THING.

The purely geometric alias table fails, and the way it fails is familiar. At 0.85
it merges `Microsoft Office` with `Microsoft Azure`, `Languages` with
`Programming languages proficiency`, and Teamwork + Collaboration + Leadership +
Interpersonal + Communication into one 11,086-occurrence blob. **Cosine cannot
tell "same thing, different wording" from "different things, same topic"** — the
third time in this project that an embedding has been asked to judge sameness and
could not.

The fix is to stop asking it. A merge now needs BOTH:

  * centroids close (the geometric condition, kept); and
  * the two labels **share a specific name** — a token that identifies a thing
    rather than describing one.

A stoplist carries the descriptive vocabulary (`experience`, `knowledge`,
`skills`, `degree`, `management`) and the vendor prefixes that caused the worst
false merge (`microsoft`, `google`, `amazon`), so `Microsoft Office` and
`Microsoft Azure` no longer share anything mergeable while the SQL, Python and
AWS families still do.

This narrows the fix to exactly what D5 is about — one technology spread across
several groups — and deliberately does not attempt the soft-skill families, where
"the same thing" is not well defined enough to merge safely.
"""
import re
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

MIN_COS = 0.80

# Words that describe rather than name. A shared token from this list is not
# evidence that two groups are the same thing.
GENERIC = set("""
experience experiences knowledge skills skill proficiency expertise
understanding familiarity background degree diploma qualification certification
management managing developer development engineering engineer technical
technology technologies tools tool systems system platform platforms software
and or the of in with a an for to strong good excellent solid advanced basic
relevant professional practical hands-on hands on work working ability abilities
communication team teams leadership interpersonal collaboration mindset
attitude thinking orientation focus oriented driven learning
microsoft google amazon apache oracle ibm sap adobe
data business commercial general senior junior level years
""".split())

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


def names(cid):
    """Specific tokens in a group's label: not generic, not a bare short word."""
    text = str(lab.get(cid, "")).lower()
    toks = re.findall(r"[a-z0-9#+./]+", text)
    return {t for t in toks if t not in GENERIC and (len(t) > 2 or t in {"go", "r", "c#", "ai"})}


parent = list(range(len(cids)))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


pairs, rejected = [], []
ii, jj = np.where(np.triu(S >= MIN_COS, k=1))
for a, b in zip(ii, jj):
    ca, cb = int(cids[a]), int(cids[b])
    shared = names(ca) & names(cb)
    if shared:
        pairs.append((ca, cb, float(S[a, b]), sorted(shared)))
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    else:
        rejected.append((ca, cb, float(S[a, b])))

groups = {}
for i in range(len(cids)):
    groups.setdefault(find(i), []).append(int(cids[i]))
comp = [g for g in groups.values() if len(g) > 1]
comp.sort(key=lambda c: -sum(occ.get(x, 0) for x in c))

print("=" * 92)
print(f"MERGES ACCEPTED AT COSINE >= {MIN_COS} WITH A SHARED SPECIFIC NAME")
print("=" * 92)
for c in comp:
    total = sum(occ.get(x, 0) for x in c)
    nm = " + ".join(f"{lab.get(x, '?')} ({occ.get(x, 0)})"
                    for x in sorted(c, key=lambda x: -occ.get(x, 0)))
    print(f"  [{total:>5}] {nm[:140]}")
print(f"\n  {len(comp)} merges covering {sum(len(c) for c in comp)} groups "
      f"-> {617 - sum(len(c) for c in comp) + len(comp)} groups after merging")
sizes = sorted((len(c) for c in comp), reverse=True)
print(f"  largest merge: {sizes[0]} groups  (the geometric version reached 12)")

print("")
print("=" * 92)
print("PAIRS THE NAME RULE REJECTED — the false merges it prevents")
print("=" * 92)
for ca, cb, s in sorted(rejected, key=lambda r: -r[2])[:12]:
    print(f"  {s:.3f}  {str(lab.get(ca,'?'))[:40]:<42} =/= {str(lab.get(cb,'?'))[:40]}")
print(f"  ({len(rejected)} rejected, {len(pairs)} accepted)")

alias = {}
for c in comp:
    keep = max(c, key=lambda x: occ.get(x, 0))
    for x in c:
        alias[x] = keep
pd.DataFrame({"cluster": list(alias), "merged_into": list(alias.values())}).to_csv(
    W3 + r"\alias_table.csv", index=False, encoding="utf-8")

print("")
print("=" * 92)
print("EFFECT ON THE HEADLINE")
print("=" * 92)
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
asg_m = asg.copy()
asg_m["cluster"] = asg_m["cluster"].map(lambda c: alias.get(c, c))
for nm, a, d in [("as published", asg, drop),
                 ("after merging", asg_m, {alias.get(c, c) for c in drop})]:
    prof = var.cell_profiles(a, reqs, exclude=d)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    print(f"  {nm:<16} sales {s:.4f}  software {w:.4f}  ratio {s/w:.3f}")

print("")
print("=" * 92)
print("WHAT IT FIXES — per-technology demand, single group vs merged")
print("=" * 92)
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
sw = j[j["macro_function"] == "SOFTWARE_DATA"]
n_sw = sw["vacancy_id"].nunique()
for name, seed in [("SQL", 175), ("Python", 114), ("AWS", 526), ("English", 155),
                   ("Java", 246), ("JavaScript", 262)]:
    root = alias.get(seed, seed)
    fam = [c for c in alias if alias[c] == root] or [seed]
    one = sw.loc[sw["cluster"] == seed, "vacancy_id"].nunique() / n_sw
    mrg = sw.loc[sw["cluster"].isin(fam), "vacancy_id"].nunique() / n_sw
    print(f"  {name:<11} single group {one:>6.1%}   merged {mrg:>6.1%}   "
          f"understated by {1 - one/max(mrg, 1e-9):>5.1%}   ({len(fam)} groups)")
print(f"\ntotal {time.time()-t0:.0f}s")
