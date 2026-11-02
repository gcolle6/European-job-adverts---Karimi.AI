"""Can our own adverts carry a career timeline?

A timeline "from junior to senior" needs two things the adverts may or may not
hold: a usable seniority field, and requirements that actually change along it.
This probes both before step 3 is designed around them.

1. years of experience asked, read from the requirement text, per seniority
   level - does "senior" mean more years, and how many;
2. for the deepest roles, how far the junior profile sits from the senior one,
   against the split-half noise floor (the control `distance_floor.py` showed is
   needed: without it sparsity alone reads as difference);
3. which requirement groups rise most from junior to senior - what the step up
   actually asks for.

Run: python seniority_probe.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from karimi import data  # noqa: E402
from advert_decoder import OUT, REQS, clean_title  # noqa: E402

LEVELS = ["Junior", "Mid-level", "Senior"]
MIN_PER_LEVEL = 25
N_DRAWS = 40
SEED = 20261022
# A number followed by a years word, in the corpus languages. Ranges ("3-5")
# take the lower bound, which is the stated minimum.
YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|–\s*\d{1,2})?\s*"
    r"(?:years?|yrs?|jahre?n?|ans?|anni|años|jaar|lat)\b", re.I)


def first_years(text: str) -> float:
    m = YEARS.search(text or "")
    if not m:
        return np.nan
    v = int(m.group(1))
    return float(v) if 0 < v <= 25 else np.nan


def profile(df: pd.DataFrame, n: int) -> np.ndarray:
    u = df.drop_duplicates(["vacancy_id", "cluster"])
    v = np.bincount(u["cluster"].to_numpy(), minlength=n).astype(float)
    return v / v.sum() if v.sum() else v


def dist(p, q) -> float:
    return 1.0 - np.minimum(p, q).sum()


def main() -> None:
    b = data.build_analysis_base().df
    b["role"] = b["job_title"].fillna("").str.lower().map(clean_title)
    b["years"] = b["must_have"].map(first_years)

    print("1. YEARS OF EXPERIENCE ASKED, by seniority field\n")
    t = b.groupby("seniority").agg(adverts=("vacancy_id", "size"),
                                   states_years=("years", lambda s: s.notna().mean()),
                                   median_years=("years", "median"),
                                   p25=("years", lambda s: s.quantile(.25)),
                                   p75=("years", lambda s: s.quantile(.75)))
    print(t.to_string(float_format=lambda x: f"{x:.2f}"))

    r = pd.read_parquet(REQS)
    clu = pd.read_parquet(OUT / "phrase_clusters.parquet")[["phrase_norm", "cluster"]]
    r = r.merge(clu.drop_duplicates("phrase_norm"), on="phrase_norm", how="left")
    r = r[r["cluster"].notna()]
    r["cluster"] = r["cluster"].astype(int)
    d = pd.read_csv(OUT / "cluster_dictionary_named.csv")
    mixed = set(d.loc[d["label"].eq("MIXED"), "cluster"])
    lab = dict(zip(d["cluster"], d["label"]))
    r = r[(r["cluster"] >= 0) & ~r["cluster"].isin(mixed)]
    # requirements.parquet has no seniority or role; take them from the base.
    r = r.merge(b[["vacancy_id", "role", "seniority"]], on="vacancy_id", how="inner")
    n_cl = int(r["cluster"].max()) + 1
    rng = np.random.default_rng(SEED)

    print("\n\n2. JUNIOR vs SENIOR profile, against the split-half noise floor\n")
    print(f"{'role':<34} {'jun':>4} {'sen':>4} {'floor':>6} {'jun-sen':>8} {'excess':>7}")
    rows = []
    for role, g in r.groupby("role"):
        n_lvl = g.groupby("seniority")["vacancy_id"].nunique()
        if n_lvl.get("Junior", 0) < MIN_PER_LEVEL or n_lvl.get("Senior", 0) < MIN_PER_LEVEL:
            continue
        J, S = g[g.seniority == "Junior"], g[g.seniority == "Senior"]
        dd = dist(profile(J, n_cl), profile(S, n_cl))
        fl = []
        for part in (J, S):
            v = part["vacancy_id"].unique()
            h = len(v) // 2
            for _ in range(N_DRAWS):
                sh = rng.permutation(v)
                fl.append(dist(profile(part[part.vacancy_id.isin(sh[:h])], n_cl),
                               profile(part[part.vacancy_id.isin(sh[h:2 * h])], n_cl)))
        f = float(np.mean(fl))
        rows.append((role, J, S))
        print(f"{role:<34} {n_lvl['Junior']:>4} {n_lvl['Senior']:>4} {f:>6.2f} "
              f"{dd:>8.2f} {dd - f:>+7.2f}")

    print("\n\n3. WHAT THE STEP UP ASKS FOR - groups rising most, junior -> senior\n")
    for role, J, S in rows[:4]:
        nj, ns = J.vacancy_id.nunique(), S.vacancy_id.nunique()
        sj = J.drop_duplicates(["vacancy_id", "cluster"]).groupby("cluster").size() / nj
        ss = S.drop_duplicates(["vacancy_id", "cluster"]).groupby("cluster").size() / ns
        both = pd.concat([sj.rename("jun"), ss.rename("sen")], axis=1).fillna(0)
        both["gain"] = both.sen - both.jun
        print(f"  {role.upper()}  ({nj} junior, {ns} senior adverts)")
        for c, x in both.sort_values("gain", ascending=False).head(5).iterrows():
            print(f"    +{x.gain:>5.0%}  {lab.get(c, c):<40} {x.jun:>4.0%} -> {x.sen:>4.0%}")
        for c, x in both.sort_values("gain").head(2).iterrows():
            print(f"    {x.gain:>+6.0%}  {lab.get(c, c):<40} {x.jun:>4.0%} -> {x.sen:>4.0%}")
        print()


if __name__ == "__main__":
    main()
