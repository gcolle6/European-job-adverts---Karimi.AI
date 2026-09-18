"""Move the confirmed intruders out of the groups they landed in.

Seven groups were named after reading the dense review sheet. Two of those
namings were wrong and are dropped here rather than carried forward:

  * `5+ years' experience in Go-to-Market strategies` inside **Sales
    experience** is correctly placed — go-to-market IS sales work. The scan
    caught it on the substring "Go" and the summary repeated the error.
  * `Highly proficient software engineer in at least one programming language`
    inside **Rust programming** is a generic phrase, not a polysemy case; it
    belongs to the same over-flagging family as the rest of the dense list.

What remains is the finding-13 family: a product name that is also an ordinary
word, or a substring of a compound. `Keyless-Go` matched on "Go", `Cypress`,
`Cucumber` and `Juniper` on plant names, `Puppet` and `Kibana` on their own.

**The target is not chosen by hand.** Each phrase is re-scored against every
centroid except the one it currently sits in, and it moves to the nearest — or
to the noise class when nothing reaches the assignment threshold, which is the
honest outcome for a phrase with no home. Corrections are written as a table
applied on top of the assignment, exactly like the alias table: auditable,
reversible, and never edited into the source data.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, embed as emb

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

# (cluster it sits in, a substring identifying the phrase) — read off the dense
# review sheet, with the two mis-namings above removed.
INTRUDERS = [
    (383, "Airflow"),
    (383, "Confluence"),
    (2, "Puppet"),
    (67, "Kibana"),
    (233, "Spring Boot"),
    (379, "Keyless"),
    (194, "Cypress"),
    (194, "Cucumber"),
    (194, "Juniper"),
]

named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
lab = dict(zip(named["cluster"], named["label"]))

z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
cids = np.array(z["cluster_ids"])
C = z["centroids"]
C = C / np.clip(np.linalg.norm(C, axis=1, keepdims=True), 1e-12, None)
phrases, vecs = emb.load_corpus(W1 + r"\embeddings.npz")
store = {p: i for i, p in enumerate(phrases)}

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)

rows = []
for cid, needle in INTRUDERS:
    sub = j[(j["cluster"] == cid) &
            j["phrase"].astype(str).str.contains(needle, case=False, na=False)]
    for pn in sub["phrase_norm"].unique():
        if pn not in store:
            continue
        v = vecs[store[pn]]
        v = v / max(np.linalg.norm(v), 1e-12)
        sims = v @ C.T
        order = np.argsort(-sims)
        # the best centroid that is not the one it currently sits in
        alt = next(k for k in order if int(cids[k]) != cid)
        # ⚠️ The nearest alternative centroid is NOT a safe target, and the first
        # run proved it: `Strong experience with Juniper switching` moved to
        # `Switching and transformers` (electrical switching) and
        # `Hands-on experience with Nokia/Juniper` to `Android app development`.
        # The same embedding that put these phrases in a gardening cluster is
        # choosing where they go next, so it trades one polysemy error for
        # another — the structural failure this project has now hit four times.
        #
        # These phrases land in a gardening cluster because the structure has NO
        # networking-equipment group for them. Assigning them anywhere is worse
        # than saying so: they go to the noise class, which is what the noise
        # class is for, and their absence becomes a visible coverage gap rather
        # than a hidden mislabel.
        target = -1
        _proposed = int(cids[alt]) if sims[alt] >= cl.MIN_ASSIGN_COSINE else -1
        rows.append({
            "phrase_norm": pn,
            "phrase": sub.loc[sub["phrase_norm"] == pn, "phrase"].iat[0],
            "from_cluster": cid, "from_label": lab.get(cid, "?"),
            "to_cluster": target,
            "to_label": "(noise)",
            "nearest_alternative": lab.get(_proposed, "(none)") if _proposed != -1 else "(none)",
            "similarity": round(float(sims[alt]), 3),
            "occurrences": int((j["phrase_norm"] == pn).sum()),
        })

fix = pd.DataFrame(rows).drop_duplicates("phrase_norm")
print("=" * 100)
print("THE MOVES, WITH THE TARGET CHOSEN BY THE DATA")
print("=" * 100)
for r in fix.sort_values("occurrences", ascending=False).head(14).itertuples():
    print(f"  [{r.occurrences:>3}] {str(r.phrase)[:50]:<52}")
    print(f"        out of {str(r.from_label)[:26]:<28} → noise "
          f"(nearest alternative was {str(r.nearest_alternative)[:26]}, {r.similarity})")

print("")
print(f"  phrases moved: {len(fix)}   requirements affected: {int(fix['occurrences'].sum())}")
print(f"  all sent to the noise class — no target was safe")
bad = fix[fix["nearest_alternative"] != "(none)"]
print(f"  the embedding would have proposed a target for {len(bad)} of them,")
print(f"  and those targets are what made this approach unusable")

# ------------------------------------------------------------------ effect
fmap = dict(zip(fix["phrase_norm"], fix["to_cluster"]))
asg_f = asg.copy()
asg_f["cluster"] = [fmap.get(p, c) for p, c in zip(asg_f["phrase_norm"], asg_f["cluster"])]

from karimi import variance as var
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])
print("")
print("=" * 100)
print("EFFECT")
print("=" * 100)
for nm, a in [("before", asg), ("after", asg_f)]:
    prof = var.cell_profiles(a, reqs, exclude=drop)
    s = var.index_for(prof, "SALES_BD")["js"]
    w = var.index_for(prof, "SOFTWARE_DATA")["js"]
    placed = (a["cluster"] != -1).mean()
    print(f"  {nm:<8} H1 {s/w:.3f}   placed {placed:.2%}")

fix.to_csv(W3 + r"\intruder_corrections.csv", index=False, encoding="utf-8")
asg_f.to_parquet(W3 + r"\phrase_clusters_corrected.parquet", index=False)
print(f"\nwritten: intruder_corrections.csv, phrase_clusters_corrected.parquet")
print(f"total {time.time()-t0:.0f}s")
