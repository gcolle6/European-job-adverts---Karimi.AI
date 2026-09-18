"""Build the final alias table: automatic merges + the reviewed decisions + step (b).

Three layers, in increasing order of how much judgement each needed.

  **Layer 1 — automatic.** `cluster.merge_aliases`: centroids close AND the labels
  share a specific name or are identical. 44 families, no judgement required.

  **Layer 2 — the twelve.** Pairs where at least one side is shell and BOTH peak
  in the same cell. Reviewed and decided 2026-09-18; two were rejected and the
  reasons are recorded beside them, because a rejected merge is a decision too.

  **Layer 3 — step (b).** Pairs where one side has no peak at all. The
  "they peak in different cells" argument does not apply to these — a group with
  no peak cannot contradict the other's — so the geometric-plus-name rule is
  given a third signal it did not have: **member vocabulary overlap**, validated
  separately at 0.862 separation (89.5% of known merges caught, 3.3% of random
  pairs). Credential-to-credential pairs are held back: the vocabulary signal is
  known to fail there, since every degree is written out of the same frame.

What remains after all three — pairs peaking in genuinely different cells — is
left for LLM adjudication later, and listed so it is not forgotten.
"""
import re
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

# Reviewed 2026-09-18. Rejections carry their reason — an unmerged pair is a
# decision, not an omission.
REJECTED = {
    ("Telecommunications degree", "Electronics degree"):
        "two different degrees, however adjacent",
    ("Finance degree", "Financial services experience"):
        "a qualification is not sector experience, and that distinction is what "
        "finding 3 exists to show",
}
CRED = re.compile(r"degree|diploma|bachelor|master|bac\+|graduate|apprentice", re.I)

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
lab = dict(zip(named["cluster"], named["label"]))
occ = dict(zip(named["cluster"], named["occurrences"]))

merge = cl.merge_aliases(named, z["cluster_ids"], z["centroids"])
alias = dict(merge["alias"])
short = pd.read_csv(W3 + r"\merge_shortlist_shell.csv")
print(f"layer 1 — automatic: {len(merge['families'])} families, "
      f"{merge['n_groups_before']} -> {merge['n_groups_after']} groups")


def root(c):
    seen = set()
    while c in alias and alias[c] != c and c not in seen:
        seen.add(c)
        c = alias[c]
    return c


def join(a, b):
    ra, rb = root(a), root(b)
    if ra == rb:
        return False
    keep, gone = (ra, rb) if occ.get(ra, 0) >= occ.get(rb, 0) else (rb, ra)
    for k in list(alias):
        if root(k) == gone:
            alias[k] = keep
    alias[gone] = keep
    return True


# ---------------------------------------------------------------- layer 2 ---
same = short[short["same_peak_cell"]]
merged2, refused = 0, []
for r in same.itertuples():
    key = (str(r.label_a), str(r.label_b))
    why = REJECTED.get(key) or REJECTED.get((key[1], key[0]))
    if why:
        refused.append((key, why))
        continue
    if join(int(r.cluster_a), int(r.cluster_b)):
        merged2 += 1
print(f"layer 2 — the twelve: {merged2} merged, {len(set(k for k,_ in refused))} refused")
for (a, b), why in refused:
    print(f"    refused  {a}  +  {b}\n             {why}")

# ---------------------------------------------------------------- layer 3 ---
vocab = cl.member_vocabulary(asg, reqs)
nopeak = short[(~short["same_peak_cell"]) &
               ((short["peak_a"] == "—") | (short["peak_b"] == "—"))]
print(f"\nlayer 3 — one side has no peak: {len(nopeak)} pairs to test")
merged3, held = 0, 0
applied = []
for r in nopeak.itertuples():
    a, b = int(r.cluster_a), int(r.cluster_b)
    if CRED.search(str(r.label_a)) and CRED.search(str(r.label_b)):
        held += 1
        continue
    va, vb = vocab.get(a, set()), vocab.get(b, set())
    ov = len(va & vb) / len(va | vb) if va and vb else 0.0
    if ov >= cl.MEMBER_MIN_OVERLAP and join(a, b):
        merged3 += 1
        applied.append((str(r.label_a), str(r.label_b), round(ov, 3), r.cosine))
print(f"    merged {merged3}, held back {held} credential pairs")
for la, lb, ov, cos in sorted(applied, key=lambda x: -x[2])[:12]:
    print(f"    ov {ov:.2f} cos {cos:.3f}  {la[:32]:<34} + {lb[:32]}")

# ---------------------------------------------------------------- result ----
alias = {c: root(c) for c in alias}
alias = {c: r for c, r in alias.items() if c != r}
n_after = len(named) - len(alias) + len(set(alias.values()))
print("")
print("=" * 92)
print(f"FINAL: {len(named)} groups -> {n_after}   ({len(alias)} folded into "
      f"{len(set(alias.values()))} survivors)")
print("=" * 92)

boiler = set(named.loc[named["boilerplate"] == True, "cluster"])
mixed = set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
asg_m = cl.apply_aliases(asg, alias)
for tag, a, dr in [("before", asg, boiler | mixed),
                   ("after ", asg_m, {alias.get(c, c) for c in (boiler | mixed)})]:
    cs = cl.core_shell(a, reqs, boilerplate=dr)
    sh = cs[cs["verdict"] == "shell"]
    per = sh.groupby("macro_function")["cluster"].size() / \
        cs.groupby("macro_function")["company_industry"].nunique()
    print(f"  {tag}  shell per cell — sales {per.get('SALES_BD', np.nan):>5.1f}  "
          f"software {per.get('SOFTWARE_DATA', np.nan):>5.1f}  "
          f"ratio {per.get('SALES_BD', np.nan)/per.get('SOFTWARE_DATA', np.nan):.3f}")
    if tag == "after ":
        cs.to_csv(W3 + r"\core_shell_final.csv", index=False, encoding="utf-8")
        lm = {}
        for c in named["cluster"]:
            lm.setdefault(alias.get(c, c), str(lab.get(alias.get(c, c), "?")))
        print("\n  the atlas, strongest elevated requirements:")
        for r in sh.nlargest(10, "lift").itertuples():
            print(f"    {r.lift:>5.1f}x  {lm.get(r.cluster, '?')[:34]:<36}"
                  f"{r.macro_function:<14} {str(r.company_industry)[:26]}")

left = short[(~short["same_peak_cell"]) &
             (short["peak_a"] != "—") & (short["peak_b"] != "—")]
left = left[[root(int(r.cluster_a)) != root(int(r.cluster_b)) for r in left.itertuples()]]
left.to_csv(W3 + r"\merge_pending_adjudication.csv", index=False, encoding="utf-8")
pd.DataFrame({"cluster": list(alias), "merged_into": list(alias.values())}).to_csv(
    W3 + r"\alias_table.csv", index=False, encoding="utf-8")
print(f"\n  left for adjudication later: {len(left)} pairs "
      f"-> merge_pending_adjudication.csv")
print(f"  written: alias_table.csv, core_shell_final.csv")
print(f"total {time.time()-t0:.0f}s")
