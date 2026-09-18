"""What is in the 'other' third of the residual?

Step 19 assigned a reason to residual groups from two features — does it name
something, do its members agree — and 33% of sales' residual and 44% of
software's landed in neither box. That is the largest single bucket for software
and calling it "uncharacterised" is a description of our filing, not of the data.

'Other' is not one thing. It is two opposite failures of the rule:

  * **named but incoherent** — entity yes, consistency no. Members mention
    specific things and still do not converge, which usually means SEVERAL
    different named things share a group;
  * **coherent but unnamed** — consistency yes, entity no. Members agree on a
    topic that nothing in the group names. Neither new nor vague: a general
    competence area at a granularity ESCO does not carry.

Also tested: whether the three-way split is forcing structure onto continuous
features. If most groups sit near a threshold rather than away from it, the
boxes are arbitrary and the honest report is a gradient, not a taxonomy.
"""
import re
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)

ENTITY_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][A-Za-z0-9]{1,}\b|\b\w*[0-9#+/][\w#+./]*\b")
CONSISTENT_MIN, ENTITY_MIN = 0.80, 0.30

res = pd.read_csv(W3 + r"\residual_by_reason.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
j = reqs.merge(asg[["phrase_norm", "cluster", "similarity"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)

oth = res[res["reason"] == "other"].copy()
oth["sub"] = np.where(oth["entity_share"] >= ENTITY_MIN,
                      "named but incoherent", "coherent but unnamed")

print("=" * 94)
print("1. 'OTHER' IS TWO OPPOSITE THINGS")
print("=" * 94)
print(oth.groupby("sub").agg(groups=("cluster", "size"),
                             occurrences=("occurrences", "sum"),
                             mean_entity=("entity_share", "mean"),
                             mean_consistency=("consistency", "mean")).round(3).to_string())
print("")

# by function, in mass
rmap = dict(zip(oth["cluster"], oth["sub"]))
sub = j[j["cluster"].isin(rmap)].copy()
sub["sub"] = sub["cluster"].map(rmap)
allres = j[j["cluster"].isin(res["cluster"])]
tot = allres.groupby("macro_function").size()
share = sub.groupby(["sub", "macro_function"]).size().unstack(fill_value=0) / tot * 100
print("share of each family's RESIDUAL mass:")
print(share.round(1).to_string())
print("")

print("=" * 94)
print("2. WHAT THEY LOOK LIKE")
print("=" * 94)
for s in ["named but incoherent", "coherent but unnamed"]:
    print(f"  --- {s.upper()} ---")
    for r in oth[oth["sub"] == s].nlargest(5, "occurrences").itertuples():
        mem = j[j["cluster"] == r.cluster]["phrase"].value_counts().head(5)
        print(f"    [{r.occurrences:>5}] {str(r.label)[:38]:<40} "
              f"entity {r.entity_share:.2f} consistency {r.consistency:.3f}")
        print(f"             " + " | ".join(str(p)[:34] for p in mem.index))
    print("")

print("=" * 94)
print("3. DO 'NAMED BUT INCOHERENT' GROUPS HOLD SEVERAL ENTITIES?")
print("=" * 94)
STOP = {"Experience", "Knowledge", "Strong", "Good", "Excellent", "Solid", "Proven",
        "Understanding", "Familiarity", "Proficiency", "Ability", "Working", "Deep"}


def n_entities(frame):
    toks = []
    for p in frame["phrase"].astype(str):
        toks += [m for m in re.findall(r"(?<!^)\b[A-Z][A-Za-z0-9]{2,}\b", p) if m not in STOP]
    return len(set(toks))


rows = []
for s in ["named but incoherent", "coherent but unnamed"]:
    for r in oth[oth["sub"] == s].nlargest(40, "occurrences").itertuples():
        f = j[j["cluster"] == r.cluster]
        rows.append({"sub": s, "cluster": r.cluster,
                     "distinct_entities": n_entities(f),
                     "per_100_reqs": round(n_entities(f) / max(len(f), 1) * 100, 1)})
e = pd.DataFrame(rows)
print(e.groupby("sub")[["distinct_entities", "per_100_reqs"]].mean().round(1).to_string())
nov = res[res["reason"] == "novelty"].nlargest(40, "occurrences")
nr = [n_entities(j[j["cluster"] == c]) for c in nov["cluster"]]
nl = [len(j[j["cluster"] == c]) for c in nov["cluster"]]
print(f"  NOVELTY groups, for comparison: distinct_entities "
      f"{np.mean(nr):.1f}, per 100 reqs {np.mean(np.array(nr)/np.array(nl)*100):.1f}")
print("")

print("=" * 94)
print("4. IS THE THREE-WAY SPLIT FORCING STRUCTURE ON A GRADIENT?")
print("=" * 94)
r2 = res[res["reason"] != "structural"]
for col, thr in [("entity_share", ENTITY_MIN), ("consistency", CONSISTENT_MIN)]:
    v = r2[col]
    near = ((v - thr).abs() < 0.05).mean()
    print(f"  {col:<13} median {v.median():.3f}  IQR {v.quantile(.25):.3f}-{v.quantile(.75):.3f}"
          f"   within 0.05 of the threshold: {near:.1%}")
print("")
print("  how many groups would change reason if each threshold moved by 0.05:")
for d in (-0.05, 0.05):
    ent = ENTITY_MIN + d
    con = CONSISTENT_MIN + d
    nov_n = int(((r2["entity_share"] >= ent) & (r2["consistency"] >= con)).sum())
    vag_n = int(((r2["entity_share"] < ent) & (r2["consistency"] < con)).sum())
    print(f"    shift {d:+.2f}:  novelty {nov_n:>3}   vagueness {vag_n:>3}")
base_nov = int(((r2["entity_share"] >= ENTITY_MIN) & (r2["consistency"] >= CONSISTENT_MIN)).sum())
base_vag = int(((r2["entity_share"] < ENTITY_MIN) & (r2["consistency"] < CONSISTENT_MIN)).sum())
print(f"    baseline  :  novelty {base_nov:>3}   vagueness {base_vag:>3}")
