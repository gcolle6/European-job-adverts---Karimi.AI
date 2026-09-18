"""The variance index: how far a function's requirement profile moves across industries.

Week 2 answered a weaker version of this by *counting* groups above a shell
threshold. A count is threshold-dependent by construction — a group one point
below the cut-off contributes nothing and one point above contributes a whole
unit — so the headline moved with an arbitrary choice. This is the continuous
version.

**Profiles are built from posting shares, never from requirement counts.** Week 1
misses ~19.5% of requirements and misses them unevenly: long-segment exposure is
4.4% of software segments against 2.4% of sales, which is the exact comparison
H1 turns on. "What share of adverts asked for this group" is invariant to
under-counting within an advert; "how many requirements did this advert have" is
not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

# Resampling settings. Fixed here, before results, like every other threshold.
BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 20260911


def cell_profiles(assigned: pd.DataFrame, reqs: pd.DataFrame,
                  exclude: set[int] | None = None,
                  unit: str = "vacancy_id",
                  factor: str = "company_industry",
                  levels: list | None = None) -> pd.DataFrame:
    """Share of each cell's adverts that ask for each group.

    ``unit='company'`` counts each employer once per cell instead of each
    advert, which is the employer-weighted reading. It is not a robustness
    check — it moved the H1 headline from 1.50x to 1.06x — so both are primary
    and the caller runs each.
    """
    exclude = exclude or set()
    j = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    j["cluster"] = j["cluster"].fillna(-1).astype(int)
    j = j[(j["cluster"] != -1) & (~j["cluster"].isin(exclude))]
    keep = levels if levels is not None else (
        config.PAIRED_INDUSTRIES if factor == "company_industry" else None)
    if keep is not None:
        j = j[j[factor].isin(keep)]

    denom = j.groupby(["macro_function", factor])[unit].nunique()
    hits = j.groupby(["macro_function", factor, "cluster"])[unit].nunique()
    out = hits.rename("with").reset_index().merge(
        denom.rename("total").reset_index(), on=["macro_function", factor])
    out["share"] = out["with"] / out["total"]
    return out.rename(columns={factor: "level"})


def _matrix(profiles: pd.DataFrame, function: str) -> tuple[np.ndarray, list[str]]:
    """Cells x groups share matrix for one function, missing groups as zero."""
    sub = profiles[profiles["macro_function"] == function]
    wide = sub.pivot_table(index="level", columns="cluster",
                           values="share", fill_value=0.0)
    return wide.to_numpy(dtype=float), list(wide.index)


def _js_distance(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon distance between two L1-normalised profiles.

    Normalising each cell to sum to 1 is what removes advert verbosity: a cell
    whose adverts simply list more requirements would otherwise read as more
    distinctive when it is only wordier. JS is symmetric, bounded in [0, 1] with
    a base-2 log, and — unlike KL — defined when a group is absent from one
    cell, which happens constantly here.
    """
    p = p / p.sum() if p.sum() else p
    q = q / q.sum() if q.sum() else q
    m = 0.5 * (p + q)
    with np.errstate(divide="ignore", invalid="ignore"):
        kl_pm = np.nansum(np.where(p > 0, p * np.log2(p / m), 0.0))
        kl_qm = np.nansum(np.where(q > 0, q * np.log2(q / m), 0.0))
    return float(np.sqrt(max(0.5 * (kl_pm + kl_qm), 0.0)))


def _cosine_distance(p: np.ndarray, q: np.ndarray) -> float:
    n = np.linalg.norm(p) * np.linalg.norm(q)
    return float(1.0 - (p @ q) / n) if n else 0.0


def index_for(profiles: pd.DataFrame, function: str) -> dict:
    """Mean pairwise distance between a function's cell profiles.

    Both metrics are returned. If they order the two functions differently, that
    disagreement is the finding and neither should be quoted alone.
    """
    mat, cells = _matrix(profiles, function)
    if len(mat) < 2:
        return {"function": function, "n_cells": len(mat), "js": np.nan, "cosine": np.nan}
    js, cos = [], []
    for i in range(len(mat)):
        for k in range(i + 1, len(mat)):
            js.append(_js_distance(mat[i], mat[k]))
            cos.append(_cosine_distance(mat[i], mat[k]))
    return {"function": function, "n_cells": len(mat), "n_groups": mat.shape[1],
            "js": float(np.mean(js)), "cosine": float(np.mean(cos)),
            "js_min": float(np.min(js)), "js_max": float(np.max(js))}


