"""Can a language model find what the pipeline got wrong? The explorer measured before it is trusted.

    python "New project/score_explorer.py" counts --half read  --llm local    # the prompt is worked on here
    python "New project/score_explorer.py" counts --half blind --llm local    # read once per prompt version
    python "New project/score_explorer.py" batch1 --llm vertex                # known errors, development batch

Two tests, both fixed 2026-11-16 before any model answered:

* **counts** — the 115 items counted by hand (`score_counts.py` halves). The
  library's split is wrong where its count differs from the human's. Of the
  items the explorer says were SPLIT wrong, at least MIN_FLAG_PRECISION must
  be (the bar of 2026-11-07, which the local judge failed at 28% and 21%).
  On the blind half only aggregates are printed;
* **batch1** — batch 1 of the new postings as the API returned it (rules
  0.4.1, the development batch: its text may be read). Items the inspector
  flagged hold a known error: how many the explorer finds unaided. Items it
  did not flag: what the explorer calls wrong there is written out to be read
  by a person, since that is where a NEW kind would show.

Models (the user's call, 2026-11-16: measure both, then choose): ``local``, an
open model behind llama-server; ``vertex``, Gemini on Vertex AI's regional
endpoint in europe-west1, token from gcloud.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from karimi_normalise import Dictionary, TranslationCache, errors, explorer, split_posting  # noqa: E402
from karimi_normalise.freeze import STORE  # noqa: E402
from karimi_normalise.quality import QUALITY  # noqa: E402
from karimi_normalise.versions import RULES_VERSION  # noqa: E402

MIN_FLAG_PRECISION = 0.60
SEED = 20261116
OUT = HERE / "output" / "explorer"
# The EU multi-region, served from the EU's own host: on 2026-11-16 this new
# project could reach no Gemini model in europe-west1 or any other single EU
# region (404, older models are closed to new projects), and only
# gemini-3.5-flash here. Never `global`, and never europe-west2 (London).
PROJECT, REGION, HOST = "karimi-normalise-2026", "eu", "aiplatform.eu.rep.googleapis.com"


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def _client(llm: str, model: str | None) -> tuple[explorer.Client, str]:
    if llm == "local":
        url = os.environ.get("KARIMI_EXPLORER_URL", "http://127.0.0.1:8081/v1")
        name = model or "qwen3-14b"
        # Qwen3 thinks aloud unless told not to; the answer is parsed after it
        return explorer.Client(url, name, extra={"chat_template_kwargs": {"enable_thinking": False}}), name
    name = model or "google/gemini-3.5-flash"
    sdk = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Cloud SDK" / "google-cloud-sdk"
    cmd = [str(sdk / "platform" / "bundledpython" / "python.exe"), str(sdk / "lib" / "gcloud.py"),
           "auth", "print-access-token"]
    cache = {"t": None, "at": 0.0}

    def token() -> str:
        if time.time() - cache["at"] > 1800:
            cache["t"] = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
            cache["at"] = time.time()
        return cache["t"]

    url = f"https://{HOST}/v1/projects/{PROJECT}/locations/{REGION}/endpoints/openapi"
    return explorer.Client(url, name, token=token), name


def _reqs(items: list[str], d, cache) -> list[dict]:
    out = []
    for it in items:
        rs = [dataclasses.asdict(q) for q in split_posting([it], d, cache=cache)]
        out.append({"item": it, "english": rs[0]["item_split"] if rs and rs[0]["translated"] else None,
                    "requirements": rs})
    return out


def counts(args, client, name) -> dict:
    import score_counts

    rows = score_counts.load()
    score_counts.halves(rows)
    rows = [r for r in rows if r["n"] is not None and r["half"] == args.half]
    d = Dictionary(STORE / args.dict)
    cache = TranslationCache(HERE / "output" / "translate_cache.jsonl")
    items = _reqs([r["item"] for r in rows], d, cache)
    answers = explorer.read(client, items)
    lib = [sum(q["counted"] for q in it["requirements"]) for it in items]
    human = [r["n"] for r in rows]
    wrong = [lib[k] != human[k] for k in range(len(rows))]
    answered = [k for k, a in enumerate(answers) if a is not None]
    split_flag = [k for k in answered if any(p.get("stage") == "split" for p in answers[k]["problems"])]
    any_flag = [k for k in answered if not answers[k]["ok"]]
    out = {"test": "counts", "half": args.half, "model": name, "prompt": explorer.PROMPT_VERSION,
           "rules_version": RULES_VERSION, "items": len(rows), "answered": len(answered),
           "library_wrong": sum(wrong[k] for k in answered),
           "split_flags": len(split_flag),
           "split_flag_precision": _rate(sum(wrong[k] for k in split_flag), len(split_flag)),
           "split_flag_recall": _rate(sum(wrong[k] for k in split_flag), sum(wrong[k] for k in answered)),
           "any_flags": len(any_flag), "min_flag_precision": MIN_FLAG_PRECISION}
    out["passes"] = out["split_flag_precision"] is not None and out["split_flag_precision"] >= MIN_FLAG_PRECISION
    if args.half == "read":      # the read half may be looked at, item by item
        _write(f"counts_read_{_slug(name)}.jsonl",
               [{**items[k], "human": human[k], "library": lib[k], "answer": answers[k]} for k in range(len(rows))])
    return out


def batch1(args, client, name) -> dict:
    path = HERE / "output" / "new_postings" / "batch_01" / "results.jsonl"
    posts = [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()]
    by_item: dict[tuple, list[dict]] = {}
    for p in posts:
        for r in p.get("requirements") or []:
            by_item.setdefault((p["id"], r["item_idx"]), []).append(r)
    flagged, clean = [], []
    for key, rs in by_item.items():
        kinds = [f for f in (errors.inspector_flag(r) for r in rs) if f]
        (flagged if kinds else clean).append((key, rs, kinds))
    rnd = random.Random(SEED)
    sample = rnd.sample(flagged, min(args.n, len(flagged))) + rnd.sample(clean, min(args.n, len(clean)))
    items = [{"item": rs[0]["item"], "english": rs[0]["item_split"] if rs[0]["translated"] else None,
              "requirements": rs} for _, rs, _ in sample]
    answers = explorer.read(client, items)
    rows, found, kind_right, clean_flags = [], 0, 0, 0
    nf = min(args.n, len(flagged))
    for k, ((_, _, kinds), it, a) in enumerate(zip([s for s in sample], items, answers)):
        if a is None:
            continue
        if k < nf:
            found += not a["ok"]
            kind_right += any(p.get("kind") in kinds for p in a["problems"])
        else:
            clean_flags += not a["ok"]
        rows.append({**it, "inspector": kinds, "answer": a})
    _write(f"batch1_{_slug(name)}.jsonl", rows)
    n_clean = len(sample) - nf
    return {"test": "batch1", "model": name, "prompt": explorer.PROMPT_VERSION, "rules_version": "0.4.1",
            "known_errors": nf, "found": _rate(found, nf), "named_with_the_known_kind": _rate(kind_right, nf),
            "clean_items": n_clean, "clean_items_flagged": _rate(clean_flags, n_clean),
            "to_read": f"output/explorer/batch1_{_slug(name)}.jsonl"}


def _slug(s: str) -> str:
    return s.replace("/", "_").replace(":", "_")


def _write(name: str, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("test", choices=["counts", "batch1"])
    ap.add_argument("--llm", choices=["local", "vertex"], required=True)
    ap.add_argument("--model")
    ap.add_argument("--half", choices=["read", "blind"], default="read")
    ap.add_argument("--dict", default="0.3.2")
    ap.add_argument("--n", type=int, default=40, help="batch1: items with a known error, and as many without")
    args = ap.parse_args(argv)
    client, name = _client(args.llm, args.model)
    t0 = time.time()
    out = counts(args, client, name) if args.test == "counts" else batch1(args, client, name)
    out["seconds"] = round(time.time() - t0)
    QUALITY.mkdir(parents=True, exist_ok=True)
    path = QUALITY / f"explorer_{args.test}_{args.half if args.test == 'counts' else 'dev'}_{_slug(name)}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
