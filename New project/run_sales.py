"""Run the FROZEN splitter and normaliser on SALES_BD, as a test of generalisation.

    python "New project/run_sales.py" --translate   # translate, resumable (slow)
    python "New project/run_sales.py"               # split, normalise, measure
    python "New project/run_sales.py" --sample2     # the same on the untouched sample

Decided 2026-11-02. Every rule was written looking at software postings only,
and the aim is a model that holds on `must_have` text nobody has seen yet. A
different job family is the hardest such text available, so the rules are run
here exactly as committed (9c8b5f0) and nothing is changed during the test.

Input is `europe_jobs_SALES_BD.json` as delivered, `must_have` only. That
export joins items with ` | `; for the 16,460 software postings present in both
exports, splitting the old string on ` | ` gives the new list exactly in 98.7%
of cases, so the format is not a confound.

Without labels this measures whether the model BREAKS on sales — the same
label-free defects as `split_quality.py`, beside `software_holdout` — not
whether it COUNTS right. That would need a hand count on sales.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import split_must_have as smh  # noqa: E402
import split_quality as q  # noqa: E402
import translate_must_have as tm  # noqa: E402

SALES = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "europe_jobs_SALES_BD.json"
# Sample 1 was read on 2026-11-02 to find the patterns behind the errors, so it
# is a development set from then on. Sample 2 is drawn from the postings left
# over and is the one any change is judged on.
SAMPLE = 2 if "--sample2" in sys.argv else 1
OUT = HERE / "output" / ("sales" if SAMPLE == 1 else "sales_2")
TRANSLATIONS = OUT / "items_en.parquet"
SAMPLE_POSTINGS = 1000
SEED = 20261102


def rows() -> list[dict]:
    """`vacancy_id` and the `must_have` items of a random SAMPLE of postings.

    A sample, not the export: the question is whether the model holds on
    sales, which ~6,000 items answer, and translating all 44,809 unique items
    would be the transformation of sales we do not want (decided 2026-11-02).
    """
    rs = [{"_id": r["vacancy_id"],
           "must_have": [x.strip() for x in (r["must_have"] or "").split(" | ") if x.strip()]}
          for r in json.loads(SALES.read_text(encoding="utf-8"))]
    rs = [r for r in rs if r["must_have"]]
    first = random.Random(SEED).sample(rs, SAMPLE_POSTINGS)
    if SAMPLE == 1:
        return first
    taken = {r["_id"] for r in first}
    return random.Random(SEED + 1).sample([r for r in rs if r["_id"] not in taken], SAMPLE_POSTINGS)


def translate(rs: list[dict]) -> None:
    items = tm.item_languages(rs)
    print(items.language.fillna("(undecided)").value_counts().to_string())
    # Same append-only cache as software: an item already translated there is reused.
    cache = tm.translate_all(items)
    items["item_en"] = [cache.get(tm._key(c, i)) if isinstance(c, str) else i
                        for i, c in zip(items.item, items.code)]
    items["translated"] = items.code.notna()
    assert items.item_en.notna().all(), "translation incomplete"
    OUT.mkdir(parents=True, exist_ok=True)
    items.to_parquet(TRANSLATIONS, index=False)
    print(f"wrote {TRANSLATIONS}")


def main() -> None:
    rs = rows()
    if "--translate" in sys.argv:
        translate(rs)
        return
    t = pd.read_parquet(TRANSLATIONS)
    tr = dict(zip(t["item"], t["item_en"]))
    df = smh.split_export(rs, tr)
    df.to_parquet(OUT / "must_have_atoms.parquet", index=False)
    summary = smh.summarise(rs, df)
    summary["items_translated"] = int(df.drop_duplicates(["posting_id", "item_idx"]).translated.sum())
    (OUT / "must_have_atoms_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    table = pd.DataFrame([q.measure(f"sales_sample{SAMPLE}", rows=rs, tr=tr),
                          # Tagger on for both, or the comparison is not like for like.
                          q.measure("software_holdout", rows=q.rows_for("software_holdout"),
                                    tr=q.translations("software_holdout"))]).set_index("set")
    table.T.to_csv(OUT / "quality_vs_software.csv")
    print(table.T.to_string())


if __name__ == "__main__":
    main()
