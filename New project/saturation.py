"""How much data does a requirement vocabulary actually need?

A vocabulary grows sublinearly in the corpus: the first thousand adverts bring
almost all the common phrasings, and every thousand after that brings fewer new
ones. Heaps' law (V = K * N^beta) describes that, and beta says how fast the
return decays.

The question this answers is practical. The export we would ask Karimi for is
sized by how many postings the vocabulary needs, not by how many exist. If beta
is low, asking for 500k when 100k would do is a cost with no return.

Run: python saturation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")
REQS = ROOT / "week 1" / "output" / "requirements.parquet"
SEED = 20261012
# Draw the curve at these fractions of the posting base, plus a fine head where
# the curve bends most.
FRACTIONS = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40,
             0.50, 0.60, 0.70, 0.80, 0.90, 1.00]


def main() -> int:
    reqs = pd.read_parquet(REQS)
    print("columns:", list(reqs.columns))
    print("rows:", f"{len(reqs):,}")

    # Find the posting key and the phrase column without assuming names.
    id_col = next((c for c in ("vacancy_id", "posting_id", "job_id", "id")
                   if c in reqs.columns), None)
    phrase_col = next((c for c in ("phrase_norm", "phrase", "atom", "text")
                       if c in reqs.columns), None)
    if id_col is None or phrase_col is None:
        print("could not find id/phrase columns", file=sys.stderr)
        return 1
    print(f"using id={id_col!r} phrase={phrase_col!r}")

    df = reqs[[id_col, phrase_col]].dropna()
    postings = df[id_col].unique()
    rng = np.random.default_rng(SEED)
    postings = np.asarray(postings, dtype=object)[rng.permutation(len(postings))]
    n_total = len(postings)
    print(f"postings: {n_total:,}")

    order = {p: i for i, p in enumerate(postings)}
    df = df.assign(_rank=df[id_col].map(order))

    # For each unique phrase, the rank of the first posting that uses it. The
    # curve is then a cumulative count, which is exact rather than resampled.
    first_seen = np.sort(df.groupby(phrase_col)["_rank"].min().to_numpy())

    print()
    print(f"{'postings':>10} {'unique phrases':>16} {'new per 1k':>12}")
    pts = []
    prev_n = prev_v = 0
    for f in FRACTIONS:
        n = max(1, int(round(f * n_total)))
        v = int(np.searchsorted(first_seen, n, side="left"))
        rate = (v - prev_v) / max(1, (n - prev_n)) * 1000
        print(f"{n:>10,} {v:>16,} {rate:>12.0f}")
        pts.append((n, v))
        prev_n, prev_v = n, v

    # Heaps' law on the upper half, where the early transient has passed.
    tail = [(n, v) for n, v in pts if n >= 0.2 * n_total]
    ln_n = np.log([n for n, _ in tail])
    ln_v = np.log([v for _, v in tail])
    beta, ln_k = np.polyfit(ln_n, ln_v, 1)
    k = float(np.exp(ln_k))
    print()
    print(f"Heaps' law fit on the top 80%: V = {k:.2f} * N^{beta:.4f}")

    print()
    print(f"{'postings':>10} {'projected vocab':>17} {'x25,800':>10}")
    base_v = pts[-1][1]
    for n in (n_total, 50_000, 100_000, 200_000, 300_000, 500_000):
        v = k * n ** beta
        print(f"{n:>10,} {v:>17,.0f} {v / base_v:>10.2f}x")

    # The number that decides the ask: how many postings reach 90% of what the
    # full 500k would give?
    v500 = k * 500_000 ** beta
    for target in (0.80, 0.90, 0.95):
        n_needed = (target * v500 / k) ** (1 / beta)
        print(f"  {target:.0%} of the 500k vocabulary is reached at "
              f"{n_needed:,.0f} postings ({n_needed / 500_000:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
