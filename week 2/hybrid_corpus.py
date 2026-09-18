"""Apply the hybrid classifier to the CORPUS, and test the translation hypothesis.

`requirements.classify_requirements` calls `classify.classify` — the lexicon
alone. So `requirements.parquet` carries lexicon-only types at ~53% coverage, and
every Week 2 statement that reads `req_type` was computed on the weak classifier:
the residual composition table, the H2 asymmetry, and every cluster's
`top_type`. The hybrid reaches 0.885 coverage on the labelled sample against the
lexicon's 0.526 and has never been run over the corpus.

Two things measured here, in one pass because both need the embedding store.

A. **Is the untyped mass disproportionately non-English?** This is the testable
   core of the proposal to translate everything to English first. If the
   lexicon's abstentions are concentrated in non-English text, translation
   targets the right thing; if they are mostly English, it cannot help.

B. **What does the hybrid recover?** Coverage, the new type mix, and the
   accuracy price paid for it — the lexicon scores 0.927 on what it assigns, the
   hybrid 0.754, so this trades precision for characterisation and both numbers
   have to travel together.
"""
import sys

sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import classify_embed as ce, config, embed as emb, language as lang
from karimi import requirements as rq

OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 250)

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
print(f"requirements: {len(reqs):,}   unique phrases: {reqs['phrase_norm'].nunique():,}")
print(f"current req_type is LEXICON ONLY — unassigned "
      f"{(reqs['req_type'] == 'unassigned').mean():.2%}")
print("")

# ---------------------------------------------------------------- A. language
print("=" * 90)
print("A. IS THE UNTYPED MASS NON-ENGLISH? (the translation hypothesis)")
print("=" * 90)
# Detection on a 5-word atom is weak, so the atom's own detection is used only
# where the stopword detector actually found something; otherwise the posting's
# recorded language stands in. Both are reported so the weakness is visible.
det = lang.detect_series(reqs["phrase"])
reqs["atom_lang"] = det["detected"]
reqs["atom_hits"] = det["hits"]
reqs["text_lang"] = reqs["atom_lang"].where(det["hits"] >= 1, reqs["language"])
reqs["untyped"] = reqs["req_type"] == "unassigned"
print(f"  atom-level detection fired on {float((det['hits'] >= 1).mean()):.1%} of atoms; "
      f"the rest fall back to the posting's recorded language")

tab = (reqs.groupby("text_lang")
       .agg(requirements=("phrase", "size"), untyped_pct=("untyped", "mean"))
       .assign(untyped_pct=lambda d: (d["untyped_pct"] * 100).round(1))
       .sort_values("requirements", ascending=False))
tab["share_of_corpus"] = (tab["requirements"] / len(reqs) * 100).round(1)
print(tab.head(12).to_string())
print("")
eng = reqs["text_lang"].eq("English")
print(f"  English text        : {eng.mean():>6.1%} of the corpus, "
      f"untyped {reqs.loc[eng, 'untyped'].mean():.1%}")
print(f"  non-English text    : {(~eng).mean():>6.1%} of the corpus, "
      f"untyped {reqs.loc[~eng, 'untyped'].mean():.1%}")
share_non_en = float(reqs.loc[reqs["untyped"], "text_lang"].ne("English").mean())
print(f"  share of the UNTYPED mass that is non-English: {share_non_en:.1%}")
print(f"  (against {(~eng).mean():.1%} non-English in the corpus overall — the gap is"
      f" what translation could address)")
print("")

# ---------------------------------------------------------------- B. hybrid
print("=" * 90)
print("B. RUNNING THE HYBRID OVER THE CORPUS")
print("=" * 90)
phrases, vecs = emb.load_corpus(W1 + r"\embeddings.npz")
store = {p: i for i, p in enumerate(phrases)}
uniq = reqs["phrase_norm"].astype(str).unique()
have = np.array([p in store for p in uniq])
print(f"  unique phrases {len(uniq):,}   in the embedding store {have.sum():,} "
      f"({have.mean():.1%})")

idx = np.array([store[p] for p in uniq[have]])
model = emb.load_model()
types, centroids = ce.fit_prototypes(model)
emb_pred, best, margin = ce.classify_vectors(vecs[idx], types, centroids)

from karimi import classify as lex
lex_pred = {p: lex.classify(p) for p in uniq}

hybrid = {}
for p, e in zip(uniq[have], emb_pred):
    h = lex_pred.get(p)
    hybrid[p] = h if h in ce.LEXICON_PRECEDENCE else (e if e is not None else h)
for p in uniq[~have]:                      # no vector: lexicon or nothing
    hybrid[p] = lex_pred.get(p)

reqs["req_type_hybrid"] = reqs["phrase_norm"].astype(str).map(hybrid).fillna("unassigned")
print("")
print("  coverage on the corpus:")
print(f"    lexicon only : {1 - (reqs['req_type'] == 'unassigned').mean():.1%}")
print(f"    hybrid       : {1 - (reqs['req_type_hybrid'] == 'unassigned').mean():.1%}")
print("")
a = reqs["req_type"].value_counts(normalize=True).mul(100).round(2)
b = reqs["req_type_hybrid"].value_counts(normalize=True).mul(100).round(2)
mix = pd.DataFrame({"lexicon": a, "hybrid": b}).fillna(0)
mix["shift_pp"] = (mix["hybrid"] - mix["lexicon"]).round(2)
print("  type mix, occurrences (%):")
print(mix.sort_values("hybrid", ascending=False).to_string())
print("")
print("  by function, hybrid:")
print(pd.crosstab(reqs["req_type_hybrid"], reqs["macro_function"],
                  normalize="columns").mul(100).round(1).to_string())
print("")
print("  where the recovered mass went (previously unassigned only):")
rec = reqs[reqs["req_type"] == "unassigned"]
print(rec["req_type_hybrid"].value_counts(normalize=True).mul(100).round(1).to_string())
print("")
print("  and how much of the recovery is non-English text:")
r2 = rec[rec["req_type_hybrid"] != "unassigned"]
print(f"    {r2['text_lang'].ne('English').mean():.1%} of recovered requirements are non-English")

reqs[["vacancy_id", "phrase_norm", "req_type", "req_type_hybrid", "text_lang"]].to_parquet(
    OUT + r"\req_type_hybrid.parquet", index=False)
print("")
print(f"  written: req_type_hybrid.parquet")
