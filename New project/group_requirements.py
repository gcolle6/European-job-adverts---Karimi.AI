"""Group requirements whose cores mean the same, by embedding similarity.

    python "New project/group_requirements.py" --bands         # pairs per similarity band, to read
    python "New project/group_requirements.py" --assign 0.90   # write the groups at a threshold
    python "New project/group_requirements.py" --topic 0.80    # then the coarser topic level

Runs after `split_must_have.py`. The rules have already moved years, level,
head and qualifier into their own columns (`normalise_req.decompose`), so
what is embedded is the CORE alone — `SQL`, `CI/CD pipelines` — and grouping
cannot merge `3+ years of Python` with `Basic Python`: those differ in columns
the grouping never sees.

Decided 2026-11-01, and the order matters: rules separate attributes, the
embedding merges wordings no rule anticipates (`GitLab` / `Gitlab CI` /
`GitLab CI/CD`). The limits are the ones Week 2 measured: the model groups by
topic and can join different things (`Kommunikationsstärke` with `messaging
systems`), so

* cores are compared only within the same SPACE (`normalise_req.space`):
  language, education, or everything else. Until rules 0.3.0 it was the head
  group, so `Experience with Python` and `Knowledge of Python` were two
  groups; the user decided 2026-11-10 they are one, Python, with how it was
  asked kept in `req_head_group`;
* each core joins its most frequent neighbour above the threshold, ONE hop:
  no chains, so A~B and B~C never makes A~C;
* the threshold is chosen by reading pairs from `software_dev` postings
  (`--bands`), never from the holdout;
* text is embedded as written, cased: the model is cased, and lowercasing
  moved named entities into generic groups in Week 2.

Local model (`karimi.embed.DEFAULT_MODEL`); vectors cached in
`output/core_embeddings.npz`, so a rerun encodes only new cores.
"""

from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import embed  # noqa: E402
from karimi.normalise_req import names  # noqa: E402,F401  (shared with karimi_normalise)
from karimi.normalise_req import canon as normalise_canon  # noqa: E402

OUT = HERE / "output"
ATOMS = OUT / "must_have_atoms.parquet"
CACHE = OUT / "core_embeddings.npz"
FROZEN = HERE / "test_sets.json"
BLOCK = 2048
SEED = 20261101


