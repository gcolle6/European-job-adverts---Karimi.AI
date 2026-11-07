"""Does the output stay put when the employer's wording changes and the meaning does not?

    python "New project/invariance.py"                  # 150 postings, every perturbation
    python "New project/invariance.py" --postings 40 --no-german

A test that needs no labels: each perturbation below leaves the requirement
the same, so the right answer is "the same output as before". Where the
output moves, the library depends on something the employer did not mean.
Same family as the casing defect found in the embedding (CLAUDE.md,
2026-09-11), asked of the whole library instead of one model.

Postings from ``software_dev`` (`datasets.py`): the holdout is not read, and
this prints examples. Many dev items are in the dictionary verbatim, so the
original goes `known`; the perturbed text is no longer verbatim and has to
find its way back through normalisation and the embedding, as new text would.

Perturbations, each applied to every item of a posting:

* ``lower``      — the item in lower case;
* ``punct``      — a bullet in front, a full stop at the end (and, read
  only, ``bullet`` and ``stop``: each half alone);
* ``spaces``     — doubled spaces, a trailing space;
* ``order``      — the posting's items in reverse order (compared item by item);
* ``swap_and``   — English items ending `X and Y`, one word each: `Y and X`;
* ``german``     — English items translated to German (opus-mt-en-de), then
  through the library, which translates them back. This one is a ROUND TRIP:
  a change mixes the en->de model's error with ours, so it bounds the
  library's sensitivity to language from above.

Titles: ``title_lower`` and ``title_punct`` (a trailing ` - ` and a
`(m/f/d)`, as adverts write them).

What is compared, per item: the sorted list of what each requirement became
(its `req_group`, or `match:core` when no group), its atom count, and the set
of groups. Per title: `title_group`.

Reading fixed 2026-11-07, BEFORE the first run: for lower, punct, spaces,
order and the titles, an item changed is a defect, and more than 5% changed
is a defect worth fixing before the next version. swap_and and german have
no threshold: a change there is read, not counted.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import datasets  # noqa: E402

from karimi_normalise import Dictionary, TranslationCache, process  # noqa: E402
from karimi_normalise import translate as tr  # noqa: E402
from karimi_normalise.titles import normalise_title  # noqa: E402

DICT = HERE / "output" / "dictionaries" / "0.1.0"
OUT = HERE / "output" / "invariance"
SEED = 20261107
THRESHOLD = 0.05
COUNTED = ("lower", "punct", "spaces", "order", "title_lower", "title_punct")

_AND = re.compile(r"\b([A-Za-z][\w+#.-]*) and ([A-Za-z][\w+#.-]*)([.;]?)\s*$")


def perturb(kind: str, items: list[str], english: list[bool]) -> list[str] | None:
    """The posting's items, perturbed; None when the perturbation does not apply to any."""
    if kind == "lower":
        return [x.lower() for x in items]
    if kind == "punct":
        return ["- " + x.rstrip() + ("" if x.rstrip().endswith((".", ";", ":")) else ".") for x in items]
    # Its two halves, added after the 5-posting smoke run to say which one moves the output.
    if kind == "bullet":
        return ["- " + x for x in items]
    if kind == "stop":
        return [x.rstrip() + ("" if x.rstrip().endswith((".", ";", ":")) else ".") for x in items]
    if kind == "spaces":
        return [x.replace(" ", "  ") + " " for x in items]
    if kind == "order":
        return items[::-1]
    if kind == "swap_and":
        out = [(_AND.sub(r"\2 and \1\3", x) if en else x) for x, en in zip(items, english)]
        return out if out != items else None
    raise ValueError(kind)


def _german(texts: list[str]) -> dict[str, str]:
    import torch
    from transformers import MarianMTModel, MarianTokenizer, logging
    logging.set_verbosity_error()
    tok = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-de")
    mdl = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-de").eval()
    out, todo = {}, sorted(set(texts), key=len)
    for i in range(0, len(todo), tr.BATCH):
        chunk = todo[i:i + tr.BATCH]
        b = tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=256)
        with torch.no_grad():
            g = mdl.generate(**b, num_beams=tr.NUM_BEAMS, max_new_tokens=256)
        out.update(zip(chunk, (t.strip() for t in tok.batch_decode(g, skip_special_tokens=True))))
    return out


