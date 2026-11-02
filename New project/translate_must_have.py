"""Translate every non-English `must_have` item to English, locally.

    python "New project/translate_must_have.py"            # translate, resumable
    python "New project/translate_must_have.py" --count    # how much is left, no model

Decided 2026-10-29, for the requirement COUNT: translate first, then split. The
test behind it (58 labelled non-English rows, same rules) left precision and
recall unchanged at 0.607 / 0.526 but raised exact-count agreement 0.638 ->
0.690 and halved over-splitting (0.138 -> 0.069); on 600 corpus items it cut
one-word fragments 87 -> 49. The rules are simply better developed in English.

What it costs, and must stay visible downstream: atoms are in translated
English, not the employer's words, so `item` (original) is kept beside
`item_en` and every atom stays traceable to it. And scoring against the labels
needs the labels translated too, which biases P/R AGAINST translation.

Helsinki-NLP opus-mt on CPU, beam 4, the settings the test measured. Nothing
leaves the machine. The cache is append-only and keyed by language + text, so
an interrupted run loses at most one batch.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import language  # noqa: E402

EXPORT = ROOT / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"
OUT_DIR = Path(__file__).resolve().parent / "output"
CACHE = OUT_DIR / "translate_cache.jsonl"
OUT = OUT_DIR / "items_en.parquet"

CODE = {"Deutsch": "de", "Français": "fr", "Nederlands": "nl", "Italiano": "it",
        "Español": "es", "Português": "pt", "Svenska": "sv"}
MODEL_FOR = {"de": "opus-mt-de-en", "fr": "opus-mt-fr-en", "nl": "opus-mt-nl-en",
             "sv": "opus-mt-sv-en", "it": "opus-mt-ROMANCE-en", "es": "opus-mt-ROMANCE-en",
             "pt": "opus-mt-ROMANCE-en"}
BATCH = 16
NUM_BEAMS = 4


def _key(code: str, text: str) -> str:
    return hashlib.sha256(f"{code}\x00{text}".encode("utf-8")).hexdigest()[:32]


def item_languages(rows: list[dict]) -> pd.DataFrame:
    """The language of each unique item, and how it was decided.

    The item's own text where the detector can decide it; the posting's
    otherwise. Items are short, so the detector abstains often — `Python`,
    `Teamfähigkeit` — and the posting is the better guess than nothing. Where
    neither decides, the item is left as written and marked.
    """
    seen: dict[str, tuple[str | None, str]] = {}
    for r in rows:
        if not r["must_have"]:
            continue
        posting_lang = language.detect(" | ".join(r["must_have"]))[0]
        for it in r["must_have"]:
            if it in seen:
                continue
            own = language.detect(it)[0]
            if own:
                seen[it] = (own, "item")
            elif posting_lang:
                seen[it] = (posting_lang, "posting")
            else:
                seen[it] = (None, "undecided")
    d = pd.DataFrame([(k, v[0], v[1]) for k, v in seen.items()],
                     columns=["item", "language", "language_source"])
    d["code"] = d.language.map(CODE)
    return d


def load_cache() -> dict[str, str]:
    out = {}
    if CACHE.exists():
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    out[r["key"]] = r["out"]
    return out


def translate_all(items: pd.DataFrame) -> dict[str, str]:
    import torch
    from transformers import MarianMTModel, MarianTokenizer

    torch.set_num_threads(os.cpu_count() or 4)
    cache = load_cache()
    OUT_DIR.mkdir(exist_ok=True)
    todo = items[items.code.notna()]
    by_model = collections.defaultdict(list)
    for it, code in zip(todo.item, todo.code):
        if _key(code, it) not in cache:
            by_model[MODEL_FOR[code]].append((code, it))
    left = sum(len(v) for v in by_model.values())
    print(f"to translate: {left:,} (cached: {len(todo) - left:,})", flush=True)

    done, t0 = 0, time.time()
    for name, pairs in by_model.items():
        tok = MarianTokenizer.from_pretrained(f"Helsinki-NLP/{name}")
        mdl = MarianMTModel.from_pretrained(f"Helsinki-NLP/{name}").eval()
        # Short first: batches of similar length pad less and run faster.
        pairs.sort(key=lambda p: len(p[1]))
        with open(CACHE, "a", encoding="utf-8") as fh:
            for i in range(0, len(pairs), BATCH):
                chunk = pairs[i:i + BATCH]
                batch = tok([p[1] for p in chunk], return_tensors="pt", padding=True,
                            truncation=True, max_length=256)
                with torch.no_grad():
                    gen = mdl.generate(**batch, num_beams=NUM_BEAMS, max_new_tokens=256)
                for (code, src), out in zip(chunk, tok.batch_decode(gen, skip_special_tokens=True)):
                    cache[_key(code, src)] = out.strip()
                    fh.write(json.dumps({"key": _key(code, src), "lang": code, "src": src,
                                         "out": out.strip()}, ensure_ascii=False) + "\n")
                fh.flush()
                done += len(chunk)
                if (i // BATCH) % 50 == 0:
                    rate = done / max(time.time() - t0, 1e-9)
                    print(f"  {name}: {done:,}/{left:,}  {rate:.1f} items/s  "
                          f"~{(left - done) / max(rate, 1e-9) / 60:.0f} min left", flush=True)
    return cache


def main() -> None:
    rows = json.loads(EXPORT.read_text(encoding="utf-8"))
    items = item_languages(rows)
    print(items.language.fillna("(undecided)").value_counts().to_string())
    print(items.language_source.value_counts().to_string())
    if "--count" in sys.argv:
        cache = load_cache()
        todo = items[items.code.notna()]
        print(f"non-English items: {len(todo):,}, still to translate: "
              f"{sum(_key(c, i) not in cache for i, c in zip(todo.item, todo.code)):,}")
        return

    cache = translate_all(items)
    items["item_en"] = [cache.get(_key(c, i)) if isinstance(c, str) else i
                        for i, c in zip(items.item, items.code)]
    items["translated"] = items.code.notna()
    assert items.item_en.notna().all(), "translation incomplete"
    items.to_parquet(OUT, index=False)
    print(f"wrote {OUT} — {items.translated.sum():,} translated, "
          f"{(~items.translated).sum():,} kept as written")


if __name__ == "__main__":
    main()
