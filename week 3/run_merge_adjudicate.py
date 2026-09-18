"""Pass (c): send the 85 undecided pairs to adjudication, then apply and measure.

These are the pairs the three local signals could not judge — credential
families, language families, and the chains that formed through hub groups. Each
is shown with example phrases from both sides, because the group names are
themselves model output and are what went wrong in `Messaging systems`.

The run is cached by pair, so re-running costs nothing, and the decisions are
written out in full so every merge can be read back and argued with.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, llm_split as L, merge_adjudicate as adj, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

pairs = pd.read_csv(W3 + r"\merge_for_adjudication.csv")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
lab = dict(zip(named["cluster"], named["label"]))
occ = dict(zip(named["cluster"], named["occurrences"]))
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

# example phrases carry the signal; the labels are model output and can be wrong
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
members = {int(c): [str(p) for p in s["phrase"].value_counts().head(6).index]
           for c, s in j[j["cluster"] != -1].groupby("cluster")}

print(f"pairs to adjudicate: {len(pairs)}")
client = L.load_openai_client()
dec = adj.adjudicate(pairs, members, client, W3 + r"\merge_adjudication.jsonl")
print(f"  decided in {time.time()-t0:.0f}s   "
      f"tokens in {dec.attrs['input_tokens']:,} out {dec.attrs['output_tokens']:,}   "
      f"from cache {dec.attrs['from_cache']}   chunk failures {dec.attrs['chunk_failures']}")

same = dec[dec["same"] == True]
diff = dec[dec["same"] == False]
print(f"\n  same demand: {len(same)}   different: {len(diff)}   "
      f"undecided: {int(dec['same'].isna().sum())}")

print("")
print("=" * 96)
print("MERGED BY ADJUDICATION")
print("=" * 96)
for r in same.itertuples():
    print(f"  {str(r.label_a)[:36]:<38} + {str(r.label_b)[:36]}")

print("")
print("=" * 96)
print("REFUSED — the distinctions it kept")
print("=" * 96)
for r in diff.nlargest(18, "cosine").itertuples():
    print(f"  cos {r.cosine:.3f}  {str(r.label_a)[:34]:<36} =/= {str(r.label_b)[:34]}")

# ------------------------------------------------------------------ combine
prev = pd.read_csv(W3 + r"\alias_table_shell.csv")
ids = sorted(set(named["cluster"]))
pos = {c: i for i, c in enumerate(ids)}
parent = list(range(len(ids)))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    ra, rb = find(pos[int(a)]), find(pos[int(b)])
    if ra != rb:
        parent[ra] = rb


for r in prev.itertuples():
    union(r.cluster, r.merged_into)
for r in same.itertuples():
    union(r.cluster_a, r.cluster_b)

comp = {}
for c in ids:
    comp.setdefault(find(pos[c]), []).append(c)
families = sorted((v for v in comp.values() if len(v) > 1),
                  key=lambda f: -sum(occ.get(c, 0) for c in f))
alias = {}
for f in families:
    keep = max(f, key=lambda c: occ.get(c, 0))
    for c in f:
        alias[c] = keep

print("")
print("=" * 96)
print("THE FULL MERGE, ALL THREE PASSES")
print("=" * 96)
print(f"  {len(families)} families covering {sum(len(f) for f in families)} groups   "
      f"617 → {617 - sum(len(f) for f in families) + len(families)}   "
      f"largest {max(len(f) for f in families)}")
print("")
for f in families[:16]:
    total = sum(occ.get(c, 0) for c in f)
    names = " + ".join(f"{lab.get(c,'?')} ({occ.get(c,0)})"
                       for c in sorted(f, key=lambda c: -occ.get(c, 0)))
    print(f"  [{total:>5}] {names[:126]}")

# ------------------------------------------------------------------ effect
asg_m = asg.copy()
asg_m["cluster"] = asg_m["cluster"].map(lambda c: alias.get(c, c))
drop_m = {alias.get(c, c) for c in drop}
print("")
print("=" * 96)
print("EFFECT ON THE HEADLINE AND THE ATLAS")
print("=" * 96)
for nm, a, d in [("as published", asg, drop), ("fully merged", asg_m, drop_m)]:
    prof = var.cell_profiles(a, reqs, exclude=d)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    cs = cl.core_shell(a, reqs, boilerplate=d)
    sh = cs[cs["verdict"] == "shell"]
    per = sh.groupby("macro_function")["cluster"].size() / \
        cs.groupby("macro_function")["company_industry"].nunique()
    print(f"  {nm:<14} H1 {s/w:.3f}   shell entries {len(sh):>4}   "
          + "  ".join(f"{k} {v:.1f}" for k, v in per.items()))

pd.DataFrame({"cluster": list(alias), "merged_into": list(alias.values())}).to_csv(
    W3 + r"\alias_table_final.csv", index=False, encoding="utf-8")
dec.to_csv(W3 + r"\merge_decisions.csv", index=False, encoding="utf-8")
print(f"\nwritten: alias_table_final.csv ({len(alias)} groups), merge_decisions.csv")
print(f"total {time.time()-t0:.0f}s")
