"""The artefact, built small, on data already in hand.

The proposal is a role map with two axes - other roles, and the same role in
other industries. Both are computable today on the 25,800-posting base, for the
roles deep enough to carry a profile. Building it on 39 roles proves the method
before anyone is asked for 500,000 postings, and a prototype is a better thing to
put in front of a data owner than a plan.

What it computes, all from one representation (a role's profile = the share of
its adverts asking for each requirement group):

* **nearest roles**, by overlap distance - `1 - sum(min(p, q))` on L1-normalised
  profiles, which reads as "how much of the list changes" and ranks identically
  to Jensen-Shannon (Spearman -0.987);
* **core and shell** per role - what it asks for everywhere against what belongs
  to one industry;
* **the same role across industries** - the axis Nesta's map does not have.

Guards, each paid for earlier:

* a role needs adverts AND **employers**. 50 adverts from 2 companies is a
  template, not a role - `Empathy` was 90% one employer;
* distance is computed on profiles, while roles come from title strings, so the
  two axes stay independent (see 3.3 on circularity);
* seniority is stripped into its own field rather than splitting a role in two.

Run: python prototype_map.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from karimi import data  # noqa: E402
from title_cleanup import GENDER, BRACKETS, SENIORITY, TAIL, tidy  # noqa: E402

CLUSTERS = HERE.parent / "week 2" / "output" / "phrase_clusters.parquet"
REQS = HERE.parent / "week 1" / "output" / "requirements.parquet"
NAMED = HERE.parent / "week 2" / "output" / "cluster_dictionary_named.csv"

MIN_ADVERTS = 50
MIN_EMPLOYERS = 15          # a role is not one company's template
MIN_INDUSTRY_ADVERTS = 25   # for the per-industry axis
CORE_BAND = 0.35            # |lift - 1| <= this, as in the published core rule
SHELL_LIFT = 1.75


def clean_title(s: str) -> str:
    for rx in (GENDER, BRACKETS, SENIORITY):
        s = tidy(rx.sub(" ", s))
    head = tidy(TAIL.sub("", s))
    return head if len(head.split()) >= 2 else s


def overlap_distance(P: np.ndarray) -> np.ndarray:
    """1 - sum(min(p, q)), pairwise. 0 = identical list, 1 = nothing shared."""
    n = len(P)
    D = np.zeros((n, n))
    for i in range(n):
        D[i] = 1.0 - np.minimum(P[i], P).sum(axis=1)
    np.fill_diagonal(D, 0.0)
    return D


def main() -> None:
    b = data.build_analysis_base().df
    b["role"] = b["job_title"].fillna("").str.lower().map(clean_title)

    reqs = pd.read_parquet(REQS)
    clu = pd.read_parquet(CLUSTERS)[["phrase_norm", "cluster"]].drop_duplicates("phrase_norm")
    r = reqs.merge(clu, on="phrase_norm", how="left")
    r = r[r["cluster"].notna()]
    r["cluster"] = r["cluster"].astype(int)
    r = r[r["cluster"] >= 0]
    r = r.merge(b[["vacancy_id", "role"]], on="vacancy_id", how="left")

    names = {}
    if NAMED.exists():
        nd = pd.read_csv(NAMED)
        col = next((c for c in nd.columns if c.lower() in ("name", "label", "cluster_name")), None)
        if col:
            names = dict(zip(nd["cluster"], nd[col]))

    # Which roles are deep enough to carry a profile?
    g = b.groupby("role").agg(adverts=("vacancy_id", "nunique"),
                              employers=("company", "nunique"),
                              function=("macro_function", lambda s: s.mode()[0]))
    roles = g[(g.adverts >= MIN_ADVERTS) & (g.employers >= MIN_EMPLOYERS)]
    roles = roles.sort_values("adverts", ascending=False)
    print(f"{len(b):,} postings -> {b['role'].nunique():,} cleaned titles")
    print(f"roles with >={MIN_ADVERTS} adverts and >={MIN_EMPLOYERS} employers: "
          f"{len(roles)}  ({roles.adverts.sum() / len(b):.1%} of postings)\n")
    print(roles.head(45).to_string())

    # Profile: share of a role's adverts that ask for each group.
    sub = r[r["role"].isin(roles.index)]
    n_ad = sub.groupby("role")["vacancy_id"].nunique()
    share = (sub.drop_duplicates(["role", "vacancy_id", "cluster"])
             .groupby(["role", "cluster"]).size()
             .unstack(fill_value=0).div(n_ad, axis=0))
    share = share.loc[roles.index]
    P = share.to_numpy()
    P = P / P.sum(axis=1, keepdims=True)

    D = overlap_distance(P)
    print(f"\n\n{'=' * 78}\nNEAREST ROLES  (overlap distance: 0 = same list, "
          f"1 = nothing shared)\n{'=' * 78}")
    for i, name in enumerate(share.index):
        near = np.argsort(D[i])[1:4]
        bits = ", ".join(f"{share.index[j]} {D[i, j]:.2f}" for j in near)
        print(f"  {name:<34} {roles.function.iloc[i][:4]:<5} -> {bits}")

    # Core and shell, against the role's own function as the benchmark.
    print(f"\n\n{'=' * 78}\nCORE vs SHELL for four roles\n{'=' * 78}")
    for fn in ("SOFTWARE_DATA", "SALES_BD"):
        idx = [i for i, nm in enumerate(share.index) if roles.function.iloc[i] == fn]
        if not idx:
            continue
        base = P[idx].mean(axis=0)
        for i in idx[:2]:
            lift = np.divide(P[i], base, out=np.zeros_like(P[i]), where=base > 0)
            ok = share.iloc[i].to_numpy() >= 0.05
            core = [(share.columns[j], share.iloc[i, j]) for j in np.where(
                ok & (np.abs(lift - 1) <= CORE_BAND))[0]]
            shell = [(share.columns[j], share.iloc[i, j], lift[j]) for j in np.where(
                (lift >= SHELL_LIFT) & (share.iloc[i].to_numpy() >= 0.03))[0]]
            print(f"\n  {share.index[i].upper()}  ({fn})")
            print(f"    CORE  ({len(core)} groups travel):")
            for c, s in sorted(core, key=lambda t: -t[1])[:6]:
                print(f"      {s:>5.0%}  {names.get(c, f'cluster {c}')}")
            print(f"    SHELL ({len(shell)} groups are specific to it):")
            for c, s, lf in sorted(shell, key=lambda t: -t[2])[:6]:
                print(f"      {s:>5.0%}  {lf:>4.1f}x  {names.get(c, f'cluster {c}')}")

    # The axis Nesta does not have: one role, several industries.
    print(f"\n\n{'=' * 78}\nSAME ROLE, DIFFERENT INDUSTRY\n{'=' * 78}")
    # `r` ALREADY carries company_industry from requirements.parquet. Merging the
    # base again shadows it with _x/_y - the fourth time this trap has fired in
    # this project. Use the column that is already there.
    sub2 = r
    for role in share.index[:6]:
        rr = sub2[sub2["role"] == role]
        cnt = rr.groupby("company_industry")["vacancy_id"].nunique()
        cnt = cnt[cnt >= MIN_INDUSTRY_ADVERTS]
        if len(cnt) < 2:
            continue
        rr = rr[rr["company_industry"].isin(cnt.index)]
        na = rr.groupby("company_industry")["vacancy_id"].nunique()
        sh = (rr.drop_duplicates(["company_industry", "vacancy_id", "cluster"])
              .groupby(["company_industry", "cluster"]).size()
              .unstack(fill_value=0).div(na, axis=0))
        Q = sh.to_numpy()
        Q = Q / Q.sum(axis=1, keepdims=True)
        DD = overlap_distance(Q)
        iu = np.triu_indices(len(Q), 1)
        print(f"\n  {role.upper()}  ({len(cnt)} industries with >="
              f"{MIN_INDUSTRY_ADVERTS} adverts)")
        print(f"    mean distance between industry versions: {DD[iu].mean():.2f}"
              f"   (range {DD[iu].min():.2f}-{DD[iu].max():.2f})")
        a, bb = np.unravel_index(np.argmax(DD), DD.shape)
        print(f"    furthest apart: {sh.index[a]} vs {sh.index[bb]} "
              f"= {DD[a, bb]:.2f}")


if __name__ == "__main__":
    main()
