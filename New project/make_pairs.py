"""Draw the blind pair sample that measures whether the two normalisations are right.

    python "New project/make_pairs.py"            # write validation/pairs_BLANK.csv + pairs_KEY.csv
    python "New project/make_pairs.py" --round2   # write validation/pairs_r2_BLANK.csv + pairs_r2_KEY.csv
    python "New project/score_pairs.py"           # after labelling (--round2 for the second)

The split has a measured count (`score_counts.py`); the grouping of
requirements and of job titles had only tests written by us, which check that
the rules do what we decided, not that what we decided is right. One question
answers both: *are these two the same thing?*

Four cells of 15, so neither answer is the safe guess:

* requirement, MERGED   — two cores the embedding joined at cosine >= 0.90;
* requirement, APART    — a core and its nearest neighbour at 0.85-0.90, same
  names and same head group, so the threshold alone kept them apart;
* role, MERGED          — two title keys in one title group;
* role, APART           — two title groups whose keys differ by one word
  (`data analyst` / `data scientist`): the hard ones, not `Java` / `Sales`.

`MERGED` judged "no" is a wrong merge; `APART` judged "yes" is a missed one.

Round 2 (2026-11-04): round 1 found 14 of 14 near misses at 0.85-0.90 judged
the same, so the threshold is too strict, but not where wrong merges begin.
Round 2 draws 15 requirement pairs one band lower, 0.80-0.85, by the same rule,
none repeated from round 1. Roles are not redrawn: their rules are not a threshold.
Only postings outside `software_holdout`. The decision of the rules is in the
key file, never in the sheet the labeller sees.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import embed  # noqa: E402
import group_requirements as gr  # noqa: E402

OUT = HERE / "output"
VAL = HERE / "validation"
SEED = 20261104
PER_CELL = 15
MIN_N = 3          # a pair of one-off wordings says little about the method


def _dev_ids() -> set:
    hold = set(json.loads((HERE / "test_sets.json").read_text(encoding="utf-8"))["software_holdout"])
    return hold


def requirement_pairs(rng: random.Random, hold: set, band: tuple[float, float] = (0.85, 0.90),
                      with_merged: bool = True, exclude: set = frozenset()) -> list[dict]:
    df = pd.read_parquet(OUT / "must_have_atoms.parquet",
                         columns=["posting_id", "counted", "atom_norm", "req_head_group",
                                  "req_core", "req_group_core"])
    df = df[df.counted & (df.req_core.str.strip() != "") & ~df.posting_id.isin(hold)]
    n = df.groupby(["req_head_group", "req_core"]).size()
    example = df.groupby(["req_head_group", "req_core"]).atom_norm.agg(lambda s: s.value_counts().index[0])
    phrases, vecs = embed.load_corpus(gr.CACHE)
    idx = {p: i for i, p in enumerate(phrases)}

    def vec(core):
        v = vecs[idx[core]].astype(np.float32)
        return v / np.linalg.norm(v)

    def row(g, a, b, decision):
        return {"kind": "requirement", "context": g or "(no head)",
                "a": a, "a_example": example.get((g, a), a),
                "b": b, "b_example": example.get((g, b), b),
                "decision": decision, "cosine": round(float(vec(a) @ vec(b)), 3)}

    merged = (df[df.req_core.str.casefold() != df.req_group_core.str.casefold()]
              .drop_duplicates(["req_head_group", "req_core"]))
    merged = [(g, a, b) for g, a, b in zip(merged.req_head_group, merged.req_core, merged.req_group_core)
              if n.get((g, a), 0) >= MIN_N and n.get((g, b), 0) >= MIN_N]
    out = [row(g, a, b, "merged") for g, a, b in rng.sample(merged, PER_CELL)] if with_merged else []

    # Near misses: nearest neighbour inside the head group, among frequent cores.
    apart = []
    c = n[n >= MIN_N].reset_index()
    grouped = set(zip(df.req_head_group, df.req_core.str.casefold(), df.req_group_core.str.casefold()))
    for g, sub in c.groupby("req_head_group"):
        cores = sub.req_core.tolist()
        if len(cores) < 2:
            continue
        v = np.stack([vec(x) for x in cores])
        best, sim = gr.nearest(v)
        for k, a in enumerate(cores):
            b = cores[best[k]]
            if band[0] <= sim[k] < band[1] and a.casefold() != b.casefold() \
                    and gr.names(a) == gr.names(b) and a < b and frozenset((a, b)) not in exclude:
                apart.append((g, a, b))
    out += [row(g, a, b, "apart") for g, a, b in rng.sample(apart, PER_CELL)]
    return out


def role_pairs(rng: random.Random, hold: set) -> list[dict]:
    t = pd.read_parquet(OUT / "titles.parquet")
    t = t[(t.title_group != "") & ~t.posting_id.isin(hold)]
    per_key = t.groupby("title_key").agg(n=("posting_id", "size"), group=("title_group", "first"),
                                         role=("title_role", lambda s: s.value_counts().index[0]),
                                         example=("job_title", lambda s: s.value_counts().index[0]))
    per_key = per_key[per_key.n >= MIN_N]

    def row(ka, kb, decision):
        a, b = per_key.loc[ka], per_key.loc[kb]
        return {"kind": "role", "context": "", "a": a.role, "a_example": a.example,
                "b": b.role, "b_example": b.example, "decision": decision, "cosine": ""}

    merged = []
    for g, sub in per_key.groupby("group"):
        keys = sub.index.tolist()
        merged += [(x, y) for i, x in enumerate(keys) for y in keys[i + 1:]]
    out = [row(x, y, "merged") for x, y in rng.sample(merged, PER_CELL)]

    # One word apart, in different groups. The commonest key of each group.
    top = per_key.sort_values("n", ascending=False).groupby("group").head(1)
    toks = {k: set(k.split()) for k in top.index}
    apart = [(x, y) for x in top.index for y in top.index
             if x < y and len(toks[x]) == len(toks[y]) >= 2 and len(toks[x] ^ toks[y]) == 2]
    out += [row(x, y, "apart") for x, y in rng.sample(apart, PER_CELL)]
    return out


def main() -> None:
    r2 = "--round2" in sys.argv
    tag = "pairs_r2" if r2 else "pairs"
    blank, key = VAL / f"{tag}_BLANK.csv", VAL / f"{tag}_KEY.csv"
    if (VAL / f"{tag}_LABELLED.csv").exists():
        raise FileExistsError(f"{tag}_LABELLED.csv exists: move it aside before redrawing")
    rng = random.Random(SEED + 1 if r2 else SEED)
    hold = _dev_ids()
    if r2:
        k1 = pd.read_csv(VAL / "pairs_KEY.csv", encoding="utf-8-sig", dtype=str).fillna("")
        seen = {frozenset((a, b)) for a, b in zip(k1.a, k1.b)}
        pairs = requirement_pairs(rng, hold, band=(0.80, 0.85), with_merged=False, exclude=seen)
    else:
        pairs = requirement_pairs(rng, hold) + role_pairs(rng, hold)
    rng.shuffle(pairs)
    for i, p in enumerate(pairs, 1):
        p["pair"] = i
        if rng.random() < 0.5:   # which side is `a` says nothing either
            p["a"], p["b"] = p["b"], p["a"]
            p["a_example"], p["b_example"] = p["b_example"], p["a_example"]
    d = pd.DataFrame(pairs)
    d[["pair", "kind", "context", "a", "a_example", "b", "b_example"]].assign(
        same="", unsure="", note="").to_csv(blank, index=False, encoding="utf-8-sig")
    d[["pair", "kind", "decision", "cosine", "a", "b"]].to_csv(key, index=False, encoding="utf-8-sig")
    print(f"{len(d)} pairs -> {blank.name} (blind) and {key.name} (do not open while labelling)")
    print(d.groupby(["kind", "decision"]).size().to_string())


if __name__ == "__main__":
    main()
