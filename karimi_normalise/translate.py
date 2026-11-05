"""Translate a non-English item to English before it is split.

Same models and settings as `New project/translate_must_have.py`, which made
the batch the measures come from: Helsinki-NLP opus-mt on CPU, beam 4. A
different setting would split differently, so `tests/test_library.py` checks
that the two files still agree.

Runs inside the process, so no text leaves the machine or the container.
Models load on first use, one per language, and stay loaded.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from karimi import language

CODE = {"Deutsch": "de", "Français": "fr", "Nederlands": "nl", "Italiano": "it",
        "Español": "es", "Português": "pt", "Svenska": "sv"}
MODEL_FOR = {"de": "opus-mt-de-en", "fr": "opus-mt-fr-en", "nl": "opus-mt-nl-en",
             "sv": "opus-mt-sv-en", "it": "opus-mt-ROMANCE-en", "es": "opus-mt-ROMANCE-en",
             "pt": "opus-mt-ROMANCE-en"}
BATCH = 16
NUM_BEAMS = 4

_models: dict[str, tuple] = {}


def item_code(item: str, posting_items: list[str] | None = None, hint: str | None = None) -> str | None:
    """The language code to translate from, or None to keep the item as written.

    The item's own text where the detector decides, else the posting's: items
    are short and the detector abstains on `Python` or `Teamfähigkeit`. Then
    ``hint``, a language name the caller knows (`Deutsch`), last because the
    export's language field describes the advert, not `must_have`. English,
    and anything undecided, is not translated.

    The batch decides an item once, from the first posting it appears in; here
    it is decided in the posting at hand, so a shared item can differ.
    """
    own = language.detect(item)[0]
    if not own and posting_items:
        own = language.detect(" | ".join(posting_items))[0]
    own = own or hint
    return CODE.get(own) if own else None


def _model(name: str):
    if name not in _models:
        from transformers import MarianMTModel, MarianTokenizer, logging
        logging.set_verbosity_error()   # one length warning per batch, same as the batch run
        _models[name] = (MarianTokenizer.from_pretrained(f"Helsinki-NLP/{name}"),
                         MarianMTModel.from_pretrained(f"Helsinki-NLP/{name}").eval())
    return _models[name]


def cache_key(code: str, text: str) -> str:
    """The batch's key (`translate_must_have._key`), so its cache file can be reused."""
    return hashlib.sha256(f"{code}\x00{text}".encode("utf-8")).hexdigest()[:32]


class TranslationCache:
    """(code, text) -> English, in memory and, with ``path``, in an append-only file.

    Translation is the costliest step and `must_have` items repeat across
    postings, so each one is translated once. The file has the batch's format
    (one JSON line: key, lang, src, out), so `New project/output/translate_cache.jsonl`
    can seed it, and an interrupted run loses nothing already written.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._out: dict[str, str] = {}
        if self.path and self.path.exists():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        self._out[r["key"]] = r["out"]

    def __len__(self) -> int:
        return len(self._out)

    def get(self, code: str, text: str) -> str | None:
        return self._out.get(cache_key(code, text))

    def put(self, done: dict[tuple[str, str], str]) -> None:
        self._out.update({cache_key(c, t): o for (c, t), o in done.items()})
        if self.path and done:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                for (c, t), o in done.items():
                    fh.write(json.dumps({"key": cache_key(c, t), "lang": c, "src": t, "out": o},
                                        ensure_ascii=False) + "\n")


# Used when the caller passes no cache: repeats inside one process are free.
MEMORY = TranslationCache()


def translate(pairs: list[tuple[str, str]], cache: TranslationCache | None = None) -> dict[tuple[str, str], str]:
    """(code, text) -> English, for many items at once; only what the cache lacks is translated."""
    cache = cache if cache is not None else MEMORY
    out: dict[tuple[str, str], str] = {}
    by_model: dict[str, list[tuple[str, str]]] = {}
    for code, text in dict.fromkeys(pairs):
        hit = cache.get(code, text)
        if hit is not None:
            out[(code, text)] = hit
        else:
            by_model.setdefault(MODEL_FOR[code], []).append((code, text))
    if not by_model:
        return out
    import torch
    new: dict[tuple[str, str], str] = {}
    for name, todo in by_model.items():
        tok, mdl = _model(name)
        todo.sort(key=lambda p: len(p[1]))
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            batch = tok([p[1] for p in chunk], return_tensors="pt", padding=True,
                        truncation=True, max_length=256)
            with torch.no_grad():
                gen = mdl.generate(**batch, num_beams=NUM_BEAMS, max_new_tokens=256)
            for p, text in zip(chunk, tok.batch_decode(gen, skip_special_tokens=True)):
                new[p] = text.strip()
    cache.put(new)
    return out | new
