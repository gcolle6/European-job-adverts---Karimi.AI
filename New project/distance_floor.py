"""Is "changing industry costs more than changing role" real, or sparsity?

`prototype_map.py` found that a role's versions in two industries sit further
apart (mean 0.52) than that role sits from a neighbouring role (0.36). That would
be the headline of the whole tool, so it has to survive the obvious confound
first: **industry versions are built on fewer adverts**, and a smaller sample
makes any two profiles look further apart whether or not they differ.

This project has already paid for exactly this mistake once - companies with 15
adverts all piled against one edge because they could not mention as many things
as a 14,700-advert aggregate. Compare like with like, or sparsity decides.

The control is a **split-half noise floor**: take one role, in one industry,
split its adverts at random into two halves, and measure the distance between the
halves. Nothing differs between them except the draw, so whatever distance comes
back is pure noise at that sample size. A real effect has to clear it.

Run: python distance_floor.py
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

REQS = HERE.parent / "week 1" / "output" / "requirements.parquet"
CLUSTERS = HERE.parent / "week 2" / "output" / "phrase_clusters.parquet"
MIN_ADVERTS, MIN_EMPLOYERS, MIN_IND = 50, 15, 25
N_DRAWS = 40
SEED = 20261012


def clean_title(s: str) -> str:
    for rx in (GENDER, BRACKETS, SENIORITY):
        s = tidy(rx.sub(" ", s))
    head = tidy(TAIL.sub("", s))
    return head if len(head.split()) >= 2 else s


def profile(df: pd.DataFrame, n_cluster: int) -> np.ndarray:
    """Share of adverts asking for each group, L1-normalised."""
    u = df.drop_duplicates(["vacancy_id", "cluster"])
    v = np.bincount(u["cluster"].to_numpy(), minlength=n_cluster).astype(float)
    return v / v.sum() if v.sum() else v


def dist(p: np.ndarray, q: np.ndarray) -> float:
    return 1.0 - np.minimum(p, q).sum()


def main() -> None:
    b = data.build_analysis_base().df
    b["role"] = b["job_title"].fillna("").str.lower().map(clean_title)

    r = pd.read_parquet(REQS)
    clu = pd.read_parquet(CLUSTERS)[["phrase_norm", "cluster"]].drop_duplicates("phrase_norm")
    r = r.merge(clu, on="phrase_norm", how="left")
    r = r[r["cluster"].notna()]
    r["cluster"] = r["cluster"].astype(int)
    r = r[r["cluster"] >= 0]
    r = r.merge(b[["vacancy_id", "role"]], on="vacancy_id", how="left")
    n_cluster = int(r["cluster"].max()) + 1

    g = b.groupby("role").agg(a=("vacancy_id", "nunique"), e=("company", "nunique"))
    keep = g[(g.a >= MIN_ADVERTS) & (g.e >= MIN_EMPLOYERS)].index
    rng = np.random.default_rng(SEED)

    print(f"{'role':<34} {'ind.':>5} {'n/ind':>6} {'FLOOR':>7} {'INDUSTRY':>9} "
          f"{'excess':>7}")
    print("-" * 74)
    floors, inds, rows = [], [], []
    for role in keep:
        rr = r[r["role"] == role]
        cnt = rr.groupby("company_industry")["vacancy_id"].nunique()
        cnt = cnt[cnt >= MIN_IND]
        if len(cnt) < 2:
            continue

        # Industry distances, and the floor measured at the SAME sample size.
        per_ind, floor_d = {}, []
        for ind in cnt.index:
            sub = rr[rr["company_industry"] == ind]
            per_ind[ind] = profile(sub, n_cluster)
            vacs = sub["vacancy_id"].unique()
            half = len(vacs) // 2
            for _ in range(N_DRAWS):
                sh = rng.permutation(vacs)
                A = sub[sub["vacancy_id"].isin(sh[:half])]
                B = sub[sub["vacancy_id"].isin(sh[half:2 * half])]
                floor_d.append(dist(profile(A, n_cluster), profile(B, n_cluster)))

        names = list(per_ind)
        pair = [dist(per_ind[names[i]], per_ind[names[j]])
                for i in range(len(names)) for j in range(i + 1, len(names))]
        fl, idd = float(np.mean(floor_d)), float(np.mean(pair))
        floors.append(fl); inds.append(idd)
        rows.append((role, len(cnt), int(cnt.mean()), fl, idd, idd - fl))
        print(f"{role:<34} {len(cnt):>5} {int(cnt.mean()):>6} {fl:>7.2f} "
              f"{idd:>9.2f} {idd - fl:>+7.2f}")

    print("-" * 74)
    print(f"{'MEAN':<34} {'':>5} {'':>6} {np.mean(floors):>7.2f} "
          f"{np.mean(inds):>9.2f} {np.mean(inds) - np.mean(floors):>+7.2f}")
    print(f"\nindustry distance exceeds its own noise floor in "
          f"{sum(i > f for i, f in zip(inds, floors))}/{len(inds)} roles")

    # Where the excess sits is the finding, not its average.
    fn = b.groupby("role")["macro_function"].agg(lambda s: s.mode()[0])
    byfn: dict[str, list[float]] = {}
    for role, _, _, _, _, exc in rows:
        byfn.setdefault(str(fn.get(role, "?")), []).append(exc)
    print()
    for k, v in sorted(byfn.items()):
        print(f"  mean excess over floor, {k:<14} {np.mean(v):>+6.3f}  "
              f"({len(v)} roles)")
    if len(byfn) == 2:
        x, z = [float(np.mean(v)) for v in byfn.values()]
        print(f"  ratio: {max(x, z) / min(x, z):.1f}x")

    # Half the floor comes from sample size. State the comparison it licenses.
    print("\nREAD: a role-to-role distance of ~0.36 is computed on full samples "
          "(>=50 adverts),\nso it carries a much lower floor. The honest "
          "comparison is excess-over-floor,\nnot the raw numbers side by side.")


if __name__ == "__main__":
    main()
