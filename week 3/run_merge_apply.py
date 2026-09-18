"""Apply the merge decisions: the 12 judged by hand, then filter (b), guarded.

⚠️ **The first version of pass 2 was wrong and the failure is instructive.** Run
without guards, the member-vocabulary signal merged `German proficiency` with
`Swedish fluency`, `Computer Science degree` with `Engineering degree`, teamwork
with leadership, and the MIXED junk drawer with trade occupations. Every one of
those falls in a family this project had **already measured** as the signal's
blind spot — and the union-find here bypassed the `MERGE_MAX_COMPONENT` guard in
`cluster.merge_aliases` that exists to catch precisely that.

The blind spot has one shape: **families whose members are written out of a
shared frame.** Every degree says "degree"; every language requirement says
"fluency"; every frame group says "experience with". Inside such a family the
member vocabulary overlaps for reasons that have nothing to do with the two
groups being the same demand, so the signal has no discrimination there.

So pass 2 now runs only outside those families, and the excluded pairs go to the
adjudication file rather than being merged on evidence that does not apply to
them.

**Pass 1 — the twelve same-peak pairs, decided by a person.** Ten merged, two
refused: `Telecommunications degree` + `Electronics degree` (two different
degrees) and `Finance degree` + `Financial services experience` (a qualification
is not sector experience).
"""
import re
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)

NO_PEAK = {"—", "-", "nan", "", "None"}
MEMBER_MIN = 0.10
MAX_FAMILY = 5              # a family larger than this is chaining, not merging

REFUSED = [
    ("Telecommunications degree", "Electronics degree"),
    ("Finance degree", "Financial services experience"),
]

# The three frames inside which member vocabulary carries no signal, because
# every member of the family shares the frame's own words.
CREDENTIAL = re.compile(r"degree|diploma|bachelor|master|apprentice|graduat|"
                        r"certificat|education|bac\+|qualification", re.I)
LANGUAGE = re.compile(r"fluency|proficiency in|english|german|french|spanish|"
                      r"italian|dutch|swedish|portuguese|polish|language", re.I)
FRAME = re.compile(r"^(relevant|general|technical|years of|work|proven|"
                   r"professional)?\s*(experience|knowledge|skills|ability|"
                   r"understanding|expertise)$", re.I)

short = pd.read_csv(W3 + r"\merge_shortlist_shell.csv")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
lab = dict(zip(named["cluster"], named["label"]))
occ = dict(zip(named["cluster"], named["occurrences"]))
mixed = {int(c) for c, l in lab.items() if str(l).strip().upper() == "MIXED"}

vocab = cl.member_vocabulary(asg, reqs)


def overlap(a, b):
    va, vb = vocab.get(a, set()), vocab.get(b, set())
    return len(va & vb) / len(va | vb) if va and vb else 0.0


def blind_spot(la, lb):
    """Is this pair inside a shared-frame family, where the signal cannot see?"""
    for rx in (CREDENTIAL, LANGUAGE):
        if rx.search(str(la)) and rx.search(str(lb)):
            return True
    return bool(FRAME.match(str(la).strip()) or FRAME.match(str(lb).strip()))


def refused(r):
    return any({str(r["label_a"]).strip(), str(r["label_b"]).strip()} == set(x)
               for x in REFUSED)


def no_peak(r):
    return (str(r["peak_a"]).strip() in NO_PEAK) or (str(r["peak_b"]).strip() in NO_PEAK)


# ------------------------------------------------------------------ pass 1
p1 = short[short["same_peak_cell"]].copy()
p1["merge"] = ~p1.apply(refused, axis=1)
print("=" * 94)
print("PASS 1 — TWELVE SAME-PEAK PAIRS, DECIDED BY HAND")
print("=" * 94)
for r in p1.itertuples():
    print(f"  {'merge ' if r.merge else '✗ keep'}  {str(r.label_a)[:34]:<36} + {str(r.label_b)[:34]}")
accept1 = p1[p1["merge"]]
print(f"\n  merged {len(accept1)} of {len(p1)}")

# ------------------------------------------------------------------ pass 2
p2 = short[(~short["same_peak_cell"]) & short.apply(no_peak, axis=1)].copy()
p2["overlap"] = [overlap(int(a), int(b)) for a, b in zip(p2["cluster_a"], p2["cluster_b"])]
p2["blind"] = [blind_spot(a, b) for a, b in zip(p2["label_a"], p2["label_b"])]
p2["has_mixed"] = [int(a) in mixed or int(b) in mixed
                   for a, b in zip(p2["cluster_a"], p2["cluster_b"])]
p2["merge"] = (p2["overlap"] >= MEMBER_MIN) & ~p2["blind"] & ~p2["has_mixed"]
accept2 = p2[p2["merge"]]

