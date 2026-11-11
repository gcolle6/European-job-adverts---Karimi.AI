"""The quality card: how good one version is, measured on human labels.

    python -m karimi_normalise.quality --dict 0.0.dev2

Generated, never written by hand, so it cannot drift from the code. One card
per (rules version, dictionary version), kept in `New project/output/quality/`
beside an index of every card made, which is the version history the site
shows. Aggregates only: no advert text goes into a card.

What it collects, each from the script that owns the measure:

* the pattern cases (`test_patterns.py`) — behaviour, not correctness;
* the requirement count on 120 hand-counted items (`score_counts.py`), the
  blind half reported apart, as it is the honest one;
* the pair labels (`score_pairs.py`), blind and rechecked never pooled, and
  for requirements at BOTH levels, group and topic, read off the current output;
* lookup against batch on postings the dictionary did not see (`reference.py`);
* parity of library and batch, if `parity.py` has been run for these versions;
* what is NOT measured, said as plainly as what is.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import io
import json
import sys
from pathlib import Path

import pandas as pd

from .dictionary import Dictionary
from .freeze import BATCH, STORE
from .versions import RULES_VERSION

NEW = Path(__file__).resolve().parents[1] / "New project"
QUALITY = BATCH / "quality"

NOT_MEASURED = [
    "translation quality: only indirectly (translating first raised exact counts 64% -> 69%)",
    "normalisation of wording and the columns (years, level, head, core): pattern cases only",
    "wrong merges at the topic level: only the pairs drawn near the group threshold; no random sample of topic merges",
    "titles translated locally (71 postings): read, not scored",
]


def _load(name: str):
    sys.path.insert(0, str(NEW))
    spec = importlib.util.spec_from_file_location(name, NEW / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a)


def tests() -> dict:
    tp = _load("test_patterns")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tp.main()
    passed, total = buf.getvalue().strip().splitlines()[-1].split()[0].split("/")
    return {"passed": int(passed), "total": int(total)}


def split_count() -> dict:
    sc = _load("score_counts")
    rows = _quiet(sc.load)
    sc.halves(rows)
    rows = [r for r in rows if r["n"] is not None]
    cur = sc.system_counts(rows)["current: translated + repairs + tagger"]

    def score(idx):
        s = sc.stats([rows[k]["n"] for k in idx], [cur[k] for k in idx])
        return {"items": len(idx), "exact": round(s["exact"], 4),
                "exact_ci95": [round(x, 4) for x in s["exact_ci"]],
                "over_split": round(s["over"], 4), "under_split": round(s["under"], 4),
                "found_vs_human": round(s["ratio"], 4)}
    return {"labels": "120 items from software_holdout, counted by hand 2026-10-30 without seeing "
                      "any output; 5 left blank. The blind half was never read row by row.",
            "blind_half": score([k for k, r in enumerate(rows) if r["half"] == "blind"]),
            "all": score(list(range(len(rows))))}


def _levels(d: pd.DataFrame) -> pd.DataFrame:
    """Requirement pairs: are a and b in one group, and in one topic, NOW?"""
    atoms = pd.read_parquet(BATCH / "must_have_atoms.parquet",
                            columns=["req_space", "req_core", "req_group", "req_topic"])
    where = atoms.drop_duplicates(["req_space", "req_core"]).set_index(["req_space", "req_core"])
    out = []
    for _, r in d[d.kind == "requirement"].iterrows():
        h = "" if r.context == "(no head)" else r.context
        if (h, r.a) not in where.index or (h, r.b) not in where.index:
            # A rule change since the draw no longer produces this core: the
            # pair cannot be read off the current output, and is left out.
            continue
        a, b = where.loc[(h, r.a)], where.loc[(h, r.b)]
        out.append({**r, "same_group_now": a.req_group == b.req_group,
                    "same_topic_now": a.req_topic == b.req_topic})
    return pd.DataFrame(out)


def _level_rates(d: pd.DataFrame, col: str) -> dict:
    merged, apart = d[d[col]], d[~d[col]]
    return {"merged": {"errors": int((~merged.same).sum()), "pairs": len(merged)},
            "apart": {"errors": int(apart.same.sum()), "pairs": len(apart)}}


def pairs() -> dict:
    sp = _load("score_pairs")
    out = {"labels": "pairs judged same / different by the user, blind; 8 rechecked after seeing "
                     "the rules, reported apart. Round 1: 60 pairs (2026-11-04), round 2: 15 "
                     "requirement pairs at cosine 0.80-0.85."}
    for reading in ("blind", "rechecked"):
        frames = []
        for tag in ("pairs", "pairs_r2"):
            blind, rc = _quiet(sp.load, tag, False)
            lab = pd.read_csv(sp.VAL / f"{tag}_LABELLED.csv", encoding="utf-8-sig", dtype=str).fillna("")
            d = blind if reading == "blind" or rc is None else rc
            frames.append(d.merge(lab[["pair", "context"]], on="pair").assign(round=tag))
        d = pd.concat(frames, ignore_index=True)
        req = _levels(d)
        out["requirement_pairs_readable"] = f"{len(req)} of {int((d.kind == 'requirement').sum())}"
        out[reading] = {
            "requirement_group": _level_rates(req, "same_group_now"),
            "requirement_topic": _level_rates(req, "same_topic_now"),
            "role": sp.rates(d[d.kind == "role"]).get("role", {}),
        }
    return out


def _invariance() -> dict | None:
    """Share of items whose output moved under a meaning-preserving change (`invariance.py`)."""
    p = BATCH / "invariance" / "summary.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text(encoding="utf-8"))
    if s.get("rules_version") != RULES_VERSION:
        return None
    return {k: {"items": v["items"], "changed_share": v["changed_share"], "passes": v["passes"]}
            for k, v in s["summary"].items()}


def card(dict_version: str) -> dict:
    d = Dictionary(STORE / dict_version)
    parity = QUALITY / f"parity_{RULES_VERSION}__{dict_version}.json"
    detectors = QUALITY / f"error_detectors_{RULES_VERSION}__{dict_version}.json"
    split_errors = QUALITY / f"split_errors_{RULES_VERSION}__{dict_version}.json"
    return {
        "rules_version": RULES_VERSION,
        "dict_version": dict_version,
        "generated": dt.date.today().isoformat(),
        "release": not dict_version.startswith("0.0."),
        "tests": tests(),
        "split_count": split_count(),
        "pairs": pairs(),
        "lookup_vs_batch": (d.reference or {}).get("lookup_vs_batch"),
        "parity_with_batch": json.loads(parity.read_text(encoding="utf-8")) if parity.exists() else None,
        # how far the site's splitting-error counts can be trusted (`score_error_detectors.py`)
        "error_detectors": json.loads(detectors.read_text(encoding="utf-8")) if detectors.exists() else None,
        # the splitting half of the site's error table (`score_split_errors.py`)
        "split_errors": json.loads(split_errors.read_text(encoding="utf-8")) if split_errors.exists() else None,
        "invariance": _invariance(),
        "match_cosine": {"group_threshold": d.group_threshold, "topic_threshold": d.topic_threshold},
        "not_measured": NOT_MEASURED,
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dict", required=True)
    args = p.parse_args(argv)
    c = card(args.dict)
    QUALITY.mkdir(parents=True, exist_ok=True)
    path = QUALITY / f"quality_{c['rules_version']}__{c['dict_version']}.json"
    path.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    cards = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(QUALITY.glob("quality_*.json"))]
    (QUALITY / "index.json").write_text(json.dumps(
        [{k: x[k] for k in ("rules_version", "dict_version", "generated", "release")} |
         {"count_exact_blind": x["split_count"]["blind_half"]["exact"]} for x in cards],
        indent=2), encoding="utf-8")
    print(json.dumps(c, indent=2, ensure_ascii=False))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
