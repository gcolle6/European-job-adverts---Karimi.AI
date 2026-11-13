"""Split every `must_have` item of the re-delivered software export into atoms.

    python "New project/split_must_have.py"              # split the English translation
    python "New project/split_must_have.py" --original   # split the text as written

Rules only, run locally: nothing leaves the machine. By default the input is
the English translation from `translate_must_have.py` (decided 2026-10-29: the
rules count requirements better in English); `item` keeps the original. `config.SPLIT_REPAIRS` is
turned on here and only here, so the Week 1-4 runners still reproduce their
published figures.

What the repairs are and why: `New project/split_damage.py` grouped every
damaged rules split over the whole export (3,191 unique items, 6.3% of
splits), found that ~93% came from one function — bracket-list expansion —
and the fixes target each class. What still looks damaged afterwards (80
unique items, 0.2% of splits) is kept WHOLE, in the original wording: an
unsplit requirement is recoverable later, a wrongly split one is not.

`route` per item, as `atomise.route` labels it:

* ``rules``   — split by the rules;
* ``single``  — one requirement, correctly whole;
* ``llm``     — looks compound, but the rules cannot separate it. With no LLM
  stage it is kept whole: the name records why, not what ran;
* ``damaged`` — the rules split it and the result was visibly broken, so it is
  kept whole.

⚠️ The labelled gate does not move: holdout F1 0.618 -> 0.620. That is the
expected reading, not a failure of the repairs — the damage classes are rare
in a 150-row sample (3 rows) and common in the corpus (3,191 items). The gate
remains failed: precision 0.673 / recall 0.575 against 0.90 / 0.75.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402
from karimi import language  # noqa: E402
from karimi import normalise_req  # noqa: E402

EXPORT = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"
OUT_DIR = Path(__file__).resolve().parent / "output"


TRANSLATIONS = OUT_DIR / "items_en.parquet"


def split_export(rows: list[dict], translated: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per atom, carrying the item it came from and how it was handled.

    With ``translated`` (item -> English, from `translate_must_have.py`) the
    English text is what gets split — decided 2026-10-29 for the requirement
    count — and the original `item` stays on every atom so each one can be
    traced back to the employer's wording.
    """
    config.SPLIT_REPAIRS = True
    # The tagger needs English, so it runs only on the translate-first input
    # (`karimi/pos.py`, `PATTERNS.md`).
    config.SPLIT_POS = bool(translated)
    translated = translated or {}
    unique = {it for r in rows for it in r["must_have"]}
    # The library repairs the same mistranslation at the same point (rules 0.4.1).
    translated = {it: atom.repair_translation(it, en) for it, en in translated.items()}
    if config.SPLIT_POS:
        from karimi import pos
        pos.prime(translated.get(it, it) for it in unique)
    routed = {it: atom.route(translated.get(it, it)) for it in unique}
    # Same wording for the same demand (`karimi/normalise_req.py`), next to the
    # atom, never instead of it.
    normed = {(it, a): normalise_req.normalise_requirement(a, it in translated and translated[it] != it)
              for it in unique for a in routed[it][0]}
    # Years, level, head, core and the grouping key, each in its own column so
    # grouping loses nothing (`normalise_req.decompose`).
    parts = {v: normalise_req.decompose(v) for v in set(normed.values())}

    out = []
    for r in rows:
        items = r["must_have"]
        if not items:
            continue
        # The language OF THE TEXT. The export carries no language field, and
        # the old one described the advert, not `must_have` — 10.9% disagreed.
        text_lang = language.detect(" | ".join(items))[0]
        for i, item in enumerate(items):
            atoms, how = routed[item]
            counts = atom.counted(atoms)
            for j, a in enumerate(atoms):
                out.append({
                    "posting_id": r["_id"], "item_idx": i, "item": item,
                    "item_split": translated.get(item, item),
                    "translated": item in translated and translated[item] != item,
                    "text_language": text_lang, "route": how,
                    "atom_idx": j, "n_atoms": len(atoms), "atom": a,
                    # Optional by the employer (`Dutch is a plus`): kept, and not
                    # counted when it adds to a required part (`atom.counted`).
                    "nice_to_have": atom.nice_to_have(a),
                    "counted": counts[j],
                    "atom_norm": normed[(item, a)],
                    **{f"req_{k}": v for k, v in parts[normed[(item, a)]].items()},
                })
    return pd.DataFrame(out)


def summarise(rows: list[dict], df: pd.DataFrame) -> dict:
    items = df.drop_duplicates(["posting_id", "item_idx"])
    return {
        "postings": len(rows),
        "postings_with_must_have": int(df.posting_id.nunique()),
        "postings_empty_must_have": sum(1 for r in rows if not r["must_have"]),
        "items": len(items),
        "atoms": len(df),
        "requirements_counted": int(df.counted.sum()),
        "unique_atoms": int(df.atom.nunique()),
        "unique_atoms_norm": int(df.atom_norm.nunique()),
        "atoms_changed_by_norm": int((df.atom != df.atom_norm).sum()),
        "unique_keys": int(df.req_key.nunique()),
        "share_with_head": round(float((df.req_head_group != "").mean()), 4),
        "share_with_years": round(float(df.req_years_raw.ne("").mean()), 4),
        "atoms_per_item": round(len(df) / len(items), 3),
        "items_by_route": items.route.value_counts().to_dict(),
        "items_by_route_share": items.route.value_counts(normalize=True).round(4).to_dict(),
        "postings_by_text_language": (df.drop_duplicates("posting_id").text_language
                                      .fillna("(undetected)").value_counts().to_dict()),
        "config": {"SPLIT_REPAIRS": True, "SPLIT_POS": config.SPLIT_POS,
                   "EXPAND_PAREN_LISTS": config.EXPAND_PAREN_LISTS,
                   "ATOMISE_MAX_PASSES": config.ATOMISE_MAX_PASSES},
    }


def main() -> None:
    rows = json.loads(EXPORT.read_text(encoding="utf-8"))
    original = "--original" in sys.argv
    translated = None
    if not original:
        if not TRANSLATIONS.exists():
            sys.exit(f"{TRANSLATIONS} missing: run translate_must_have.py first, "
                     "or pass --original to split the text as written")
        t = pd.read_parquet(TRANSLATIONS)
        translated = dict(zip(t["item"], t["item_en"]))
    df = split_export(rows, translated)
    OUT_DIR.mkdir(exist_ok=True)
    name = "must_have_atoms_original" if original else "must_have_atoms"
    df.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
    summary = summarise(rows, df)
    summary["input"] = "original text" if original else "translated to English first"
    summary["items_translated"] = int(df.drop_duplicates(["posting_id", "item_idx"]).translated.sum())
    (OUT_DIR / f"{name}_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
