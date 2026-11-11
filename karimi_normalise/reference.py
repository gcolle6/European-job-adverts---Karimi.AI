"""What a normal run looks like: the bands a run report is read against.

A user's run has no human labels, so its report cannot say how much is right.
It can say whether the run LOOKS LIKE the corpus on which correctness was
measured (`quality.py`). Each signal of `metrics.run_metrics` is computed here
on the batch, for random runs of several sizes, and kept as percentiles: a
run of 10 postings varies far more than a run of 1,000, so it is read against
runs of its own size.

The match signals (`nuovo`, topic only, ...) cannot be read off the batch: the
dictionary was made from it, so everything in it is `known`. They are
simulated instead. 90% of the postings make a dictionary, the other 10% are
looked up in it, exactly as a new run would be, and the lookup is compared
with the batch's own groups. That comparison is phase 1's criterion 2: how
often lookup and batch agree on cores the dictionary had not seen. A 90%
dictionary knows a little less than the full one, so these `nuovo` rates are a
slight overestimate for a real run.

Dev postings only: `software_holdout` is kept for the labelled scores.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

from . import dictionary as dc

SIZES = [10, 30, 100, 300, 1000]
RUNS = 500
SEED = 20261104
HELD = 0.10
PCT = [1, 5, 50, 95, 99]

# Signal -> (numerator, denominator), both per posting. `metrics.run_metrics`
# computes the same ratios on a run; the names must agree.
SIGNALS = {
    "requirements_per_item": ("atoms", "items"),
    "share_items_llm": ("items_llm", "items"),
    "share_items_damaged": ("items_damaged", "items"),
    "share_one_word": ("atoms_one_word", "atoms"),
    "share_translated": ("atoms_translated", "atoms"),
    "share_known": ("atoms_known", "atoms"),
    "share_group_nearest": ("atoms_group", "atoms"),
    "share_topic_only": ("atoms_topic", "atoms"),
    "share_nuovo": ("atoms_nuovo", "atoms"),
    "share_titles_nuovo": ("titles_nuovo", "titles"),
}
MATCH_SIGNALS = {"share_known", "share_group_nearest", "share_topic_only", "share_nuovo",
                 "share_titles_nuovo"}


def _per_posting(atoms: pd.DataFrame) -> pd.DataFrame:
    items = atoms.drop_duplicates(["posting_id", "item_idx"])
    g = atoms.groupby("posting_id")
    return pd.DataFrame({
        "atoms": g.size(),
        "atoms_one_word": g.atom.agg(lambda s: int((s.str.split().str.len() == 1).sum())),
        "atoms_translated": g.translated.sum(),
        "items": items.groupby("posting_id").size(),
        "items_llm": items.assign(x=items.route == "llm").groupby("posting_id").x.sum(),
        "items_damaged": items.assign(x=items.route == "damaged").groupby("posting_id").x.sum(),
    })


def simulated_matches(atoms: pd.DataFrame, titles: pd.DataFrame, vectors: dict[str, np.ndarray],
                      manifest: dict, acronyms: dict):
    """The lookup itself: a dictionary from 90% of postings, the other 10% looked up.

    Returns the held atoms with each lookup's `status` and `via` (the known core
    it was placed by), the 90% dictionary, and the held postings. The judge's
    reference (`check.reference`) samples its pairs from exactly these.
    """
    ids = sorted(atoms.posting_id.unique())
    random.Random(SEED).shuffle(ids)
    held = set(ids[: int(len(ids) * HELD)])
    a, b = atoms[~atoms.posting_id.isin(held)], atoms[atoms.posting_id.isin(held)]
    a = a[a.req_core.str.strip() != ""]
    cores = (a.groupby(["req_space", "req_core"])
             .agg(req_group=("req_group", "first"), req_topic=("req_topic", "first"))
             .reset_index())
    v = np.stack([vectors[c] for c in cores.req_core])
    ta = titles[~titles.posting_id.isin(held) & (titles.title_group != "")]
    tdict = ta.groupby("title_role").agg(title_key=("title_key", "first"), title_group=("title_group", "first"),
                                         title_name=("title_name", "first")).reset_index()
    d = dc.Dictionary.from_tables(manifest, cores, v, tdict, acronyms,
                                  encoder=lambda texts: np.stack([vectors[t] for t in texts]))
    parts = list(dict.fromkeys(zip(b.req_space, b.req_core)))
    match = dict(zip(parts, d.lookup_requirements(parts)))
    m = [match[p] for p in zip(b.req_space, b.req_core)]
    b = b.assign(status=[x.status for x in m], via=[x.via for x in m],
                 same_group=[x.group == g for x, g in zip(m, b.req_group)],
                 same_topic=[x.topic == t for x, t in zip(m, b.req_topic)])
    return b, d, held


def simulate_lookup(atoms: pd.DataFrame, titles: pd.DataFrame, vectors: dict[str, np.ndarray],
                    manifest: dict, acronyms: dict) -> tuple[pd.DataFrame, dict]:
    """Dictionary from 90% of postings, lookup of the other 10%.

    Returns per-posting match counts for the 10%, and how often the lookup
    agrees with the batch's own groups, by match kind, weighted by occurrences.
    """
    b, d, held = simulated_matches(atoms, titles, vectors, manifest, acronyms)
    agree = {s: {"atoms": int((b.status == s).sum()),
                 "same_group": round(float(b[b.status == s].same_group.mean()), 4),
                 "same_topic": round(float(b[b.status == s].same_topic.mean()), 4)}
             for s in ("known", "group", "topic") if (b.status == s).any()}
    g = b.groupby("posting_id")
    per = pd.DataFrame({f"atoms_{s}": g.status.agg(lambda x, s=s: int((x == s).sum()))
                        for s in ("known", "group", "topic", "nuovo")})
    per["atoms"] = g.size()
    tb = titles[titles.posting_id.isin(held)].set_index("posting_id").title_role.reindex(per.index).fillna("")
    status = {r: d.lookup_title(r)[3] for r in set(tb)}
    per["titles"] = 1
    per["titles_nuovo"] = [int(status[r] == "nuovo") for r in tb]
    return per, {"held_postings": len(held), "by_match": agree}


def bands(per: pd.DataFrame, signals: list[str]) -> dict:
    rng = np.random.default_rng(SEED)
    out = {}
    for name in signals:
        num, den = SIGNALS[name]
        x, y = per[num].to_numpy(float), per[den].to_numpy(float)
        out[name] = {"overall": round(float(x.sum() / y.sum()), 4), "by_size": {}}
        for s in SIZES:
            idx = rng.integers(0, len(per), (RUNS, s))
            den_s = y[idx].sum(1)
            r = np.divide(x[idx].sum(1), den_s, out=np.full(RUNS, np.nan), where=den_s > 0)
            out[name]["by_size"][str(s)] = dict(zip(map(str, PCT), np.nanpercentile(r, PCT).round(4).tolist()))
    return out


def build(atoms: pd.DataFrame, titles: pd.DataFrame, vectors: dict[str, np.ndarray],
          manifest: dict, acronyms: dict, holdout: set) -> dict:
    atoms = atoms[~atoms.posting_id.isin(holdout)]
    titles = titles[~titles.posting_id.isin(holdout)]
    per_split = _per_posting(atoms)
    per_match, agreement = simulate_lookup(atoms, titles, vectors, manifest, acronyms)
    return {
        "made_from": {"postings": int(len(per_split)), "dev_only": True},
        "sizes": SIZES, "runs_per_size": RUNS, "percentiles": PCT,
        "signals": {**bands(per_split, [s for s in SIGNALS if s not in MATCH_SIGNALS]),
                    **bands(per_match, sorted(MATCH_SIGNALS))},
        "lookup_vs_batch": agreement,
    }


def write(ref: dict, path: Path) -> None:
    path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
