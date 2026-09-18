"""Scan every group for members that do not belong — validated before it is trusted.

The scan runs in two stages, and the first one is a gate rather than a warm-up.

**Stage 1, the control.** Three intruders are already known from the human review
of 40 random groups: a software-release phrase in a logistics group, a DevOps
phrase in a multicultural-environment group, and a publications phrase in a
writing-skills group. Those three groups are scanned first. **If the scan does
not find them, it does not work and stage 2 is not worth paying for** — the same
discipline that rejected the geometric detector and the label cross-check.

**Stage 2** runs the remaining groups only if the control passes.

Output is a shortlist for a person, never applied automatically.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import intruders as intr, llm_split as L

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 60)
t0 = time.time()

# the three the human review found, and the phrase each scan must catch
CONTROL = {
    166: "shipping code",
    188: "DevOps culture",
    82: "publications",
}

named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
members = {int(c): [str(p) for p in s["phrase"].value_counts().head(12).index]
           for c, s in j[j["cluster"] != -1].groupby("cluster")}

client = L.load_openai_client()
cache = W3 + r"\intruder_cache.jsonl"

# ------------------------------------------------------------------ stage 1
print("=" * 94)
print("STAGE 1 — THE CONTROL: does it find the three we already know about?")
print("=" * 94)
ctl = named[named["cluster"].isin(CONTROL)][["cluster", "label"]]
r1 = intr.scan(ctl, members, client, cache)
hits = 0
for row in r1.itertuples():
    cid = int(row.cluster)
    found = row.intruders or []
    needle = CONTROL[cid].lower()
    hit = any(needle in str(f).lower() for f in found)
    hits += hit
    print(f"\n  cluster {cid} — {row.label}")
    print(f"    must find : a phrase containing '{CONTROL[cid]}'")
    print(f"    flagged   : {found if found else '(nothing)'}")
    print(f"    {'FOUND' if hit else 'MISSED'}")

print(f"\n  control: {hits} of 3 found")
if hits < 2:
    raise SystemExit(
        "\nSTOP: the control failed. The scan misses the intruders we already "
        "know about, so its verdict on the other 614 groups is worth nothing. "
        "Do not pay for stage 2.")
print("  control passed — proceeding to the full scan")

# ------------------------------------------------------------------ stage 2
print("")
print("=" * 94)
print("STAGE 2 — ALL REMAINING GROUPS")
print("=" * 94)
rest = named[~named["cluster"].isin(CONTROL)][["cluster", "label"]]
r2 = intr.scan(rest, members, client, cache)
print(f"  scanned {len(rest)} groups in {time.time()-t0:.0f}s   "
      f"tokens in {r2.attrs['input_tokens']:,} out {r2.attrs['output_tokens']:,}   "
      f"cached {r2.attrs['from_cache']}   failures {r2.attrs['chunk_failures']}")

allr = pd.concat([r1, r2], ignore_index=True)
allr["n_flagged"] = allr["intruders"].apply(lambda x: len(x) if isinstance(x, list) else 0)
flagged = allr[allr["n_flagged"] > 0].merge(
    named[["cluster", "occurrences", "top_type"]], on="cluster", how="left")

print("")
print(f"  groups with at least one flagged member: {len(flagged)} of {len(allr)} "
      f"({len(flagged)/len(allr):.1%})")
print(f"  total flagged phrases: {int(allr['n_flagged'].sum())}")
print("")
print("=" * 94)
print("THE SHORTLIST — largest groups first, for a person to confirm")
print("=" * 94)
for r in flagged.nlargest(25, "occurrences").itertuples():
    print(f"\n  [{r.occurrences:>5}] {str(r.label)[:44]}")
    for p in r.intruders:
        print(f"           ✗ {str(p)[:76]}")

allr.to_csv(W3 + r"\intruder_scan.csv", index=False, encoding="utf-8")
flagged.to_csv(W3 + r"\intruder_shortlist.csv", index=False, encoding="utf-8")
print(f"\nwritten: intruder_scan.csv (all {len(allr)}), "
      f"intruder_shortlist.csv ({len(flagged)} to review)")
print(f"total {time.time()-t0:.0f}s")
