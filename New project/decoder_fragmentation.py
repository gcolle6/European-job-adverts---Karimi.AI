"""Is "63% of requirements are UNUSUAL" the market, or the vocabulary?

`advert_decoder.py` reported that 62.9% of the requirements in an advert are
asked by fewer than 10% of comparable adverts. Reading the members raised a
specific suspicion: the 617 groups split one concept across several groups -
English alone sits in `English proficiency` x4, `English B2 level`, and more - so
a requirement can be universal while the exact group it lands in is rare. If so,
"unusual" measures fragmentation of the instrument, not anything about adverts.

Test: count a requirement as asked whenever a comparable advert asks for its
group OR any group whose centroid lies within cosine tau of it. At tau = 1.0 this
is the original reading. As tau falls, near-synonym groups pool. If the UNUSUAL
share collapses as tau falls, fragmentation was driving it.

⚠️ tau is NOT chosen here. Picking the tau that gives a pleasing number after
seeing it would be threshold-shopping; the curve is reported whole, and the
choice belongs to Decision 3 (granularity), made on other grounds.

A control rides along: pooling neighbours mechanically raises every share, so
the curve is also run with groups pooled to the same NUMBER of neighbours but
chosen at random. If random pooling moves the share as much as semantic pooling,
the drop is arithmetic, not synonymy.

Run: python decoder_fragmentation.py
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
from advert_decoder import (  # noqa: E402
    MIN_ADVERTS, MIN_EMPLOYERS, OUT, REQS, STANDARD, UNUSUAL, clean_title)

TAUS = [1.00, 0.95, 0.90, 0.85, 0.80, 0.75]
SEED = 20261020


def unusual_share(A: np.ndarray, roles: np.ndarray, M: np.ndarray) -> tuple[float, float]:
    """Leave-one-out verdict mix when group c counts any group in M[:, c].

    A: adverts x groups, boolean (asks for it). M: groups x groups, boolean
    neighbourhood. Returns (UNUSUAL share, STANDARD share) over every
    (advert, group-it-asks) pair.
    """
    hit = (A.astype(np.int32) @ M.astype(np.int32)) > 0      # advert covers c's neighbourhood
    uns = std = tot = 0
    for r in np.unique(roles):
        idx = roles == r
        n = idx.sum()
        cnt = hit[idx].sum(axis=0)                       # adverts in role covering c
        asked = A[idx]                                   # pairs we score
        share = (cnt[None, :] - 1) / (n - 1)             # minus itself: it covers c
        s = np.broadcast_to(share, asked.shape)[asked]
        uns += (s < UNUSUAL).sum()
        std += (s >= STANDARD).sum()
        tot += s.size
    return uns / tot, std / tot


def main() -> None:
    b = data.build_analysis_base().df
    b["role"] = b["job_title"].fillna("").str.lower().map(clean_title)
    g = b.groupby("role").agg(a=("vacancy_id", "nunique"), e=("company", "nunique"))
    roles_ok = g[(g.a >= MIN_ADVERTS) & (g.e >= MIN_EMPLOYERS)].index
    base = b[b["role"].isin(roles_ok)].set_index("vacancy_id")

    d = pd.read_csv(OUT / "cluster_dictionary_named.csv")
    mixed = set(d.loc[d["label"].eq("MIXED"), "cluster"])
    z = np.load(OUT / "cluster_centroids.npz")
    cids, C = z["cluster_ids"], z["centroids"]
    pos = {int(c): i for i, c in enumerate(cids)}

    r = pd.read_parquet(REQS)
    clu = pd.read_parquet(OUT / "phrase_clusters.parquet")[["phrase_norm", "cluster"]]
    r = r.merge(clu.drop_duplicates("phrase_norm"), on="phrase_norm", how="left")
    r = r[r["vacancy_id"].isin(base.index) & r["cluster"].notna()]
    r["cluster"] = r["cluster"].astype(int)
    r = r[r["cluster"].isin(pos) & ~r["cluster"].isin(mixed)]
    r = r.drop_duplicates(["vacancy_id", "cluster"])

    vac, vac_ix = pd.factorize(r["vacancy_id"])
    A = np.zeros((len(vac_ix), len(cids)), dtype=bool)
    A[vac, r["cluster"].map(pos).to_numpy()] = True
    roles = base.loc[vac_ix, "role"].to_numpy()

    CC = C @ C.T
    np.fill_diagonal(CC, 1.0)
    rng = np.random.default_rng(SEED)

    print(f"{len(vac_ix):,} adverts, {len(roles_ok)} roles, {len(cids)} groups\n")
    print(f"{'tau':>5} {'neighbours':>11} {'UNUSUAL':>9} {'STANDARD':>9}   "
          f"{'random pool, same size':>24}")
    for tau in TAUS:
        M = CC >= tau
        k = M.sum(axis=0)                           # neighbourhood size per group
        u, s = unusual_share(A, roles, M)
        # Control: same neighbourhood sizes, random members.
        R = np.eye(len(cids), dtype=bool)
        for c in range(len(cids)):
            extra = int(k[c]) - 1
            if extra > 0:
                others = rng.choice(np.delete(np.arange(len(cids)), c),
                                    size=extra, replace=False)
                R[others, c] = True
        ur, sr = unusual_share(A, roles, R)
        print(f"{tau:>5.2f} {k.mean():>11.1f} {u:>9.1%} {s:>9.1%}   "
              f"UNUSUAL {ur:>6.1%}  STANDARD {sr:>6.1%}")

    # The concrete cases that raised the suspicion.
    lab = dict(zip(d["cluster"], d["label"]))
    print("\nwhat pools with the cases from the demo, at tau 0.85:")
    for name in ("English B2 level", "Microsoft Excel", "Problem-solving mindset",
                 "Comfort with ambiguity"):
        hits = d.loc[d["label"].eq(name), "cluster"]
        if hits.empty:
            continue
        c = pos[int(hits.iloc[0])]
        nb = [lab.get(int(cids[j]), "?") for j in np.argsort(-CC[c])[1:7]
              if CC[c, j] >= 0.85]
        print(f"  {name:<26} -> {', '.join(nb) if nb else '(none)'}")


if __name__ == "__main__":
    main()