def signature(reqs) -> tuple[tuple, int, frozenset]:
    what = sorted(r.req_group or f"{r.match}:{r.core}" for r in reqs)
    return tuple(what), len(reqs), frozenset(r.req_group for r in reqs if r.req_group)


def by_item(posting_reqs, n_items: int, index: list[int]) -> dict[int, list]:
    """Requirements of each ORIGINAL item index (``index`` maps position -> original)."""
    out = {i: [] for i in range(n_items)}
    for r in posting_reqs:
        out[index[r.item_idx]].append(r)
    return out


def run(postings: list[dict], d, cache) -> list:
    return process([{"id": p["_id"], "must_have": p["items"]} for p in postings], d, cache=cache)["postings"]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--postings", type=int, default=150)
    ap.add_argument("--no-german", action="store_true")
    ap.add_argument("--only", nargs="*", help="perturbations to run (default all); writes no summary")
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    # A copy of the batch's translations: perturbed text adds its own, and the
    # batch's file stays as the batch left it.
    cache_file = OUT / "translate_cache.jsonl"
    if not cache_file.exists():
        shutil.copy(HERE / "output" / "translate_cache.jsonl", cache_file)
    cache = TranslationCache(cache_file)
    d = Dictionary(DICT)

    rows = [r for r in datasets.load("software_dev") if r.get("must_have")]
    random.Random(SEED).shuffle(rows)
    sample = [{"_id": r["_id"], "items": [x for x in r["must_have"] if x and x.strip()],
               "title": r.get("job_title_english") or r.get("job_title") or ""} for r in rows[:args.postings]]
    sample = [p for p in sample if p["items"]]
    english = [[tr.item_code(x, p["items"]) is None for x in p["items"]] for p in sample]
    n_items = sum(len(p["items"]) for p in sample)
    print(f"{len(sample)} postings, {n_items} items, {sum(map(sum, english))} English")

    t0 = time.time()
    base = run(sample, d, cache)
    print(f"original: {time.time() - t0:.0f}s")
    base_by = [by_item(b["requirements"], len(p["items"]), list(range(len(p["items"]))))
               for b, p in zip(base, sample)]

    changes, summary = [], {}

    def compare(kind: str, out, applied: list[list[bool]], index: list[list[int]], shown: list[list[str]]):
        c = Counter()
        for k, (o, p) in enumerate(zip(out, sample)):
            got = by_item(o["requirements"], len(p["items"]), index[k])
            for i in range(len(p["items"])):
                if not applied[k][i]:
                    continue
                a, b = signature(base_by[k][i]), signature(got[i])
                c["items"] += 1
                c["same"] += a[0] == b[0]
                lang = "english" if english[k][i] else "other"
                c[f"{lang}_items"] += 1
                c[f"{lang}_same"] += a[0] == b[0]
                c["same_count"] += a[1] == b[1]
                c["same_groups"] += a[2] == b[2]
                if a[0] != b[0]:
                    changes.append({"perturbation": kind, "posting": p["_id"], "item": p["items"][i],
                                    "perturbed": shown[k][i], "before": " | ".join(a[0]),
                                    "after": " | ".join(b[0]), "atoms_before": a[1], "atoms_after": b[1]})
        n = c["items"] or 1
        summary[kind] = {"items": c["items"], "changed": c["items"] - c["same"],
                         "changed_share": round(1 - c["same"] / n, 4),
                         "count_changed_share": round(1 - c["same_count"] / n, 4),
                         "groups_changed_share": round(1 - c["same_groups"] / n, 4),
                         **{f"{lang}_changed_share": round(1 - c[f"{lang}_same"] / c[f"{lang}_items"], 4)
                            for lang in ("english", "other") if c[f"{lang}_items"]},
                         "threshold": THRESHOLD if kind in COUNTED else None}
        s = summary[kind]
        print(f"{kind:12} {s['items']:5} items  output changed {s['changed_share']:.1%}  "
              f"(English {s.get('english_changed_share', 0):.1%}, other {s.get('other_changed_share', 0):.1%})  "
              f"count {s['count_changed_share']:.1%}  groups {s['groups_changed_share']:.1%}")

    for kind in ("lower", "punct", "bullet", "stop", "spaces", "order", "swap_and"):
        if args.only and kind not in args.only:
            continue
        t0 = time.time()
        pert = [perturb(kind, p["items"], en) for p, en in zip(sample, english)]
        use = [k for k, x in enumerate(pert) if x is not None]
        if not use:
            continue
        sub = [{**sample[k], "items": pert[k]} for k in use]
        out = dict(zip(use, run(sub, d, cache)))
        full = [out.get(k, {"requirements": []}) for k in range(len(sample))]
        applied = [[pert[k] is not None and (kind != "swap_and" or pert[k][i] != sample[k]["items"][i])
                    for i in range(len(sample[k]["items"]))] for k in range(len(sample))]
        n = [len(p["items"]) for p in sample]
        index = [list(range(m))[::-1] if kind == "order" else list(range(m)) for m in n]
        shown = [[(pert[k] or sample[k]["items"])[index[k].index(i)] for i in range(n[k])] for k in range(len(sample))]
        compare(kind, full, applied, index, shown)
        print(f"  ({time.time() - t0:.0f}s)")

    if args.only:
        return
    if not args.no_german:
        t0 = time.time()
        de = _german([x for p, en in zip(sample, english) for x, e in zip(p["items"], en) if e])
        pert = [[de[x] if e else x for x, e in zip(p["items"], en)] for p, en in zip(sample, english)]
        # The German text is announced as German, as an employer's German advert would be.
        out = process([{"id": p["_id"], "must_have": q, "language": "Deutsch"} for p, q in zip(sample, pert)],
                      d, cache=cache)["postings"]
        n = [len(p["items"]) for p in sample]
        compare("german", out, english, [list(range(m)) for m in n], pert)
        print(f"  ({time.time() - t0:.0f}s)")

    # Titles: one per posting.
    for kind, f in (("title_lower", str.lower), ("title_punct", lambda t: t.rstrip() + " (m/f/d) - ")):
        c = Counter()
        for p in sample:
            if not p["title"]:
                continue
            a, b = normalise_title(p["title"], d), normalise_title(f(p["title"]), d)
            c["items"] += 1
            if a.title_group == b.title_group:
                c["same"] += 1
            else:
                changes.append({"perturbation": kind, "posting": p["_id"], "item": p["title"],
                                "perturbed": f(p["title"]), "before": a.title_group or f"{a.match}:{a.title_role}",
                                "after": b.title_group or f"{b.match}:{b.title_role}"})
        n = c["items"] or 1
        summary[kind] = {"items": c["items"], "changed": c["items"] - c["same"],
                         "changed_share": round(1 - c["same"] / n, 4), "threshold": THRESHOLD}
        print(f"{kind:12} {c['items']:5} titles output changed {summary[kind]['changed_share']:.1%}")

    for k, s in summary.items():
        s["passes"] = None if s["threshold"] is None else s["changed_share"] <= s["threshold"]
    from karimi_normalise.versions import RULES_VERSION
    meta = {"postings": len(sample), "items": n_items, "seed": SEED, "set": "software_dev",
            "rules_version": RULES_VERSION, "dict_version": d.version, "summary": summary}
    (OUT / "summary.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    pd.DataFrame(changes).to_csv(OUT / "changes.csv", index=False, encoding="utf-8-sig")
    print(f"-> {OUT / 'summary.json'}, {len(changes)} changes in {OUT / 'changes.csv'}")


if __name__ == "__main__":
    main()
