"""Same scoring, but with the 2026-09-03 domain re-labels merged in.

The main labelled file still carries round 1's `domain` labels, which sat on a
boundary that was later moved. The corrections live in the recheck sheet and have
to be joined at scoring time or the classifier is scored against a definition
nobody holds any more.
"""
import sys

sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import atomise as atom_mod, classify as lex, classify_embed as ce
from karimi import config, embed as emb_mod, evaluate

pd.set_option("display.width", 250)
VAL = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\validation"

c = pd.read_csv(VAL + r"\validation_classification_LABELLED.csv")
c["true_type"] = c["true_type"].astype(str).str.strip().str.lower()
c = c[c["true_type"].isin(config.REQUIREMENT_TYPES)].copy()

rc = pd.read_csv(VAL + r"\validation_recheck_domain_LABELLED.csv")
rc["true_type"] = rc["true_type"].astype(str).str.strip().str.lower()
fix = dict(zip(rc["phrase"].astype(str).str.strip(), rc["true_type"]))
before = c["true_type"].copy()
c["true_type"] = [fix.get(str(p).strip(), t) for p, t in zip(c["phrase"], c["true_type"])]
moved = int((before != c["true_type"]).sum())
c["provenance"] = ["lead (recheck)" if str(p).strip() in fix else "independent"
                   for p in c["phrase"]]
print(f"re-labels merged: {moved} of {len(rc)} recheck rows changed the label")
print("")
print("corrected label distribution:")
print(c["true_type"].value_counts().to_string())
print("")

c = evaluate.dev_holdout_split(c, text_col="phrase")
model = emb_mod.load_model()
types, centroids = ce.fit_prototypes(model)
vecs = emb_mod.encode(model, c["phrase"].tolist())
emb_pred, _, _ = ce.classify_vectors(vecs, types, centroids)
c["lexicon"] = [lex.classify(atom_mod.normalise(p)) for p in c["phrase"]]
c["embedding"] = emb_pred
c["hybrid"] = [h if h in ce.LEXICON_PRECEDENCE else (x if x is not None else h)
               for h, x in zip(c["lexicon"], c["embedding"])]


def score(frame, eng):
    a = frame[eng].notna()
    ok = (frame[eng] == frame["true_type"]) & a
    return {"n": len(frame), "coverage": round(float(a.mean()), 3),
            "acc_on_assigned": round(float(ok.sum() / max(a.sum(), 1)), 3),
            "honest_acc": round(float(ok.mean()), 3)}


print("=" * 78)
print("BY ENGINE, holdout half, corrected labels")
print("=" * 78)
h = c[c["split"] == "holdout"]
print(pd.DataFrame([{"engine": e, **score(h, e)} for e in
                    ["lexicon", "embedding", "hybrid"]]).to_string(index=False))
print("")

print("=" * 78)
print("HYBRID, by label provenance -- these must not be pooled")
print("=" * 78)
rows = [{"set": "119 independent labels", **score(c[c["provenance"] == "independent"], "hybrid")},
        {"set": "  of those, holdout only", **score(c[(c["provenance"] == "independent") & (c["split"] == "holdout")], "hybrid")},
        {"set": "31 lead-relabelled", **score(c[c["provenance"] == "lead (recheck)"], "hybrid")},
        {"set": "all 150 pooled", **score(c, "hybrid")}]
print(pd.DataFrame(rows).to_string(index=False))
print("")

print("=" * 78)
print("PER TYPE, hybrid, corrected labels, all 150")
print("=" * 78)
per = []
for t in config.REQUIREMENT_TYPES:
    truth, pred = c["true_type"] == t, c["hybrid"] == t
    tp = int((truth & pred).sum())
    per.append({"type": t, "n_true": int(truth.sum()), "n_pred": int(pred.sum()),
                "correct": tp,
                "recall": round(tp / truth.sum(), 3) if truth.sum() else None,
                "precision": round(tp / pred.sum(), 3) if pred.sum() else None})
print(pd.DataFrame(per).to_string(index=False))
print("")
print("=" * 78)
print("CONFUSION, corrected labels (rows = truth, cols = prediction)")
print("=" * 78)
print(pd.crosstab(c["true_type"], c["hybrid"].fillna("(abstained)")).to_string())
