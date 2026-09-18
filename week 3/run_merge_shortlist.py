"""The minimum set of merge decisions that unblocks finding 3.

The assumption behind the last step was wrong. Groups left fragmented were
expected to be mostly *core* — flat across contexts, therefore irrelevant to a
finding about what is elevated where. They are the opposite: **47.9% of them are
shell against 32.0% of everything else**, and 78 of the 197 shell groups are
still in an unresolved near-duplicate pair.

But resolving all 179 rejected pairs is not necessary. Finding 3 reads the lift
table, so only a pair where **at least one side is shell** can change what it
shows. That is a much smaller list, and it is the whole job.

Each pair is emitted with what a person needs to decide it: both labels, both
sizes, sample members from each side, how close they sit, and — the deciding
question — whether they are elevated in the SAME cell or different ones. Two
groups that peak in the same cell are almost certainly one demand split in two;
two that peak in different cells are probably not.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 260)
t0 = time.time()

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
lab = dict(zip(named["cluster"], named["label"]))
occ = dict(zip(named["cluster"], named["occurrences"]))

merge = cl.merge_aliases(named, z["cluster_ids"], z["centroids"])
alias, rej = merge["alias"], merge["rejected"]
boiler = set(named.loc[named["boilerplate"] == True, "cluster"])
mixed = set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

cs = cl.core_shell(cl.apply_aliases(asg, alias), reqs,
                   boilerplate={alias.get(c, c) for c in (boiler | mixed)})
shell = cs[cs["verdict"] == "shell"]
peak = (shell.sort_values("lift", ascending=False)
        .drop_duplicates("cluster")
        .set_index("cluster")[["macro_function", "company_industry", "lift"]])
shell_ids = set(peak.index)

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)


def members(cid, n=5):
    sub = j[j["cluster"] == cid]
    return " | ".join(str(p)[:34] for p in sub["phrase"].value_counts().head(n).index)


rows = []
for r in rej.itertuples():
    a, b = alias.get(r.a, r.a), alias.get(r.b, r.b)
    if a == b or not ({a, b} & shell_ids):
        continue
    pa = peak.loc[a] if a in peak.index else None
    pb = peak.loc[b] if b in peak.index else None
    same_cell = (pa is not None and pb is not None
                 and pa["macro_function"] == pb["macro_function"]
                 and pa["company_industry"] == pb["company_industry"])
    rows.append({
        "cosine": r.cosine,
        "same_peak_cell": same_cell,
        "label_a": str(lab.get(a, "?")), "n_a": occ.get(a, 0),
        "peak_a": f"{pa['company_industry'][:20]} {pa['lift']:.1f}x" if pa is not None else "—",
        "label_b": str(lab.get(b, "?")), "n_b": occ.get(b, 0),
        "peak_b": f"{pb['company_industry'][:20]} {pb['lift']:.1f}x" if pb is not None else "—",
        "cluster_a": a, "cluster_b": b,
    })
d = pd.DataFrame(rows).drop_duplicates(subset=["cluster_a", "cluster_b"])
d = d.sort_values(["same_peak_cell", "cosine"], ascending=[False, False])

print("=" * 100)
print("THE DECISIONS THAT ACTUALLY MATTER FOR FINDING 3")
print("=" * 100)
print(f"  rejected pairs in total                      {len(rej)}")
print(f"  pairs where at least one side is SHELL       {len(d)}")
print(f"  of those, both peak in the SAME cell         {int(d['same_peak_cell'].sum())}"
      f"   <- almost certainly one demand split in two")
print("")
print("SAME PEAK CELL — merge unless the members say otherwise:")
for r in d[d["same_peak_cell"]].itertuples():
    print(f"\n  cos {r.cosine:.3f}  [{r.n_a:>5}] {r.label_a[:32]:<34} peaks {r.peak_a}")
    print(f"                    {members(r.cluster_a)}")
    print(f"             [{r.n_b:>5}] {r.label_b[:32]:<34} peaks {r.peak_b}")
    print(f"                    {members(r.cluster_b)}")

print("")
print("=" * 100)
print("DIFFERENT PEAK CELLS — likelier to be genuinely different demands")
print("=" * 100)
diff = d[~d["same_peak_cell"]]
print(diff[["cosine", "label_a", "n_a", "peak_a", "label_b", "n_b", "peak_b"]]
      .head(18).to_string(index=False))
print(f"\n  ({len(diff)} pairs in this group)")

d.to_csv(W3 + r"\merge_shortlist_shell.csv", index=False, encoding="utf-8")
print(f"\nwritten: merge_shortlist_shell.csv — {len(d)} decisions, not 179")
print(f"total {time.time()-t0:.0f}s")
