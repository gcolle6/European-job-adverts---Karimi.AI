"""Score the pair sample: how often the two normalisations merge wrongly or miss.

    python "New project/score_pairs.py"            # round 1
    python "New project/score_pairs.py" --round2   # round 2: requirements at 0.80-0.85

Reads `validation/pairs_LABELLED.csv` (the human's `same`: y / n) and
`pairs_KEY.csv` (what the rules decided when the sample was drawn). Per kind:

* wrong merges  — MERGED pairs judged different: the error that is fatal on
  roles, since it joins what the product exists to compare;
* missed merges — APART pairs judged the same: costs depth, not correctness.

Two readings, both printed, never pooled:

* `blind`     — the labels as given, before the labeller saw what the rules did;
* `rechecked` — after `pairs_corrections.csv`, which the labeller wrote AFTER
  seeing the rules' answers. It measures agreement with a settled definition,
  not blind accuracy.

Role decisions are read from the CURRENT `titles.parquet`, so a rule change
shows up; the key keeps the decision at draw time. A rule changed because of
these pairs is then scored on the pairs that motivated it — in-sample, and
said so.

Cells are 15 pairs, so each rate is +-~12 points; and APART pairs are the hard
near misses, not a random draw, so the missed rate is an upper bound for the
corpus. `unsure` pairs are reported, never scored as either answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
VAL = HERE / "validation"
_YN = {"y": True, "s": True, "n": False}


def _role_decisions(d: pd.DataFrame) -> pd.Series:
    t = pd.read_parquet(HERE / "output" / "titles.parquet", columns=["title_role", "title_group"])
    t = t[t.title_group != ""]
    group = t.groupby("title_role").title_group.agg(lambda s: s.value_counts().index[0])
    now = d.decision.copy()
    for i, r in d[d.kind == "role"].iterrows():
        ga, gb = group.get(r.a), group.get(r.b)
        if ga is not None and gb is not None:
            now[i] = "merged" if ga == gb else "apart"
    return now


def _report(d: pd.DataFrame, reading: str) -> None:
    print(f"\n######## {reading}")
    for kind, sub in d.groupby("kind"):
        print(f"\n== {kind} ==")
        for decision, s in sub.groupby("decision"):
            wrong = (~s.same) if decision == "merged" else s.same
            label = "wrong merges" if decision == "merged" else "missed merges"
            print(f"  {decision:7} {label}: {int(wrong.sum())}/{len(s)} = {wrong.mean():.0%}"
                  f"   (unsure {int(s.unsure.sum())})")
            for _, r in s[wrong].iterrows():
                print(f"      {r.a!r} ~ {r.b!r}  {r.cosine}  {r.note}")


def load(tag: str, verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """(blind labels, rechecked labels or None), decisions from the current rules."""
    lab = pd.read_csv(VAL / f"{tag}_LABELLED.csv", encoding="utf-8-sig", dtype=str).fillna("")
    key = pd.read_csv(VAL / f"{tag}_KEY.csv", encoding="utf-8-sig", dtype=str).fillna("")
    d = lab[["pair", "same", "unsure", "note"]].merge(key, on="pair")
    d["same"] = d.same.str.strip().str.lower().str[:1].map(_YN)
    d["unsure"] = d.unsure.str.strip() != ""
    missing = d.same.isna().sum()
    if missing and verbose:
        print(f"{missing} pairs without a y/n answer, left out")
    d = d[d.same.notna()].assign(same=lambda x: x.same.astype(bool))
    changed = (_role_decisions(d) != d.decision)
    if changed.any() and verbose:
        print(f"{int(changed.sum())} role pairs decided differently by the current rules than at draw time:")
        for _, r in d[changed].iterrows():
            print(f"      {r.a!r} ~ {r.b!r}: {r.decision} -> {'apart' if r.decision == 'merged' else 'merged'}")
    d["decision"] = _role_decisions(d)
    fix = VAL / f"{tag}_corrections.csv"
    if not fix.exists():
        return d, None
    c = pd.read_csv(fix, encoding="utf-8-sig", dtype=str).fillna("")
    new = dict(zip(c.pair, c.same.str.strip().str.lower().str[:1].map(_YN)))
    if verbose:
        print(f"\n{len(new)} labels rechecked after seeing the rules: pairs {', '.join(new)}")
    return d, d.assign(same=[new.get(p, s) for p, s in zip(d.pair, d.same)])


def rates(d: pd.DataFrame) -> dict:
    """kind -> decision -> errors, pairs, unsure: what `_report` prints, as data."""
    out = {}
    for (kind, decision), s in d.groupby(["kind", "decision"]):
        wrong = (~s.same) if decision == "merged" else s.same
        out.setdefault(kind, {})[decision] = {"errors": int(wrong.sum()), "pairs": len(s),
                                              "unsure": int(s.unsure.sum())}
    return out


def main() -> None:
    tag = "pairs_r2" if "--round2" in sys.argv else "pairs"
    d, r = load(tag)
    _report(d, "blind labels")
    if r is not None:
        _report(r, "rechecked labels (NOT blind)")


if __name__ == "__main__":
    main()
