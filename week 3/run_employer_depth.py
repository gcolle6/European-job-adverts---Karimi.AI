"""How much do high-volume employers shape the aggregate results?

The draft ranks employer identity as the largest single effect on one piece of
evidence — that counting employers once instead of adverts halves the apparent
industry effect. That is a strong claim resting on a thin measurement, so this
opens it up.

Five questions, each with its own control:

  1. **How concentrated is posting?** A long tail is normal; a handful of firms
     owning half the corpus is not, and only the second threatens an aggregate.

  2. **Are high-volume employers repeating themselves, or just posting more?**
     These have opposite consequences. Twenty adverts that differ carry twenty
     observations; twenty copies of one template carry one. Measured as how
     similar an employer's own adverts are to each other, against a control of
     same-sized groups of adverts drawn from DIFFERENT employers — without that
     control a high similarity would just mean "adverts are similar".

  3. **Do they ask for different things?** Repetition distorts weight; different
     content distorts direction. They are separate failures.

  4. **What actually moves when their weight is removed?** Four treatments, from
     untouched to employer-as-unit, on the headline the study turns on.

  5. **Which single employers carry a published number?** Naming them is the
     point: a finding that survives losing any one firm is different from one
     that does not.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import config, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()
rng = np.random.default_rng(20260914)

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

post = base.drop_duplicates("vacancy_id")
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]

# ---------------------------------------------------------------- 1 ---------
print("=" * 92)
print("1. HOW CONCENTRATED IS POSTING?")
print("=" * 92)
counts = post["company"].value_counts()
n_ads, n_emp = len(post), len(counts)
print(f"  {n_ads:,} adverts from {n_emp:,} employers — {n_ads/n_emp:.1f} per employer on average")
print(f"  median employer posts {int(counts.median())}, the largest posts {int(counts.max())}")
print("")
for frac in (0.01, 0.05, 0.10, 0.25):
    k = max(1, int(round(n_emp * frac)))
    print(f"  top {frac:>4.0%} of employers ({k:>4}) write "
          f"{counts.head(k).sum()/n_ads:>6.1%} of adverts")
s = np.sort(counts.to_numpy())
gini = (2 * np.arange(1, len(s) + 1) - len(s) - 1).dot(s) / (len(s) * s.sum())
print(f"\n  Gini coefficient of adverts per employer: {gini:.3f}")
print("  (0 = every employer posts the same number, 1 = one employer posts everything)")
print("")
print("  the ten largest posters:")
for name, c in counts.head(10).items():
    fam = post.loc[post["company"] == name, "macro_function"].mode().iat[0]
    ind = post.loc[post["company"] == name, "company_industry"].mode().iat[0]
    print(f"    {str(name)[:30]:<32}{c:>5} adverts  {c/n_ads:>5.1%} of corpus   {fam} / {ind[:26]}")

# ---------------------------------------------------------------- 2 ---------
print("")
print("=" * 92)
print("2. REPEATING THEMSELVES, OR JUST POSTING MORE?")
print("=" * 92)
sets_by_ad = j.groupby("vacancy_id")["cluster"].apply(frozenset)
ad_company = dict(zip(post["vacancy_id"], post["company"]))


def jac(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def self_similarity(ads, pairs=300):
    ads = [sets_by_ad[a] for a in ads if a in sets_by_ad.index]
    if len(ads) < 2:
        return np.nan
    out = []
    for _ in range(pairs):
        i, k = rng.integers(0, len(ads), 2)
        if i != k:
            out.append(jac(ads[i], ads[k]))
    return float(np.mean(out)) if out else np.nan


big = counts[counts >= 20].index.tolist()
rows = []
allads = list(sets_by_ad.index)
for name in big:
    ads = post.loc[post["company"] == name, "vacancy_id"].tolist()
    own = self_similarity(ads)
    # control: same number of adverts, each from a different employer
    ctl_ads = list(rng.choice(allads, size=min(len(ads), 60), replace=False))
    ctl = self_similarity(ctl_ads)
    rows.append({"company": name, "adverts": len(ads),
                 "own_similarity": own, "control": ctl})
d2 = pd.DataFrame(rows).dropna()
d2["excess"] = (d2["own_similarity"] - d2["control"]).round(3)
print(f"  employers with 20+ adverts: {len(d2)}")
print(f"  their adverts resemble each other : {d2['own_similarity'].mean():.3f}")
print(f"  random adverts resemble each other: {d2['control'].mean():.3f}")
print(f"  EXCESS self-similarity            : {d2['excess'].mean():+.3f}")
print("")
print("  the ten most template-driven employers:")
print(d2.nlargest(10, "excess")[["company", "adverts", "own_similarity", "control", "excess"]]
      .round(3).to_string(index=False))
print("")
print("  and the ten whose adverts genuinely differ:")
print(d2.nsmallest(6, "excess")[["company", "adverts", "own_similarity", "control", "excess"]]
      .round(3).to_string(index=False))

# ---------------------------------------------------------------- 3 ---------
print("")
print("=" * 92)
print("3. DO HIGH-VOLUME EMPLOYERS ASK FOR DIFFERENT THINGS?")
print("=" * 92)
post["volume"] = post["company"].map(counts)
post["band"] = pd.cut(post["volume"], [0, 2, 10, 50, 10**6],
                      labels=["1-2 adverts", "3-10", "11-50", "50+"])
jb = j.merge(post[["vacancy_id", "band"]], on="vacancy_id", how="left")
tot = jb.groupby("band", observed=True)["vacancy_id"].nunique()
share = (jb.groupby(["band", "cluster"], observed=True)["vacancy_id"].nunique()
         .unstack(0).div(tot, axis=1))
lab = dict(zip(named["cluster"], named["label"]))
share = share.dropna()
share["gap"] = share["50+"] - share["1-2 adverts"]
print("  adverts per band: " + ", ".join(f"{k} {v:,}" for k, v in tot.items()))
print("")
print("  groups most OVER-asked by high-volume employers:")
for cid, r in share.nlargest(7, "gap").iterrows():
    print(f"    {str(lab.get(cid,'?'))[:36]:<38} 50+: {r['50+']:>6.1%}   1-2: {r['1-2 adverts']:>6.1%}   {r['gap']:+.1%}")
print("\n  groups most UNDER-asked by them:")
for cid, r in share.nsmallest(7, "gap").iterrows():
    print(f"    {str(lab.get(cid,'?'))[:36]:<38} 50+: {r['50+']:>6.1%}   1-2: {r['1-2 adverts']:>6.1%}   {r['gap']:+.1%}")
print(f"\n  mean absolute gap across all groups: {share['gap'].abs().mean():.2%}")
print(f"  requirements per advert: " +
      ", ".join(f"{k} {v:.1f}" for k, v in
                jb.groupby('band', observed=True).size().div(tot).items()))

# ---------------------------------------------------------------- 4 ---------
print("")
print("=" * 92)
print("4. WHAT MOVES WHEN THEIR WEIGHT IS REMOVED?")
print("=" * 92)


def h1(frame, unit="vacancy_id"):
    prof = var.cell_profiles(asg, frame, exclude=drop, unit=unit)
    a = var.index_for(prof, "SALES_BD")["js"]
    b = var.index_for(prof, "SOFTWARE_DATA")["js"]
    return a, b, a / b


treatments = []
treatments.append(("every advert counts", reqs, "vacancy_id"))
for cap in (25, 10, 5):
    keep = (post.sort_values("vacancy_id").groupby("company").head(cap)["vacancy_id"])
    treatments.append((f"each employer capped at {cap}", reqs[reqs["vacancy_id"].isin(set(keep))], "vacancy_id"))
top10 = set(counts.head(10).index)
treatments.append(("ten largest employers removed",
                   reqs[~reqs["company"].isin(top10)], "vacancy_id"))
treatments.append(("each employer counts once", reqs, "company"))

for name, frame, unit in treatments:
    a, b, r = h1(frame, unit)
    n = frame["vacancy_id"].nunique()
    print(f"  {name:<32} sales {a:.4f}  software {b:.4f}  ratio {r:.3f}   ({n:,} adverts)")

# ---------------------------------------------------------------- 5 ---------
print("")
print("=" * 92)
print("5. DOES ANY SINGLE EMPLOYER CARRY THE RESULT?")
print("=" * 92)
base_ratio = h1(reqs)[2]
print(f"  with everyone: {base_ratio:.3f}")
loo = []
for name in counts.head(15).index:
    _, _, r = h1(reqs[reqs["company"] != name])
    loo.append({"employer removed": str(name)[:28], "adverts": int(counts[name]),
                "ratio": round(r, 3), "shift": round(r - base_ratio, 3)})
d5 = pd.DataFrame(loo).sort_values("shift")
print(d5.to_string(index=False))
print(f"\n  largest single-employer shift: {d5['shift'].abs().max():.3f}")
print(f"  the ratio stays above 1 in every case: "
      f"{bool((d5['ratio'] > 1).all())}")

d2.to_csv(W3 + r"\employer_templates.csv", index=False, encoding="utf-8")
d5.to_csv(W3 + r"\employer_leave_one_out.csv", index=False, encoding="utf-8")
print(f"\ntotal {time.time()-t0:.0f}s")