print("")
print("=" * 94)
print(f"PASS 2 — FILTER (b), GUARDED: {len(p2)} pairs where one side has no shell peak")
print("=" * 94)
print(f"  member vocabulary >= {MEMBER_MIN}   : {int((p2['overlap']>=MEMBER_MIN).sum())}")
print(f"  minus shared-frame families      : −{int(((p2['overlap']>=MEMBER_MIN) & p2['blind']).sum())}")
print(f"  minus anything touching MIXED    : −{int(((p2['overlap']>=MEMBER_MIN) & ~p2['blind'] & p2['has_mixed']).sum())}")
print(f"  MERGED                           : {len(accept2)}")
print("\n  what survives the guards:")
for r in accept2.sort_values("overlap", ascending=False).itertuples():
    print(f"    {r.overlap:.3f} cos {r.cosine:.3f}  {str(r.label_a)[:32]:<34} + {str(r.label_b)[:32]}")
print("\n  blocked as blind-spot families (sent to adjudication):")
for r in p2[(p2["overlap"] >= MEMBER_MIN) & p2["blind"]].nlargest(8, "overlap").itertuples():
    print(f"    {r.overlap:.3f}  {str(r.label_a)[:32]:<34} + {str(r.label_b)[:32]}")

# ------------------------------------------------------------------ closing
# The two passes close under different rules, because their evidence differs.
#
# Pass 1 is a person's call on a shortlist they read: its families form with no
# size limit. The `Systems*` family is four groups and that was the judgement.
#
# Pass 2 is a weak signal, and transitive closure is exactly where it fails —
# `Software development experience` sits in five pairs and absorbs its whole
# neighbourhood. So pass 2 keeps only components of TWO: direct evidence for
# that one pair, never an inference through a third group.
ids = sorted(set(named["cluster"]))
pos = {c: i for i, c in enumerate(ids)}


def close(pairs, cap=None):
    parent = list(range(len(ids)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(pos[int(a)]), find(pos[int(b)])
        if ra != rb:
            parent[ra] = rb
    comp = {}
    for c in ids:
        comp.setdefault(find(pos[c]), []).append(c)
    fams = [v for v in comp.values() if len(v) > 1]
    if cap is None:
        return fams, []
    return [f for f in fams if len(f) <= cap], [f for f in fams if len(f) > cap]


fam1, _ = close(list(zip(accept1["cluster_a"], accept1["cluster_b"])))
fam2, chained = close(list(zip(accept2["cluster_a"], accept2["cluster_b"])), cap=2)

# a pass-2 pair touching a pass-1 family joins it rather than forming its own
in1 = {c for f in fam1 for c in f}
fam2 = [f for f in fam2 if not (set(f) & in1)]
families = sorted(fam1 + fam2, key=lambda f: -sum(occ.get(c, 0) for c in f))
biggest = max((len(f) for f in families), default=0)

print(f"\n  pass 1 families (human, no size limit): {len(fam1)}")
print(f"  pass 2 families (direct pairs only)   : {len(fam2)}")
print(f"  pass 2 chains refused                 : {len(chained)} families, "
      f"{sum(len(f) for f in chained)} groups")
for f in sorted(chained, key=lambda x: -len(x))[:5]:
    print('    ' + ' + '.join(str(lab.get(c, c))[:22] for c in f))

alias = {}
for f in families:
    keep = max(f, key=lambda c: occ.get(c, 0))
    for c in f:
        alias[c] = keep

print("")
print("=" * 94)
print("THE COMBINED FAMILIES")
print("=" * 94)
print(f"  {len(families)} families covering {sum(len(f) for f in families)} groups   "
      f"617 → {617 - sum(len(f) for f in families) + len(families)}   "
      f"largest {biggest}")
print("")
for f in families:
    total = sum(occ.get(c, 0) for c in f)
    names = " + ".join(f"{lab.get(c,'?')} ({occ.get(c,0)})"
                       for c in sorted(f, key=lambda c: -occ.get(c, 0)))
    print(f"  [{total:>5}] {names[:128]}")

pd.DataFrame({"cluster": list(alias), "merged_into": list(alias.values())}).to_csv(
    W3 + r"\alias_table_shell.csv", index=False, encoding="utf-8")
left = pd.concat([p2[~p2["merge"]],
                  short[(~short["same_peak_cell"]) & ~short.apply(no_peak, axis=1)]],
                 ignore_index=True)
left.to_csv(W3 + r"\merge_for_adjudication.csv", index=False, encoding="utf-8")
print("")
print(f"written: alias_table_shell.csv  ({len(alias)} groups mapped)")
print(f"         merge_for_adjudication.csv  ({len(left)} pairs left for pass (c))")
