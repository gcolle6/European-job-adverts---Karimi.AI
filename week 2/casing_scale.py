"""How big is the lowercasing effect? Measured before anything is claimed.

`Experience with Azure` is assigned from its NORMALISED form,
`experience with azure`, and the two embeddings sit at cosine 0.5223 — further
apart than most genuinely different requirements are from each other. Raw, it
goes to `Cloud platforms [AWS, Azure]`; normalised, to `Relevant experience`.

The embedding model is **cased**. Lowercasing removes the capital that marks a
named entity, and a named entity is exactly what distinguishes
`Experience with Azure` from generic experience language.

If this is systematic it explains the grab-bag groups, and it is a pipeline
defect rather than a property of the embedding. If it is a handful of phrases it
is a curiosity. Two samples decide it:

  * phrases carrying a mid-sentence capitalised token — the ones with something
    to lose;
  * a control of phrases with none, which should barely move.
"""
import re
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import embed as emb

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 250)

N = 2500
CAP_RE = re.compile(r"(?<!^)\b[A-Z][A-Za-z0-9]{1,}\b")

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
cids = np.array(z["cluster_ids"])
C = z["centroids"]
C = C / np.clip(np.linalg.norm(C, axis=1, keepdims=True), 1e-12, None)

uniq = reqs.drop_duplicates("phrase_norm")[["phrase", "phrase_norm"]].copy()
uniq["has_cap"] = uniq["phrase"].astype(str).str.contains(CAP_RE, na=False)
print(f"unique phrases: {len(uniq):,}   carrying a mid-phrase capital: "
      f"{uniq['has_cap'].mean():.1%}")

model = emb.load_model()


def compare(frame, label):
    raw = frame["phrase"].astype(str).tolist()
    nrm = frame["phrase_norm"].astype(str).tolist()
    A = emb.encode(model, raw)
    B = emb.encode(model, nrm)
    A = A / np.clip(np.linalg.norm(A, axis=1, keepdims=True), 1e-12, None)
    B = B / np.clip(np.linalg.norm(B, axis=1, keepdims=True), 1e-12, None)
    pair_cos = np.sum(A * B, axis=1)
    ca = cids[np.argmax(A @ C.T, axis=1)]
    cb = cids[np.argmax(B @ C.T, axis=1)]
    changed = ca != cb
    print(f"\n  {label}  (n={len(frame)})")
    print(f"    cosine(raw, normalised): median {np.median(pair_cos):.4f}  "
          f"mean {pair_cos.mean():.4f}  p10 {np.quantile(pair_cos, .1):.4f}")
    print(f"    nearest group CHANGES for {changed.mean():.1%} of them")
    return frame.assign(raw_cluster=ca, norm_cluster=cb, changed=changed,
                        pair_cos=pair_cos)


cap = uniq[uniq["has_cap"]].sample(N, random_state=3)
nocap = uniq[~uniq["has_cap"]].sample(N, random_state=3)
r1 = compare(cap, "phrases WITH a mid-phrase capital")
r2 = compare(nocap, "CONTROL — phrases without one")

print("\n" + "=" * 92)
print("WHERE THE CAPITALISED ONES GO WHEN LOWERCASED")
print("=" * 92)
ch = r1[r1["changed"]]
gain = ch["norm_cluster"].value_counts().head(8)
print("  groups that GAIN phrases through lowercasing:")
for c, n in gain.items():
    print(f"    +{n:>4}  cluster {int(c):>3}  {str(lab.get(int(c), '?'))[:46]}")
print("\n  groups that LOSE them:")
for c, n in ch["raw_cluster"].value_counts().head(8).items():
    print(f"    -{n:>4}  cluster {int(c):>3}  {str(lab.get(int(c), '?'))[:46]}")
print("\n  examples:")
for r in ch.sample(min(10, len(ch)), random_state=1).itertuples():
    print(f"    {str(r.phrase)[:44]:<46} {str(lab.get(int(r.raw_cluster),'?'))[:24]:<26}"
          f" -> {str(lab.get(int(r.norm_cluster),'?'))[:24]}")
