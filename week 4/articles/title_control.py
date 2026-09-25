"""Hold the job title fixed and ask whether industry still moves the requirements.

The published index holds `macro_function` fixed — every software and data role
pooled. If industries advertise different *jobs* rather than asking different
things of the same job, part of that index is a role-mix effect and not an
industry effect at all.

Four titles have enough adverts in three or more industries to test it, at cells
of 10 to 40 adverts. That is far below the 300–5,200 the published index runs on,
and small cells look further apart than large ones even with identical true
profiles, so the within-title figure cannot be read against 0.307.

The comparison is therefore built to be like-for-like: the same industries, and
the pooled corpus subsampled to the same cell size, averaged over repeated draws.
What that isolates is the only thing at issue — whether fixing the title changes
the distance, holding everything else the way the title run has it.
"""
import itertools
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import config, data, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"

DRAWS = 40
MIN_CELL = 10
SEED = 20260925

reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(W3 + r"\phrase_clusters_corrected.parquet")
alias = pd.read_csv(W3 + r"\alias_table_final.csv")
amap = dict(zip(alias["cluster"], alias["merged_into"]))
asg["cluster"] = asg["cluster"].map(lambda c: amap.get(c, c))
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = {amap.get(c, c) for c in
        set(named.loc[named["boilerplate"] == True, "cluster"]) |
        set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])}

post = data.build_analysis_base().df.drop_duplicates("vacancy_id")
post = post[post["company_industry"].isin(config.PAIRED_INDUSTRIES)]
reqs = reqs.merge(post[["vacancy_id", "title_norm", "macro_function",
                        "company_industry"]].rename(columns={
                            "macro_function": "_mf", "company_industry": "_ci"}),
                  on="vacancy_id", how="inner")
for a, b in (("_mf", "macro_function"), ("_ci", "company_industry")):
    if b not in reqs.columns:
        reqs[b] = reqs[a]

link = asg[["phrase_norm", "cluster"]]


def profile(ids):
    """Share of these adverts asking for each group."""
    j = reqs[reqs["vacancy_id"].isin(ids)].merge(link, on="phrase_norm", how="left")
    j["cluster"] = j["cluster"].fillna(-1).astype(int)
    j = j[(j["cluster"] != -1) & (~j["cluster"].isin(drop))]
    n = j["vacancy_id"].nunique()
    return (j.groupby("cluster")["vacancy_id"].nunique() / n) if n else None


def mean_pairwise(groups):
    keys = sorted(set().union(*[set(g.index) for g in groups]))
    mats = [g.reindex(keys).fillna(0).to_numpy() for g in groups]
    return float(np.mean([var._js_distance(a, b)
                          for a, b in itertools.combinations(mats, 2)]))


rng = np.random.default_rng(SEED)
cnt = post.groupby(["title_norm", "company_industry"]).size()
ok = cnt[cnt >= MIN_CELL].groupby("title_norm").size()
titles = ok[ok >= 3].index.tolist()

print(f"{'title':30} {'family':9} {'ind':>4} {'n':>4} {'fixed':>7} {'pooled':>7} {'ratio':>6}")
rows = []
for t in titles:
    inds = cnt[t][cnt[t] >= MIN_CELL].index.tolist()
    sub = post[(post["title_norm"] == t) & (post["company_industry"].isin(inds))]
    fam = sub["macro_function"].mode()[0]
    n = int(sub.groupby("company_industry").size().min())

    # fixed title: one profile per industry, equalised to the smallest cell
    fixed = []
    for _ in range(DRAWS):
        ps = []
        for ind in inds:
            ids = sub[sub["company_industry"] == ind]["vacancy_id"].to_numpy()
            p = profile(rng.choice(ids, n, replace=False))
            if p is not None:
                ps.append(p)
        if len(ps) > 1:
            fixed.append(mean_pairwise(ps))

    # same industries, same family, same cell size — but any title
    pool = post[(post["macro_function"] == fam) & (post["company_industry"].isin(inds))]
    pooled = []
    for _ in range(DRAWS):
        ps = []
        for ind in inds:
            ids = pool[pool["company_industry"] == ind]["vacancy_id"].to_numpy()
            p = profile(rng.choice(ids, n, replace=False))
            if p is not None:
                ps.append(p)
        if len(ps) > 1:
            pooled.append(mean_pairwise(ps))

    f, g = float(np.mean(fixed)), float(np.mean(pooled))
    rows.append((t, fam, len(inds), n, f, g))
    print(f"{t[:30]:30} {fam[:9]:9} {len(inds):4} {n:4} {f:7.3f} {g:7.3f} {f/g:6.2f}")

print()
r = np.mean([x[4] / x[5] for x in rows])
print(f"mean ratio fixed/pooled: {r:.2f}")
print("  1.00 would mean fixing the title changes nothing — the whole distance is")
print("       industry asking different things of the same job")
print("  0.00 would mean the distance was entirely role mix")
