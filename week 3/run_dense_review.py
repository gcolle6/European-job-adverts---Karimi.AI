"""The 63 densest groups, laid out for a person to judge.

The scan's binary verdict is unusable — it flags 87% of groups — but its
*density* orders them, and the top of that order contains the cases a human
review had already found. So this is not a filter: it is a reading order, and it
stops paying somewhere down the list.

Each group is shown with the phrases the scan kept **and** phrases it passed
over, because a flag can only be judged against what the group is supposed to be
about. Without the unflagged members a reader cannot tell an intruder from a
group that is simply broad.
"""
import ast
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)

MIN_FLAGS = 6

scan = pd.read_csv(W3 + r"\intruder_scan.csv")
scan["intruders"] = scan["intruders"].apply(
    lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith("[") else [])
scan["n"] = scan["intruders"].apply(len)
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
members = {int(c): [str(p) for p in s["phrase"].value_counts().head(12).index]
           for c, s in j[j["cluster"] != -1].groupby("cluster")}

dense = (scan[scan["n"] >= MIN_FLAGS]
         .merge(named[["cluster", "occurrences", "top_type", "boilerplate"]],
                on="cluster", how="left")
         .sort_values(["n", "occurrences"], ascending=[False, False]))

lines = []
lines.append(f"# The {len(dense)} densest groups — review sheet\n")
lines.append(f"Groups where the scan flagged {MIN_FLAGS} or more of the 12 members shown.")
lines.append("Ordered by flag density, then size. `x` marks a flagged phrase, `·` one the")
lines.append("scan passed over — you need both to judge whether a flag is right.\n")
lines.append("The scan's binary verdict is not trustworthy (it flags 87% of all groups).")
lines.append("Its ORDER is what carries information, and it stops paying somewhere below.\n")

print(f"{len(dense)} groups with >= {MIN_FLAGS} flags   "
      f"({int(dense['occurrences'].sum()):,} requirements, "
      f"{dense['occurrences'].sum()/reqs.shape[0]:.1%} of the corpus)")
print(f"boilerplate among them: {int(dense['boilerplate'].sum())}\n")

for i, r in enumerate(dense.itertuples(), 1):
    mem = members.get(int(r.cluster), [])
    flg = set(r.intruders)
    head = (f"## {i}. {r.label}  —  {r.occurrences:,} requirements  "
            f"[{r.top_type}]{'  (boilerplate)' if r.boilerplate else ''}")
    lines.append(head)
    lines.append(f"cluster {r.cluster} · {r.n} of {len(mem)} flagged\n")
    for m in mem:
        lines.append(f"    {'x' if m in flg else '·'}  {m}")
    lines.append("")

with open(W3 + r"\dense_groups_review.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

print("the top 12, to read here:\n")
for i, r in enumerate(dense.head(12).itertuples(), 1):
    mem = members.get(int(r.cluster), [])
    flg = set(r.intruders)
    print(f"{i:>2}. {str(r.label)[:40]:<42} {r.occurrences:>5} reqs   {r.n}/{len(mem)} flagged")
    for m in mem[:7]:
        print(f"       {'x' if m in flg else '·'}  {str(m)[:66]}")
    print("")

print(f"written: dense_groups_review.md — all {len(dense)} groups, full member lists")
