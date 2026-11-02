"""Distinct strings do not saturate. Do concepts, and does coverage?

`saturation.py` found Heaps' beta = 0.855 on raw phrase strings - almost linear,
so the string list keeps growing with the corpus and never settles. That is the
wrong thing to measure, because the deliverable is not a string list: it is a set
of normalised groups, and what matters operationally is how much of a NEW advert
a vocabulary built on old adverts already covers.

Three curves, all held out so none of them scores itself:

1. distinct CONCEPTS (cluster ids) against postings - does the concept inventory
   settle where the string inventory does not?
2. occurrence COVERAGE - build the vocabulary on the first N postings, then
   measure what share of requirement occurrences in the REMAINING postings it
   already contains. This is the number that sizes the export;
3. the same coverage per macro_function, to see whether one function needs more
   data than the other.

Everything is factorised to integer codes first: membership on 210k object
strings is quadratic in practice and does not finish.

Run: python saturation2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")
REQS = ROOT / "week 1" / "output" / "requirements.parquet"
CLUSTERS = ROOT / "week 2" / "output" / "phrase_clusters.parquet"
SEED = 20261012
HOLDOUT = 0.25          # the last quarter of the shuffle is never trained on
STEPS = [0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75]


def curve(vac: np.ndarray, val: np.ndarray, label: str) -> None:
    """Held-out occurrence coverage as the training share of postings grows."""
    vac_codes, vac_uniq = pd.factorize(vac)
    val_codes, val_uniq = pd.factorize(val)

    n_total = len(vac_uniq)
    rng = np.random.default_rng(SEED)
    # rank[i] = position of posting i in the shuffle
    rank_of_posting = np.empty(n_total, dtype=np.int64)
    rank_of_posting[rng.permutation(n_total)] = np.arange(n_total)
    rank = rank_of_posting[vac_codes]

    n_train_max = int(n_total * (1 - HOLDOUT))
    is_test = rank >= n_train_max
    test_vals = val_codes[is_test]

    print(f"\n{label}")
    print(f"  {n_total:,} postings, {len(val_codes):,} occurrences, "
          f"{len(val_uniq):,} distinct, {len(test_vals):,} held out")
    print(f"  {'train postings':>15} {'distinct seen':>14} {'held-out coverage':>18}")
    for f in STEPS:
        n = int(round(f * n_total))
        if n >= n_train_max or n == 0:
            continue
        seen = np.zeros(len(val_uniq), dtype=bool)
        seen[val_codes[rank < n]] = True
        cov = seen[test_vals].mean()
        print(f"  {n:>15,} {int(seen.sum()):>14,} {cov:>17.1%}")


def main() -> int:
    reqs = pd.read_parquet(REQS)
    clu = pd.read_parquet(CLUSTERS)
    print("cluster file columns:", list(clu.columns))

    key = "phrase_norm" if "phrase_norm" in clu.columns else clu.columns[0]
    cid = next((c for c in ("cluster", "cluster_id", "group", "label")
                if c in clu.columns), None)
    if cid is None:
        print("no cluster column found", file=sys.stderr)
        return 1
    print(f"joining on {key!r}, cluster column {cid!r}")
    m = reqs.merge(clu[[key, cid]].drop_duplicates(key), on=key, how="left")
    print(f"occurrences with a cluster: {m[cid].notna().mean():.1%}")

    curve(m["vacancy_id"].to_numpy(), m["phrase_norm"].to_numpy(),
          "RAW STRINGS - all")

    # Noise (-1) is not a concept, so it is excluded rather than counted as one.
    a = m[m[cid].notna()].copy()
    a[cid] = a[cid].astype(int)
    a = a[a[cid] >= 0]
    curve(a["vacancy_id"].to_numpy(), a[cid].to_numpy(),
          "CONCEPTS - cluster ids, noise excluded")

    for fn, sub in m.groupby("macro_function"):
        curve(sub["vacancy_id"].to_numpy(), sub["phrase_norm"].to_numpy(),
              f"RAW STRINGS - {fn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
