"""Score the requirement COUNT against the human count on the holdout.

    python "New project/score_counts.py"            # scores only, nothing per row
    python "New project/score_counts.py" --read     # also lists the errors on the READ half

`validation/count_holdout_LABELLED.csv`: 120 random item occurrences from
`software_holdout`, counted by the user on 2026-10-30 from the item text and
`COUNT_GUIDE.md`, without seeing any output. It is the only measure that does
not share the tagger with the splitter, and there will be no more of them, so it
is used in two halves, split once by a fixed seed:

* ``read``  — errors may be read and may inform rules;
* ``blind`` — never read row by row. Its score is the honest one from now on.

The first score, over all 120, is honest too: no rule was written while the
labels existed.

⚠️ The guide carries the project's own conventions (coordinated verbs = 1, ...),
so agreement measures whether the splitter follows them, not whether they are
right.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import split_quality as q  # noqa: E402
from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402
from karimi import pos  # noqa: E402

LABELLED = HERE / "validation" / "count_holdout_LABELLED.csv"
SEED = 20261030
BOOT = 2000


def load() -> list[dict]:
    """The sheet as saved: notes hold unquoted commas, so the tail is rejoined."""
    with open(LABELLED, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    head, out = rows[0], []
    for r in rows[1:]:
        if not r:
            continue
        rec = dict(zip(head[:7], r[:7]))
        rec["note"] = ",".join(r[7:]).strip()
        rec["unsure"] = bool(rec["unsure"].strip())
        rec["n"] = int(rec["n_requirements"]) if rec["n_requirements"].strip().isdigit() else None
        out.append(rec)
    assert len(out) == 120, len(out)
    # Left blank by the labeller: 5 of 120 (3 of them in Lithuanian, Polish and
    # Czech, which the pipeline does not translate). Scored on the rest; the
    # sheet is never re-opened for them.
    blank = [r["row"] for r in out if r["n"] is None]
    print(f"labelled {len(out) - len(blank)} of {len(out)}; blank rows {blank}")
    return out


def halves(rows: list[dict]) -> None:
    order = list(range(len(rows)))
    random.Random(SEED).shuffle(order)
    read = set(order[: len(rows) // 2])
    for k, r in enumerate(rows):
        r["half"] = "read" if k in read else "blind"


def system_counts(rows: list[dict]) -> dict[str, list[int]]:
    tr = q.translations("software_holdout")
    en = [tr.get(r["item"], r["item"]) for r in rows]
    orig = [r["item"] for r in rows]
    out = {"no split": [1] * len(rows)}
    config.SPLIT_REPAIRS, config.SPLIT_POS = False, False
    out["Week 1 code, original text"] = [len(atom.route(s)[0]) for s in orig]
    config.SPLIT_REPAIRS = True
    out["repairs, original text"] = [len(atom.route(s)[0]) for s in orig]
    out["repairs, translated"] = [len(atom.route(s)[0]) for s in en]
    config.SPLIT_POS = True
    pos.prime(en)
    cur = [atom.route(s)[0] for s in en]
    out["current, nice-to-have counted"] = [len(a) for a in cur]
    out["current: translated + repairs + tagger"] = [sum(atom.counted(a)) for a in cur]
    return out


def stats(human: list[int], sys_: list[int]) -> dict:
    n = len(human)
    exact = sum(h == s for h, s in zip(human, sys_)) / n
    over = sum(s > h for h, s in zip(human, sys_)) / n
    under = sum(s < h for h, s in zip(human, sys_)) / n
    mae = sum(abs(h - s) for h, s in zip(human, sys_)) / n
    ratio = sum(sys_) / sum(human)
    rng = random.Random(SEED)
    boot_e, boot_r = [], []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in range(n)]
        boot_e.append(sum(human[i] == sys_[i] for i in idx) / n)
        boot_r.append(sum(sys_[i] for i in idx) / sum(human[i] for i in idx))
    boot_e.sort(), boot_r.sort()
    lo, hi = int(BOOT * 0.025), int(BOOT * 0.975)
    return {"exact": exact, "exact_ci": (boot_e[lo], boot_e[hi]), "over": over, "under": under,
            "mae": mae, "ratio": ratio, "ratio_ci": (boot_r[lo], boot_r[hi])}


def report(rows: list[dict], counts: dict[str, list[int]], label: str) -> None:
    human = [r["n"] for r in rows]
    print(f"\n{label}: {len(rows)} items, {sum(human)} requirements by hand "
          f"({sum(r['unsure'] for r in rows)} marked unsure)")
    print(f"  {'':40s} {'exact':>6s} {'95% CI':>13s} {'over':>5s} {'under':>6s} {'MAE':>5s} "
          f"{'total':>6s} {'95% CI':>13s}")
    for name, c in counts.items():
        s = stats(human, c)
        print(f"  {name:40s} {s['exact']:6.1%} {s['exact_ci'][0]:6.1%}-{s['exact_ci'][1]:<6.1%} "
              f"{s['over']:5.1%} {s['under']:6.1%} {s['mae']:5.2f} {s['ratio']:6.3f} "
              f"{s['ratio_ci'][0]:.3f}-{s['ratio_ci'][1]:.3f}")


def main() -> None:
    rows = load()
    halves(rows)
    rows = [r for r in rows if r["n"] is not None]
    counts = system_counts(rows)
    report(rows, counts, "ALL 120")
    for h in ("read", "blind"):
        idx = [k for k, r in enumerate(rows) if r["half"] == h]
        report([rows[k] for k in idx], {n: [c[k] for k in idx] for n, c in counts.items()}, f"half '{h}'")
    if "--read" in sys.argv:
        cur = counts["current: translated + repairs + tagger"]
        tr = q.translations("software_holdout")
        print("\nerrors on the READ half only:")
        for k, r in enumerate(rows):
            if r["half"] == "read" and cur[k] != r["n"]:
                s = tr.get(r["item"], r["item"])
                config.SPLIT_REPAIRS = config.SPLIT_POS = True
                print(f"  human {r['n']}{'?' if r['unsure'] else ''} system {cur[k]} | {s[:110]}\n"
                      f"      {atom.route(s)[0]}" + (f"\n      note: {r['note']}" if r["note"] else ""))


if __name__ == "__main__":
    main()
