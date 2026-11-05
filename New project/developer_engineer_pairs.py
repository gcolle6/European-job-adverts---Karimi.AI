"""Every pair the Developer = Engineer rule joined, for the user to decide one by one.

    python "New project/developer_engineer_pairs.py"   # write validation/developer_engineer_BLANK.csv

The rule (decided 2026-11-02) joins `X Developer` with `X Engineer`. The pair
sample found two of its merges judged different (`Systems Engineer` /
`System Developer`, `Solution Engineer` / `Solution Developer`) and others
judged the same, so the rule is right for some X and wrong for others. This
lists each X once, with how many postings each side carries, so the decision
is per X. Only merges the rule actually made: both sides occur in the data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import normalise_title as nt  # noqa: E402

OUT = HERE / "output"
VAL = HERE / "validation"


def main() -> None:
    t = pd.read_parquet(OUT / "titles.parquet")
    t = t[t.title_group != ""]
    per_key = t.groupby("title_key").agg(
        n=("posting_id", "size"), group=("title_group", "first"),
        role=("title_role", lambda s: s.value_counts().index[0]),
        examples=("job_title", lambda s: " | ".join(s.value_counts().index[:3])))
    rows = []
    for g, sub in per_key.groupby("group"):
        dev = sub[[nt._developer_head(r) for r in sub.role]]
        eng = sub[[r.split()[-1].lower() in ("engineer", "engineers") for r in sub.role]]
        if dev.empty or eng.empty:
            continue
        name = t[t.title_group == g].title_name.iloc[0]
        rows.append({
            "group": name,
            "developer_side": " / ".join(dev.role), "n_developer": int(dev.n.sum()),
            "engineer_side": " / ".join(eng.role), "n_engineer": int(eng.n.sum()),
            "developer_examples": " | ".join(dev.examples)[:200],
            "engineer_examples": " | ".join(eng.examples)[:200],
        })
    d = pd.DataFrame(rows)
    d["n_total"] = d.n_developer + d.n_engineer
    d = d.sort_values("n_total", ascending=False).reset_index(drop=True)
    d.insert(0, "row", range(1, len(d) + 1))
    d["same"] = ""
    d["note"] = ""
    out = VAL / "developer_engineer_BLANK.csv"
    d.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{len(d)} merged pairs, {int(d.n_total.sum()):,} postings -> {out.name}")
    print(d[["row", "developer_side", "n_developer", "engineer_side", "n_engineer"]].to_string(index=False))


if __name__ == "__main__":
    main()
