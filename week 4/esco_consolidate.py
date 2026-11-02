"""One published ESCO number, from three draws instead of one.

**The problem this solves.** The residual is 617 judgements from a language
model, and `week 4/esco_stability.py` measured what nobody had asked: put the
identical question twice and it agrees on 90.8% of groups, and on only 54.0% of
the concepts it picks. Per-group decisions are noisy. The aggregate is not -
two draws of the same procedure gave 26.44% and 25.75% - but a single draw is a
sample, and reporting it to three decimals pretends otherwise.

So the final procedure is drawn three times and each group takes the majority.
The spread across draws is reported beside the figure as the band it is.

**The reason split is recomputed, not carried over.** `week 3/residual_by_reason`
covers the 193 groups v1 happened to leave unanchored; the majority set is a
different set, and reusing the old file would quietly mix two populations. The
features and thresholds here are step 19's, unchanged: an entity regex over the
cased phrase, mean member-to-centre similarity, and credential/availability
typed as structural.

    python "week 4/esco_consolidate.py"
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
W1 = ROOT / "week 1" / "output"
OUT = ROOT / "week 2" / "output"
DATA = ROOT / "week 4" / "data"

DRAWS = ["v3", "v3b", "v3c"]                    # the final procedure, three times
ENTITY_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][A-Za-z0-9]{1,}\b|"
                       r"\b\w*[0-9#+/][\w#+./]*\b")
CONSISTENT_MIN, ENTITY_MIN = 0.80, 0.30

reqs = pd.read_parquet(W1 / "requirements.parquet")
hyb = pd.read_parquet(OUT / "req_type_hybrid.parquet")
asg = pd.read_parquet(OUT / "phrase_clusters.parquet")
named = pd.read_csv(OUT / "cluster_dictionary_named.csv")

reqs["type"] = reqs["phrase_norm"].map(
    dict(zip(hyb["phrase_norm"], hyb["req_type_hybrid"]))).fillna("unassigned")
j = reqs.merge(asg[["phrase_norm", "cluster", "similarity"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)

draws = {t: pd.read_csv(OUT / f"esco_decisions_{t}.csv") for t in DRAWS}
votes = pd.DataFrame({t: d.set_index("cluster")["esco_uri"].notna() for t, d in draws.items()})
votes["n_anchored"] = votes[DRAWS].sum(axis=1)
votes["anchored"] = votes["n_anchored"] >= 2
votes["unanimous"] = votes["n_anchored"].isin([0, 3])

print("=" * 84)
print("THREE DRAWS OF THE SAME PROCEDURE")
print("=" * 84)
for t in DRAWS:
    s = set(votes.index[~votes[t]])
    by = j.groupby("macro_function")["cluster"].apply(lambda c: c.isin(s).mean())
    print(f"  {t:5} residual {j['cluster'].isin(s).mean():.2%}   "
          + "  ".join(f"{k} {v:.2%}" for k, v in by.items()))

final = set(votes.index[~votes["anchored"]])
by = j.groupby("macro_function")["cluster"].apply(lambda c: c.isin(final).mean())
print(f"\n  MAJORITY residual {j['cluster'].isin(final).mean():.2%}   "
      + "  ".join(f"{k} {v:.2%}" for k, v in by.items()))

print(f"\n  groups all three agree on   {int(votes['unanimous'].sum())} of {len(votes)} "
      f"({votes['unanimous'].mean():.1%})")
unstable = set(votes.index[~votes["unanimous"]])
print(f"  mass in groups they do not  {j['cluster'].isin(unstable).mean():.2%}")
spread = [j["cluster"].isin(set(votes.index[~votes[t]])).mean() for t in DRAWS]
print(f"  band across draws           {min(spread):.2%} to {max(spread):.2%}")

# ------------------------------------------------------- reasons, recomputed
placed = j[j["cluster"] != -1].copy()
placed["has_entity"] = placed["phrase"].astype(str).str.contains(ENTITY_RE, na=False)
g = (placed.groupby("cluster")
     .agg(occurrences=("phrase", "size"), entity_share=("has_entity", "mean"),
          consistency=("similarity", "mean")).reset_index()
     .merge(named[["cluster", "label"]], on="cluster", how="left"))
g["type"] = g["cluster"].map(placed.groupby("cluster")["type"].agg(lambda s: s.mode().iat[0]))
g["anchored"] = g["cluster"].map(votes["anchored"]).fillna(True)

res = g[~g["anchored"]].copy()
res["reason"] = "other"
res.loc[res["type"].isin(["credential", "availability"]), "reason"] = "structural"
m = res["reason"] == "other"
res.loc[m & (res["entity_share"] >= ENTITY_MIN) &
        (res["consistency"] >= CONSISTENT_MIN), "reason"] = "novelty"
res.loc[m & (res["entity_share"] < ENTITY_MIN) &
        (res["consistency"] < CONSISTENT_MIN), "reason"] = "vagueness"

print()
print("=" * 84)
print("THE RESIDUAL, SPLIT BY REASON")
print("=" * 84)
rmap = dict(zip(res["cluster"], res["reason"]))
rp = j[j["cluster"].isin(final)].copy()
rp["reason"] = rp["cluster"].map(rmap)
fam = {"SOFTWARE_DATA": "software", "SALES_BD": "sales"}
families = []
for fn, short in fam.items():
    tot = (j["macro_function"] == fn).sum()
    sub = rp[rp["macro_function"] == fn]
    segs = [{"reason": r, "key": k,
             "share_of_family": round(float((sub["reason"] == k).sum() / tot), 4)}
            for k, r in (("novelty", "names something not yet catalogued"),
                         ("vagueness", "names nothing in particular"),
                         ("structural", "ESCO does not model it at all"),
                         ("other", "no reason assigned"))]
    families.append({"family": short, "residual_share": round(len(sub) / tot, 4),
                     "segments": segs})
    print(f"  {short:9} {len(sub)/tot:.2%}   "
          + "  ".join(f"{s['key']} {s['share_of_family']:.2%}" for s in segs))

# ------------------------------------------------------------------- outputs
dec = draws[DRAWS[0]][["cluster", "label"]].copy()
dec["anchored"] = dec["cluster"].map(votes["anchored"])
dec["votes_anchored"] = dec["cluster"].map(votes["n_anchored"])
dec["unanimous"] = dec["cluster"].map(votes["unanimous"])
for t in DRAWS:
    dec[f"esco_{t}"] = dec["cluster"].map(draws[t].set_index("cluster")["esco_label"])
dec.to_csv(OUT / "esco_decisions_final.csv", index=False, encoding="utf-8")

payload = {
    "esco_version": "v1.2.0", "esco_released": "2024-05",
    "newer_release_not_used": "v1.2.1 (2025-12)",
    "pillar": "skills only - occupations and qualifications were not searched",
    "anchor_set": {"skills": 13939, "hierarchy_headings": 420, "labels": 214482,
                   "languages": 6, "of_which_esco_publishes": 28},
    "method": "cosine shortlist k=5 + exact-label channel + LLM adjudication, "
              "majority of three draws",
    "model": "gpt-5.4-mini-2026-03-17", "prompt_version": "anchor-v3",
    "stability": {"draws": len(DRAWS),
                  "groups_unanimous": int(votes["unanimous"].sum()),
                  "groups": int(len(votes)),
                  "mass_in_disputed_groups": round(float(j["cluster"].isin(unstable).mean()), 4),
                  "residual_band": [round(min(spread), 4), round(max(spread), 4)],
                  "same_question_twice_agreement": 0.908},
    "residual_majority": {
        "overall": round(float(j["cluster"].isin(final).mean()), 4),
        "by_function": {k: round(float(v), 4) for k, v in by.items()}},
    "families": families,
}
(OUT / "esco_residual_final.json").write_text(
    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
(DATA / "chart3_residual.json").write_text(
    json.dumps({"families": families}, indent=1, ensure_ascii=False), encoding="utf-8")
res.to_csv(ROOT / "week 4" / "residual_by_reason_final.csv", index=False, encoding="utf-8")
print("\nwritten: esco_decisions_final.csv, esco_residual_final.json,")
print("         week 4/data/chart3_residual.json, week 4/residual_by_reason_final.csv")