def bootstrap(assigned: pd.DataFrame, reqs: pd.DataFrame,
              exclude: set[int] | None = None, unit: str = "vacancy_id",
              draws: int = BOOTSTRAP_DRAWS, equalise: int | None = None,
              factor: str = "company_industry", levels: list | None = None) -> pd.DataFrame:
    """Resample adverts within each cell and recompute the index.

    **This exists because noise inflates distance.** Two cells of 300 adverts
    look further apart than two of 3,000 even with identical true profiles, and
    cell sizes here run from ~300 to ~5,200 — so the raw index partly measures
    how small the cells are. That bias does not cancel between functions.

    ``equalise=n`` resamples every cell to the same ``n`` adverts, which is the
    direct test: **a software/sales difference that disappears under equalising
    was a difference in cell size, not in the labour market.**
    """
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    j = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    j["cluster"] = j["cluster"].fillna(-1).astype(int)
    exclude = exclude or set()
    j = j[(j["cluster"] != -1) & (~j["cluster"].isin(exclude))]
    keep = levels if levels is not None else (
        config.PAIRED_INDUSTRIES if factor == "company_industry" else None)
    if keep is not None:
        j = j[j[factor].isin(keep)]

    # one row per (cell, unit, cluster) is all the index needs
    slim = j[["macro_function", factor, unit, "cluster"]].drop_duplicates()
    cells = {k: g for k, g in slim.groupby(["macro_function", factor])}
    units = {k: g[unit].unique() for k, g in cells.items()}

    rows = []
    for draw in range(draws):
        parts = []
        for key, ids in units.items():
            n = equalise or len(ids)
            pick = rng.choice(ids, size=n, replace=True)
            counts = pd.Series(pick).value_counts()
            g = cells[key]
            rep = g[g[unit].isin(counts.index)].copy()
            rep["w"] = rep[unit].map(counts)
            agg = rep.groupby("cluster")["w"].sum() / n
            parts.append(pd.DataFrame({
                "macro_function": key[0], "level": key[1],
                "cluster": agg.index, "share": agg.to_numpy()}))
        prof = pd.concat(parts, ignore_index=True)
        for fn in prof["macro_function"].unique():
            r = index_for(prof, fn)
            r["draw"] = draw
            rows.append(r)
    return pd.DataFrame(rows)


def summarise(boot: pd.DataFrame) -> pd.DataFrame:
    """Point estimate and a 95% interval per function, for both metrics."""
    out = []
    for fn, g in boot.groupby("function"):
        row = {"function": fn, "n_cells": int(g["n_cells"].iloc[0]), "draws": len(g)}
        for m in ("js", "cosine"):
            row[f"{m}_mean"] = round(float(g[m].mean()), 4)
            row[f"{m}_lo"] = round(float(g[m].quantile(0.025)), 4)
            row[f"{m}_hi"] = round(float(g[m].quantile(0.975)), 4)
        out.append(row)
    return pd.DataFrame(out)


def ratio_interval(boot: pd.DataFrame, numerator: str = "SALES_BD",
                   denominator: str = "SOFTWARE_DATA", metric: str = "js") -> dict:
    """The sales:software ratio with an interval, paired within each draw.

    Pairing matters: the two functions are resampled together, so a draw where
    both happen high cancels. Taking the ratio of two independently-summarised
    means would overstate the uncertainty and hide a real difference.
    """
    a = boot[boot["function"] == numerator].set_index("draw")[metric]
    b = boot[boot["function"] == denominator].set_index("draw")[metric]
    r = (a / b).dropna()
    return {"metric": metric, "ratio": round(float(r.mean()), 3),
            "lo": round(float(r.quantile(0.025)), 3),
            "hi": round(float(r.quantile(0.975)), 3),
            "p_ratio_above_1": round(float((r > 1).mean()), 3)}
