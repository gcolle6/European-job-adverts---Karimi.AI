"""Freeze one batch run into a versioned dictionary, and compare two of them.

    python -m karimi_normalise.freeze --version 0.0.dev1          # write a dictionary
    python -m karimi_normalise.freeze --diff 0.0.dev1 0.0.dev2    # what moved between two

Input is the batch output in `New project/output/`: `must_have_atoms.parquet`
(after `group_requirements.py --assign 0.90` and `--topic 0.80`),
`titles.parquet`, `titles_summary.json` and the core embeddings. Output is a
directory under `New project/output/dictionaries/`, ignored by git like every
table made from the adverts.

A dictionary is never overwritten: an improved rule or threshold is a new
freeze under a new version, and `diff` reports, weighted by occurrences, which
groups stayed, were renamed, split or merged. That report is what lets a rule
be improved after release without breaking whoever reads the groups.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from karimi import embed

from . import dictionary as dc
from . import reference
from .versions import RULES_VERSION, fingerprint

BATCH = Path(__file__).resolve().parents[1] / "New project" / "output"
STORE = BATCH / "dictionaries"
HOLDOUT = Path(__file__).resolve().parents[1] / "New project" / "test_sets.json"


def freeze(version: str, group_threshold: float = 0.90, topic_threshold: float = 0.80,
           batch: Path = BATCH, store: Path = STORE) -> Path:
    out = store / version
    if out.exists():
        raise FileExistsError(f"{out} exists: a dictionary is never overwritten, choose a new version")
    all_atoms = pd.read_parquet(batch / "must_have_atoms.parquet",
                                columns=["posting_id", "item_idx", "atom", "route", "translated",
                                         "req_head_group", "req_core", "req_group", "req_topic"])
    if all_atoms.req_topic.isna().any():
        raise ValueError("req_topic missing: run group_requirements.py --topic first")
    atoms = all_atoms[all_atoms.req_core.str.strip() != ""]
    cores = (atoms.groupby(["req_head_group", "req_core"])
             .agg(n=("req_group", "size"), req_group=("req_group", "first"),
                  groups=("req_group", "nunique"), req_topic=("req_topic", "first"))
             .reset_index())
    # (head group, core) decides the group in the batch, so one each.
    assert (cores.groups == 1).all(), "a core sits in two groups: lookup would be ambiguous"
    cores = cores.drop(columns="groups")

    phrases, vecs = embed.load_corpus(batch / "core_embeddings.npz")
    idx = {p: i for i, p in enumerate(phrases)}
    missing = [c for c in cores.req_core if c not in idx]
    if missing:
        raise ValueError(f"{len(missing)} cores have no embedding, e.g. {missing[:3]}: rerun grouping")
    v = vecs[[idx[c] for c in cores.req_core]].astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)

    all_titles = pd.read_parquet(batch / "titles.parquet")
    t = all_titles[all_titles.title_group != ""]
    # One row per role as written, so a new title can be matched as a variant
    # of it (`dictionary.lookup_title`), not only by its key.
    titles = (t.groupby("title_role").agg(title_key=("title_key", "first"), title_group=("title_group", "first"),
                                          title_name=("title_name", "first"), n=("posting_id", "size"))
              .reset_index())
    acronyms = json.loads((batch / "titles_summary.json").read_text(encoding="utf-8"))["acronyms_learned"]

    manifest = {
        "dict_version": version,
        "group_threshold": group_threshold,
        "topic_threshold": topic_threshold,
    }
    # The bands a run report is read against (`reference.py`), made from the
    # same batch, so they travel with the dictionary they describe.
    by_core = {c: v[i] for i, c in enumerate(cores.req_core)}
    hold = set(json.loads(HOLDOUT.read_text(encoding="utf-8"))["software_holdout"])
    ref = reference.build(all_atoms, all_titles, by_core, manifest, acronyms, hold)

    out.mkdir(parents=True)
    cores.to_parquet(out / "req_cores.parquet", index=False)
    np.save(out / "req_vectors.npy", v.astype(np.float16))
    titles.to_parquet(out / "titles.parquet", index=False)
    (out / "title_acronyms.json").write_text(json.dumps(acronyms, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    reference.write(ref, out / "reference.json")
    manifest = {
        "dict_version": version,
        "created": dt.date.today().isoformat(),
        "rules_version": RULES_VERSION,
        "rules_fingerprint": fingerprint(),
        "embed_model": embed.DEFAULT_MODEL,
        "group_threshold": group_threshold,
        "topic_threshold": topic_threshold,
        "source": {"must_have_atoms.parquet": dc.sha256(batch / "must_have_atoms.parquet"),
                   "titles.parquet": dc.sha256(batch / "titles.parquet")},
        "counts": {"req_cores": len(cores), "req_groups": int(cores.req_group.nunique()),
                   "req_topics": int(cores.req_topic.nunique()), "title_keys": int(titles.title_key.nunique()),
                   "title_groups": int(titles.title_group.nunique())},
        "sha256": {f: dc.sha256(out / f) for f in dc.FILES + ["reference.json"]},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def diff(old: str | Path, new: str | Path, store: Path = STORE) -> dict:
    """Where the members of each old group went, weighted by old occurrences.

    * ``same``    — every member still in a group of the same name;
    * ``renamed`` — every member in one group, under another name (its
      commonest wording changed);
    * ``split``   — members now in two or more groups;
    * ``gone``    — members no longer produced by the rules.

    And ``merged``: new groups that took members from two or more old ones.
    """
    a = pd.read_parquet(Path(store) / str(old) / "req_cores.parquet")
    b = pd.read_parquet(Path(store) / str(new) / "req_cores.parquet")
    m = a.merge(b[["req_head_group", "req_core", "req_group"]], on=["req_head_group", "req_core"],
                how="left", suffixes=("", "_new"))
    fate = {}
    for g, sub in m.groupby("req_group"):
        to = set(sub.req_group_new.dropna())
        fate[g] = ("gone" if not to else "split" if len(to) > 1
                   else "same" if to == {g} else "renamed")
    mass = m.groupby("req_group").n.sum()
    kinds = pd.Series(fate)
    merged = m.dropna(subset=["req_group_new"]).groupby("req_group_new").req_group.nunique()
    return {
        "groups_by_fate": kinds.value_counts().to_dict(),
        "occurrences_by_fate": {k: round(float(mass[kinds == k].sum() / mass.sum()), 4)
                                for k in kinds.unique()},
        "new_groups_merged_from_several": int((merged > 1).sum()),
        "cores_added": int(len(b) - b.merge(a[["req_head_group", "req_core"]]).shape[0]),
        "renamed": {g: m[m.req_group == g].req_group_new.dropna().iloc[0] for g in kinds[kinds == "renamed"].index},
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--version")
    p.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"))
    args = p.parse_args(argv)
    if args.diff:
        d = diff(*args.diff)
        d["renamed"] = dict(list(d["renamed"].items())[:30])
        print(json.dumps(d, indent=2, ensure_ascii=False))
    elif args.version:
        out = freeze(args.version)
        print(json.dumps(json.loads((out / "manifest.json").read_text(encoding="utf-8"))["counts"], indent=2))
        print(f"-> {out}")
    else:
        p.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
