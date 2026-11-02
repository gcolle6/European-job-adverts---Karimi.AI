"""Group requirements whose cores mean the same, by embedding similarity.

    python "New project/group_requirements.py" --bands         # pairs per similarity band, to read
    python "New project/group_requirements.py" --assign 0.90   # write the groups at a threshold

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

* cores are compared only within the same head group — competence never
  merges with experience;
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
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import embed  # noqa: E402

OUT = HERE / "output"
ATOMS = OUT / "must_have_atoms.parquet"
CACHE = OUT / "core_embeddings.npz"
FROZEN = HERE / "test_sets.json"
BLOCK = 2048
SEED = 20261101


_TOKEN = re.compile(r"[\w+#./-]+")
# Credential words are names wherever they stand: `Master's degree` and
# `Bachelor degree` sit at cosine 0.95 and are different requirements. A closed set.
_CREDENTIALS = {"bachelor", "master", "phd", "msc", "bsc", "mba", "ma", "ba", "graduate",
                "undergraduate", "postgraduate", "doctorate", "doctoral", "diploma", "hbo", "wo",
                "mbo", "associate", "bac", "licence", "license", "certificate", "certification"}


def names(core: str) -> frozenset[str]:
    """The proper names, acronyms and numbers of a core, plural- and case-free.

    The embedding places `degree in Computer Science` and `degree in Computer
    Engineering` at cosine 0.95, and `STP` next to `STL`: one different name is
    one different requirement, however close the rest. A token is a name when
    it holds a digit or a capital anywhere but the start of the first word.
    """
    out = set()
    for i, tok in enumerate(_TOKEN.findall(core)):
        if re.sub(r"[^\w]", "", tok.lower()).rstrip("s") in _CREDENTIALS:
            out.add(re.sub(r"[^\w]", "", tok.lower()).rstrip("s"))
            continue
        if any(ch.isdigit() for ch in tok) or any(ch.isupper() for ch in (tok[1:] if i == 0 else tok)):
            t = re.sub(r"[^\w+#]", "", tok.lower())
            out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return frozenset(out)


def cores(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (head group, core), with its occurrence count."""
    g = df.groupby(["req_head_group", "req_core"]).size().rename("n").reset_index()
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
    dev_cores = set(zip(df[~df.posting_id.isin(hold)].req_head_group, df[~df.posting_id.isin(hold)].req_core))
    rng = random.Random(SEED)
    pairs = collections.defaultdict(list)
    for g, sub in c.groupby("req_head_group"):
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
    for g, sub in c.groupby("req_head_group"):
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
    m = dict(zip(zip(c.req_head_group, c.req_core), c.req_group_core))
    df = df.assign(req_group_core=[m.get((g, x), x) for g, x in zip(df.req_head_group, df.req_core)])
    # A core with no frame noun names the same demand as the competence with
    # that core: `Communication` and `communication skills`, `Python` and
    # `Python skills`. Joined only on an identical group core, never by
    # similarity across head groups.
    comp = set(df.loc[df.req_head_group == "competence", "req_group_core"].str.casefold())
    bare = (df.req_head_group == "") & df.req_group_core.str.casefold().isin(comp)
    head = df.req_head_group.where(~bare, "competence")
    df["req_group"] = np.where(head != "", head + ": " + df.req_group_core.str.casefold(),
                               df.req_group_core.str.casefold())
    return df


def main() -> None:
    df = pd.read_parquet(ATOMS)
    c = cores(df)
    print(f"{len(c):,} distinct (head group, core) pairs")
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