def cores(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (space, core), with its occurrence count."""
    g = df.groupby(["req_space", "req_core"]).size().rename("n").reset_index()
    return g[g.req_core.str.strip() != ""].reset_index(drop=True)


def vectors(texts: list[str]) -> np.ndarray:
    info = embed.top_up_corpus(texts, CACHE)
    print(f"embeddings: {info}")
    phrases, vecs = embed.load_corpus(CACHE)
    idx = {p: i for i, p in enumerate(phrases)}
    v = vecs[[idx[t] for t in texts]].astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def nearest(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each row, its most similar OTHER row and the cosine."""
    best = np.full(len(v), -1, dtype=np.int64)
    sim = np.full(len(v), -1.0, dtype=np.float32)
    for s in range(0, len(v), BLOCK):
        m = v[s: s + BLOCK] @ v.T
        for k in range(m.shape[0]):
            m[k, s + k] = -1.0
        best[s: s + BLOCK] = m.argmax(1)
        sim[s: s + BLOCK] = m.max(1)
    return best, sim


def neighbours_above(v: np.ndarray, t: float) -> list[np.ndarray]:
    out = []
    for s in range(0, len(v), BLOCK):
        m = v[s: s + BLOCK] @ v.T
        for k in range(m.shape[0]):
            row = np.where(m[k] >= t)[0]
            out.append(row[row != s + k])
    return out


def bands(df: pd.DataFrame, c: pd.DataFrame, v: np.ndarray) -> None:
    hold = set(json.loads(FROZEN.read_text(encoding="utf-8"))["software_holdout"])
    dev_cores = set(zip(df[~df.posting_id.isin(hold)].req_space, df[~df.posting_id.isin(hold)].req_core))
    rng = random.Random(SEED)
    pairs = collections.defaultdict(list)
    for g, sub in c.groupby("req_space"):
        idx = sub.index.to_numpy()
        best, sim = nearest(v[idx])
        for k, i in enumerate(idx):
            j = idx[best[k]]
            if (g, c.req_core[i]) in dev_cores and c.req_core[i].lower() != c.req_core[j].lower()                     and names(c.req_core[i]) == names(c.req_core[j]):
                pairs[min(int(sim[k] * 20) / 20, 0.95)].append((g, c.req_core[i], c.req_core[j], sim[k]))
    for b in sorted(pairs):
        if b < 0.70:
            continue
        print(f"\n=== cosine {b:.2f}-{b + 0.05:.2f}: {len(pairs[b]):,} cores")
        for g, a, n_, s in rng.sample(pairs[b], min(25, len(pairs[b]))):
            print(f"   [{g or '-':10s}] {a[:45]:45s} ~ {n_[:45]}")


def assign(df: pd.DataFrame, c: pd.DataFrame, v: np.ndarray, t: float) -> pd.DataFrame:
    """Each core joins its most frequent neighbour at cosine >= t, one hop."""
    canon = c.req_core.copy()
    for g, sub in c.groupby("req_space"):
        idx = sub.index.to_numpy()
        nb = neighbours_above(v[idx], t)
        n = c.n.to_numpy()[idx]
        nm = [names(x) for x in c.req_core.to_numpy()[idx]]
        for k, i in enumerate(idx):
            cand = np.array([j for j in nb[k] if nm[j] == nm[k]], dtype=np.int64)
            if len(cand):
                j = cand[n[cand].argmax()]
                if n[j] > n[k] or (n[j] == n[k] and c.req_core[idx[j]] < c.req_core[i]):
                    canon[i] = c.req_core[idx[j]]
    c = c.assign(req_group_core=canon)
    # Two groups whose cores are one spelling apart are one group (rules 0.3.0):
    # `problem-solving` / `problem solving`, `data modelling` / `data modeling`,
    # `DevOps` / `devops`. The site's explorer listed them twice; the embedding
    # leaves some below 0.90 and `names` keeps capitalised spellings apart. The
    # group takes the commonest spelling.
    size = c.groupby(["req_space", "req_group_core"]).n.sum()
    form = {k: (k[0], normalise_canon(k[1])) for k in size.index}
    best: dict[tuple[str, str], tuple[int, str]] = {}
    for k, n_ in size.items():
        f = form[k]
        if f not in best or (n_, k[1]) > best[f]:
            best[f] = (int(n_), k[1])
    c = c.assign(req_group_core=[best[form[(s, g)]][1] for s, g in zip(c.req_space, c.req_group_core)])
    m = dict(zip(zip(c.req_space, c.req_core), c.req_group_core))
    df = df.assign(req_group_core=[m.get((g, x), x) for g, x in zip(df.req_space, df.req_core)])
    # `Python`, `Python skills`, `Experience with Python`: one space, so one
    # group by construction (rules 0.3.0); the label carries the space only
    # where there is one (`language: english`, `education: physics`).
    df["req_group"] = np.where(df.req_space != "", df.req_space + ": " + df.req_group_core.str.casefold(),
                               df.req_group_core.str.casefold())
    return df


def topics(df: pd.DataFrame, t: float) -> pd.DataFrame:
    """A second, coarser level: `req_topic`, the GROUPS joined at a lower threshold.

    Decided 2026-11-04 after two rounds of pairs: all 29 near misses at
    0.80-0.90 were judged the same by the labeller, who reads "same theme"
    (`risk` ~ `risk mitigation`), while `req_group` keeps "same requirement".
    The unit is the whole `req_group`, so the levels nest: every group sits in
    exactly one topic. Not its group cores: one group can hold several
    (`Python` / `python` fold by case, a bare core joins the competence with
    that core), and those went to different topics. Each group is embedded by
    its commonest wording, under the head its label carries.
    """
    units = pd.DataFrame({"req_group": df.req_group, "req_space": df.req_space,
                          "req_core": df.req_group_core})
    rep = units.groupby("req_group").agg(req_space=("req_space", "first"),
                                         req_core=("req_core", lambda s: s.value_counts().index[0]))
    g = units[["req_group"]].join(rep, on="req_group")
    c = cores(g)
    v = vectors(c.req_core.tolist())
    out = assign(g.assign(req_group_core=g.req_core), c, v, t)
    topic = dict(zip(g.req_group, out.req_group))
    return df.assign(req_topic=df.req_group.map(topic))


def main() -> None:
    df = pd.read_parquet(ATOMS)
    if "--topic" in sys.argv:
        t = float(sys.argv[sys.argv.index("--topic") + 1])
        out = topics(df, t)
        out.to_parquet(ATOMS, index=False)
        nest = out.groupby("req_group").req_topic.nunique().max()
        print(f"topic threshold {t}: groups {out.req_group.nunique():,} -> topics "
              f"{out.req_topic.nunique():,} (topics per group, max: {nest})")
        return
    c = cores(df)
    print(f"{len(c):,} distinct (space, core) pairs")
    v = vectors(c.req_core.tolist())
    if "--bands" in sys.argv:
        bands(df, c, v)
        return
    t = float(sys.argv[sys.argv.index("--assign") + 1])
    out = assign(df, c, v, t)
    out.to_parquet(ATOMS, index=False)
    print(f"threshold {t}: keys {df.req_key.nunique():,} -> groups {out.req_group.nunique():,}")


if __name__ == "__main__":
    main()
