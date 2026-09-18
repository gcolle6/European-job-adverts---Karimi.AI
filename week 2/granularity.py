"""Follow-up: proper word boundaries, and can the industry question be answered?"""
import re
import sys
sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")
import pandas as pd

OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
pd.set_option("display.width", 250)

reqs = pd.read_parquet(r"week 1/output/requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
lab = dict(zip(named["cluster"], named["label"]))

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j["p"] = j["phrase_norm"].astype(str)

PAT = {
    "python":   r"(?<![a-z])python(?![a-z])",
    "java":     r"(?<![a-z])java(?!script)(?![a-z])",
    "excel":    r"(?<![a-z])excel(?![a-z])",
    "rust":     r"(?<![a-z])rust(?![a-z])",
    "aws":      r"(?<![a-z])aws(?![a-z])",
    "azure":    r"(?<![a-z])azure(?![a-z])",
    "sql":      r"(?<![a-z])sql(?![a-z])",
    "nosql":    r"(?<![a-z])nosql(?![a-z])",
}

print("=" * 96)
print("WITH WORD BOUNDARIES — the top 4 clusters each token lands in")
print("=" * 96)
for tk, pat in PAT.items():
    m = j[j["p"].str.contains(pat, regex=True, na=False)]
    m = m[m["cluster"] != -1]
    print(f"{tk}  ({len(m):,} requirements)")
    if not len(m):
        print("    none"); continue
    vc = m["cluster"].value_counts().head(4)
    for cid, n in vc.items():
        print(f"    {n:>5} ({n/len(m):>5.1%})  cluster {int(cid):>3}  {str(lab.get(int(cid),'?'))[:52]}")
    print("")

# --- the analysis the user actually wants ------------------------------------
print("=" * 96)
print("CAN WE ANSWER 'IS JAVA ASKED FOR MORE THAN PYTHON, BY INDUSTRY'?")
print("=" * 96)
sw = j[j["macro_function"] == "SOFTWARE_DATA"]
targets = {"Python": 114, "Java": 246, "JavaScript": 262, "SQL": 175, "C#": 255}
post = sw.groupby("company_industry")["vacancy_id"].nunique().rename("postings")
tab = {}
for name, cid in targets.items():
    hit = (sw[sw["cluster"] == cid].groupby("company_industry")["vacancy_id"]
           .nunique().rename(name))
    tab[name] = hit
t = pd.concat([post] + list(tab.values()), axis=1).fillna(0)
for name in targets:
    t[name] = (t[name] / t["postings"] * 100).round(1)
t = t[t["postings"] >= 100].sort_values("Python", ascending=False)
print("share of software adverts in each industry asking for each language (%)")
print(t.to_string())
print("")
t2 = t.copy()
t2["Java_over_Python"] = (t2["Java"] / t2["Python"].replace(0, float("nan"))).round(2)
print("Java-to-Python ratio by industry:")
print(t2[["postings", "Python", "Java", "Java_over_Python"]]
      .sort_values("Java_over_Python", ascending=False).to_string())
