"""Draw the four review sets for the human checks, and record how each was drawn.

How a sample is drawn decides what its result can mean, so each is drawn the way
its own question requires and the method is written into the output beside it:

  D8 — ESCO decisions. **Random**, and that is the whole point. The 25 already
       checked were chosen deliberately from the suspicious cases, which is why
       they cannot give an error rate. Seeded so the draw is reproducible.

  D4 — group coherence. **By size**, not by suspicion — Gate 2 already
       over-sampled the suspect groups. Weighting by size asks a different
       question: how much of the corpus sits in groups that hold together.

  A5 — availability. **All** of it that exists in the classification pool, since
       it is 0.9% of mass and has zero labels; there is nothing to sample from.

  A4 — long segments. **Raw text only.** The reviewer writes out the
       requirements they see without being shown ours, because a person shown a
       split will grade it rather than reproduce it, and grading is not the
       measurement.
"""
import json
import re
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
SEED = 20260914
rng = np.random.default_rng(SEED)

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
dec = pd.read_csv(OUT + r"\esco_decisions.csv")
dec["anchored"] = dec["anchored"].astype(str).str.strip().str.lower().eq("true")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)


def members(cid, n=8):
    sub = j[j["cluster"] == cid]
    return [str(p) for p in sub["phrase"].value_counts().head(n).index]


# ---------------------------------------------------------------- D8 -------
extra = [c for c in ("label", "occurrences") if c not in dec.columns]
pool = dec.merge(named[["cluster"] + extra], on="cluster", how="left")
pool = pool[pool["label"].astype(str).str.upper() != "MIXED"]
pick = rng.choice(pool.index.to_numpy(), size=min(40, len(pool)), replace=False)
d8 = []
for i, idx in enumerate(sorted(pick), 1):
    r = pool.loc[idx]
    d8.append({
        "n": i, "cluster": int(r["cluster"]),
        "label": str(r["label"]),
        "occurrences": int(r.get("occurrences", 0) or 0),
        "members": members(int(r["cluster"])),
        "anchored": bool(r["anchored"]),
        "esco": str(r["esco_label"]) if r["anchored"] and pd.notna(r.get("esco_label")) else None,
        "cosine": float(r["cosine"]) if pd.notna(r.get("cosine")) else None,
    })

# ---------------------------------------------------------------- D4 -------
sized = named[named["label"].astype(str).str.upper() != "MIXED"].nlargest(60, "occurrences")
pick = rng.choice(sized["cluster"].to_numpy(), size=25, replace=False)
d4 = [{"n": i, "cluster": int(c), "label": str(named.loc[named["cluster"] == c, "label"].iat[0]),
       "occurrences": int(named.loc[named["cluster"] == c, "occurrences"].iat[0]),
       "members": members(int(c), 10)}
      for i, c in enumerate(sorted(pick), 1)]

# ---------------------------------------------------------------- A5 -------
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")
tmap = dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))
reqs["pred"] = reqs["phrase_norm"].map(tmap).fillna("unassigned")
avail = reqs[reqs["pred"] == "availability"].drop_duplicates("phrase_norm")
take = rng.choice(avail.index.to_numpy(), size=min(30, len(avail)), replace=False)
a5 = [{"n": i, "phrase": str(reqs.loc[k, "phrase"])} for i, k in enumerate(sorted(take), 1)]

# ---------------------------------------------------------------- A4 -------
# raw segments only — long ones, since that is where the gate failed
seg = reqs.groupby("vacancy_id")["phrase"].apply(lambda s: None)  # placeholder, unused
base_segs = reqs.drop_duplicates("phrase_norm")
long_atoms = reqs[reqs["from_long_segment"]]
srcs = (long_atoms.groupby("vacancy_id").size().sort_values(ascending=False).head(400).index)
cand = []
for vid in srcs:
    sub = reqs[reqs["vacancy_id"] == vid]
    if len(sub) < 4:
        continue
    cand.append(vid)
pick = rng.choice(np.array(cand), size=min(30, len(cand)), replace=False)
a4 = []
for i, vid in enumerate(sorted(pick), 1):
    sub = reqs[reqs["vacancy_id"] == vid]
    a4.append({"n": i, "vacancy_id": str(vid),
               "atoms_we_found": int(len(sub)),          # count only, never the split
               "language": str(sub["language"].iat[0])})

payload = {
    "seed": SEED,
    "drawn": "2026-09-14",
    "d8": {"method": "random from 617 anchoring decisions, MIXED excluded",
           "items": d8},
    "d4": {"method": "random from the 60 largest groups — by size, not by suspicion",
           "items": d4},
    "a5": {"method": "random from phrases the classifier typed as availability",
           "items": a5},
    "a4": {"method": "raw segments, our split deliberately not shown", "items": a4},
}
with open(W3 + r"\review_sets.json", "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)

print(f"seed {SEED}")
for k in ("d8", "d4", "a5", "a4"):
    print(f"  {k}: {len(payload[k]['items'])} items — {payload[k]['method']}")
print(f"\nwritten: review_sets.json")
print(f"\nD8 anchored/not in the draw: "
      f"{sum(1 for x in d8 if x['anchored'])}/{len(d8)}")
