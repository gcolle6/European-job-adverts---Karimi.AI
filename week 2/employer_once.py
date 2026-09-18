"""What 'counting each employer once' actually changes, on one real cell."""
import sys
sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")
import pandas as pd

OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
pd.set_option("display.width", 250)

reqs = pd.read_parquet(r"week 1/output/requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)

CELL = ("SALES_BD", "Commerce & Retail")
cell = j[(j["macro_function"] == CELL[0]) & (j["company_industry"] == CELL[1])]

n_post = cell["vacancy_id"].nunique()
n_emp = cell["company"].nunique()
print(f"cell: {CELL[0]} / {CELL[1]}")
print(f"  postings  {n_post}")
print(f"  employers {n_emp}")
print("")
top = cell.drop_duplicates("vacancy_id")["company"].value_counts().head(5)
print("  postings per employer, top 5:")
for k, v in top.items():
    print(f"    {str(k)[:40]:<42} {v:>4}  ({v/n_post:.1%} of the cell)")
print("")

# per cluster: share of postings vs share of employers
pc = cell.groupby("cluster").agg(
    postings_with=("vacancy_id", "nunique"),
    employers_with=("company", "nunique"),
).reset_index()
pc["share_postings"] = pc["postings_with"] / n_post
pc["share_employers"] = pc["employers_with"] / n_emp
pc["gap"] = pc["share_postings"] - pc["share_employers"]
pc = pc.merge(named[["cluster", "label"]], on="cluster", how="left")

print("clusters where counting postings most overstates demand:")
cols = ["label", "postings_with", "employers_with", "share_postings", "share_employers"]
show = pc[pc["postings_with"] >= 20].nlargest(8, "gap")[cols].copy()
show["share_postings"] = (show["share_postings"] * 100).round(1)
show["share_employers"] = (show["share_employers"] * 100).round(1)
print(show.to_string(index=False))
print("")

# the single most concentrated case
worst = pc[pc["postings_with"] >= 20].nlargest(1, "gap").iloc[0]
sub = cell[cell["cluster"] == worst["cluster"]]
who = sub.drop_duplicates("vacancy_id")["company"].value_counts().head(3)
print(f"take '{worst['label']}' — asked in {int(worst['postings_with'])} postings "
      f"but by only {int(worst['employers_with'])} employers:")
for k, v in who.items():
    print(f"    {str(k)[:40]:<42} {v:>4} of those postings")
