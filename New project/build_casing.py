"""The capitals each language writes, read off the employers' own items.

    python "New project/build_casing.py"      # -> karimi_normalise/casing.json

`requirements.clean_item` gives an item with no capital at all its capitals
back. In English the dictionary's cores are enough (`Dictionary.casing`); in
German they are not, because German writes every noun with a capital and the
translator reads it: `praktische erfahrung mit llms und generativer ki` comes
back with `ki` untranslated. So each language's map is built here from the
items as employers wrote them, `software_dev` only.

Same rule as `dictionary.casing`, thresholds fixed with it on 2026-11-07: a
word is kept when, outside the first position of an item, at least 90% of its
5+ occurrences carry capitals. Words of one letter are left out. The language
of an item is decided as the library decides it (`translate.item_code`, the
posting as context); English and undecided items are not used (see `main`).

Words only, no item text: the file is vocabulary, shipped with the rules and
covered by the fingerprint, so a change to it is a new rules version.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import datasets  # noqa: E402

from karimi_normalise import translate as tr  # noqa: E402
from karimi_normalise.dictionary import CASING_MIN_N, CASING_MIN_SHARE  # noqa: E402
from karimi.normalise_req import _NAME_TOKEN  # noqa: E402

OUT = HERE.parent / "karimi_normalise" / "casing.json"


def main() -> None:
    forms: dict[str, dict[str, dict[str, int]]] = {}
    for r in datasets.load("software_dev"):
        items = [x for x in r.get("must_have") or [] if x and x.strip()]
        for it in items:
            code = tr.item_code(it, items) or "en"
            lang = forms.setdefault(code, {})
            for i, tok in enumerate(_NAME_TOKEN.findall(it)):
                if i == 0 or len(tok) < 2 or not any(ch.isalpha() for ch in tok):
                    continue
                f = lang.setdefault(tok.lower(), {})
                f[tok] = f.get(tok, 0) + 1
    out = {}
    # English is left to the dictionary's cores. Read off whole items it maps
    # `it` -> `IT` and `go` -> `Go`: software adverts name the IT department and
    # the Go language more often than they write the pronoun and the verb
    # mid-item, and a lower-case `make it happen` would come back with a name.
    # The cores have the frame words stripped, so the pronoun never gets there.
    forms.pop("en", None)
    for code, words in sorted(forms.items()):
        m = {}
        for low, f in words.items():
            n = sum(f.values())
            best, k = max(f.items(), key=lambda x: x[1])
            if n >= CASING_MIN_N and best != low and k / n >= CASING_MIN_SHARE:
                m[low] = best
        out[code] = dict(sorted(m.items()))
        print(f"{code}: {len(m):,} words")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
