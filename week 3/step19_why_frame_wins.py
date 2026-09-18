"""Why does `Experience with Azure` land in `Relevant experience` and not in Azure?

Both groups exist. Assignment is nearest-centroid, so the question has an exact
answer: which centroid is nearer, and by how much. If the frame group wins by a
hair, the assignment is near-arbitrary and the grab-bags are a margin problem. If
it wins comfortably, the embedding genuinely encodes the phrase frame more
strongly than the object — which is a deeper problem and a property of the model,
not of our thresholds.

Then the same question corpus-wide: are assignments INTO the grab-bag groups
decided by thinner margins than assignments elsewhere?
"""
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import embed as emb

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 250)

named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
cids = np.array(z["cluster_ids"])
cents = z["centroids"]
cents = cents / np.clip(np.linalg.norm(cents, axis=1, keepdims=True), 1e-12, None)

model = emb.load_model()
EXAMPLES = ["Experience with Azure", "Experience with APIs", "Knowledge of Kubernetes",
            "Familiarity with Azure", "Azure", "Experience with Jenkins",
            "Erfahrungen als Tischler", "Strong experience with Python"]
v = emb.encode(model, EXAMPLES)
v = v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None)
sims = v @ cents.T

print("=" * 96)
print("WHERE EACH PHRASE WAS NEARLY ASSIGNED — top 5 centroids")
print("=" * 96)
for i, phrase in enumerate(EXAMPLES):
    order = np.argsort(-sims[i])[:5]
    print(f"{phrase}")
    for rank, k in enumerate(order):
        cid = int(cids[k])
        mark = " <- WINNER" if rank == 0 else ""
        print(f"    {sims[i][k]:.4f}  cluster {cid:>3}  {str(lab.get(cid, '?'))[:44]}{mark}")
    gap = sims[i][order[0]] - sims[i][order[1]]
    print(f"    margin over runner-up: {gap:.4f}")
    print("")

print("=" * 96)
print("CORPUS-WIDE: are grab-bag assignments decided by thinner margins?")
print("=" * 96)
phrases, vecs = emb.load_corpus(W1 + r"\embeddings.npz")
store = {p: i for i, p in enumerate(phrases)}
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
asg = asg[asg["cluster"] != -1]

sample = asg.sample(20000, random_state=7).copy()
idx = [store[p] for p in sample["phrase_norm"] if p in store]
sample = sample[sample["phrase_norm"].isin(store)]
V = vecs[idx]
V = V / np.clip(np.linalg.norm(V, axis=1, keepdims=True), 1e-12, None)
S = V @ cents.T
part = np.partition(-S, 1, axis=1)
best, second = -part[:, 0], -part[:, 1]
sample["margin"] = best - second

GRAB = [612, 613, 574, 606, 575]           # the named-but-incoherent frame groups
sample["grab"] = sample["cluster"].isin(GRAB)
print(sample.groupby("grab")["margin"].describe()[["count", "mean", "25%", "50%", "75%"]].round(4).to_string())
print("")
print("  a thin margin means the runner-up group was nearly as close,")
print("  so the assignment was decided by very little")
print("")
for cid in GRAB:
    s = sample[sample["cluster"] == cid]
    if len(s) < 20:
        continue
    print(f"  cluster {cid:>3} {str(lab.get(cid,'?'))[:34]:<36} "
          f"n={len(s):>4}  median margin {s['margin'].median():.4f}")
rest = sample[~sample["grab"]]
print(f"  {'everything else':<40} n={len(rest):>4}  median margin {rest['margin'].median():.4f}")
