"""Find every cluster that is a junk drawer, not just the one spotted by eye.

Cluster 615 was found by reading it. That is not a method — it finds the cluster
you happened to look at. The property that made it a junk drawer is testable:
**its members disagree about what kind of thing they are.** Bare one-word atoms
carry almost no context, so they group by shape rather than meaning, and the
result is a cluster whose members span several requirement types.

Two signals, both stated before looking at the output:

  `modal_type_share` < 0.50  — no single requirement type holds a majority
  `pct_single_word`  >= 35   — built largely from context-poor bare atoms

Neither alone is enough. A cluster can be one-word and perfectly coherent
(`Autonomy`, `Flexibility` — French and German adverts write those as bare
bullets), and a cluster can be type-mixed while being about one thing. It is the
conjunction that describes a junk drawer.

Types come from the HYBRID classifier, not the lexicon: at 53% coverage the
lexicon leaves `unassigned` as the modal type of half the corpus, which would
make every cluster look incoherent. At 92.6% the modal share means something.
"""
import sys

sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
pd.set_option("display.width", 260)

MODAL_MAX = 0.50
SINGLE_MIN = 35.0

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

reqs["req_type_hybrid"] = reqs["phrase_norm"].map(
    dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))).fillna("unassigned")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j["n_words"] = j["phrase"].astype(str).str.split().str.len()

rows = []
for cid, sub in j[j["cluster"] != -1].groupby("cluster"):
    vc = sub["req_type_hybrid"].value_counts(normalize=True)
    rows.append({
        "cluster": cid,
        "occurrences": len(sub),
        "modal_type": vc.index[0],
        "modal_type_share": round(float(vc.iloc[0]), 3),
        "n_types_over_10pct": int((vc >= 0.10).sum()),
        "pct_single_word": round(float((sub["n_words"] == 1).mean()) * 100, 1),
        "mean_words": round(float(sub["n_words"].mean()), 2),
    })
d = pd.DataFrame(rows).merge(named[["cluster", "label", "boilerplate"]],
                             on="cluster", how="left")

d["junk"] = (d["modal_type_share"] < MODAL_MAX) & (d["pct_single_word"] >= SINGLE_MIN)

print(f"clusters: {len(d)}")
print(f"  modal type share < {MODAL_MAX}          : {int((d['modal_type_share'] < MODAL_MAX).sum())}")
print(f"  single-word share >= {SINGLE_MIN}%       : {int((d['pct_single_word'] >= SINGLE_MIN).sum())}")
print(f"  BOTH — flagged as junk drawers       : {int(d['junk'].sum())}")
print("")
cols = ["cluster", "label", "occurrences", "modal_type", "modal_type_share",
        "n_types_over_10pct", "pct_single_word", "mean_words", "boilerplate"]
print(d[d["junk"]].sort_values("occurrences", ascending=False)[cols].to_string(index=False))
print("")

print("=" * 100)
print("WHAT IS IN EACH CANDIDATE — judge the rule by its members")
print("=" * 100)
for r in d[d["junk"]].sort_values("occurrences", ascending=False).itertuples():
    sub = j[j["cluster"] == r.cluster]
    print(f"cluster {r.cluster} — '{r.label}'  ({r.occurrences:,} reqs, "
          f"modal {r.modal_type} {r.modal_type_share:.0%}, "
          f"{r.pct_single_word:.0f}% one word)")
    print(f"    types: " + ", ".join(
        f"{k} {v:.0%}" for k, v in
        sub["req_type_hybrid"].value_counts(normalize=True).head(5).items()))
    ex = list(sub["phrase"].value_counts().head(14).items())
    print("    " + "  |  ".join(f"{p} ({n})" for p, n in ex[:7]))
    print("    " + "  |  ".join(f"{p} ({n})" for p, n in ex[7:]))
    print("")

print("=" * 100)
print("CONTROL — one-word clusters the rule does NOT flag (it must not)")
print("=" * 100)
ctl = d[(d["pct_single_word"] >= SINGLE_MIN) & ~d["junk"]].nlargest(8, "occurrences")
print(ctl[cols].to_string(index=False))

d.to_csv(OUT + r"\cluster_coherence.csv", index=False, encoding="utf-8")
print("")
print("written: cluster_coherence.csv")
