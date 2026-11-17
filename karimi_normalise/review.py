"""A person's review of a run: the human label every agent is measured against.

The check's colour counts the errors the inspector knows and estimates the
rest of the normalisation from the judge's sample; splitting errors and kinds
nobody has named are in neither (`check.error_estimate`). So "we found X
errors" could not be said of any run. Asked 2026-11-16: the project lead
reviews a random sample of a run on the Metrics page, signed in (`api.py`,
/v1/admin), and that label is the measure.

* **the sample**: SIZE items drawn at random from the whole run, seeded by the
  job, so it is the same sample whenever it is opened. Drawn once and kept
  (`sample.json`), with what each agent said of each item, which the reviewer
  never sees: a label given knowing the agents' verdict would measure them
  against themselves;
* **the label**: each item correct or incorrect, as a whole (the split, the
  keys, the translation), with an optional note. At least MIN_LABELS before it
  can be sent; sent again with more, the latest replaces it, and every
  submission is kept;
* **the measure**: the share of items wrong with its 95% interval (Wilson),
  and each agent against it: how many of the inspector's flagged items were
  wrong (precision) and how many wrong items it flagged (recall); the check's
  own estimate beside the person's figure.

Items are shown in their drawn order and the label says whether the ones
labelled are the first N: skipping the hard ones would make a run look better
than it is. What leaves the job's files is counts; items and notes never do.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict

from .store import jf, now, read_json, write_json

SIZE = 100
MIN_LABELS = 50
VERDICTS = ("correct", "incorrect")


def _sample_path(job: str) -> str:
    return f"reviews/{job}/sample.json"


def _labels_path(job: str) -> str:
    return f"reviews/{job}/labels.jsonl"


def draw(postings: list[dict], job: str, n: int = SIZE) -> list[dict]:
    """SIZE items of the run at random, each with what the run made of it and,
    privately, what the inspector and the explorer said."""
    from .errors import inspector_flag

    items = []
    for p in postings:
        by_item: dict[int, list[dict]] = defaultdict(list)
        for r in p.get("requirements") or []:
            by_item[r.get("item_idx", 0)].append(r)
        for idx, rs in sorted(by_item.items()):
            items.append({"posting": str(p.get("id", "")), "item_idx": idx, "item": rs[0].get("item", ""),
                          "english": rs[0].get("item_split") if rs[0].get("translated") else None,
                          "made": [{"atom": r.get("atom", ""), "key": r.get("key", ""),
                                    "counted": bool(r.get("counted", True))} for r in rs],
                          "inspector": sorted({f for f in (inspector_flag(r) for r in rs) if f})})
    rnd = random.Random(f"review:{job}")
    picked = rnd.sample(items, min(n, len(items)))
    return [{"n": k, **it} for k, it in enumerate(picked)]


def sample(store, job: str) -> list[dict]:
    """The run's sample, drawn on first use and kept."""
    kept = read_json(store, _sample_path(job))
    if kept is not None:
        return kept["items"]
    with store.open_read(jf(job, "results.jsonl")) as f:
        postings = [json.loads(x) for x in f if x.strip()]
    items = draw(postings, job)
    write_json(store, _sample_path(job), {"job": job, "drawn": now(), "size": len(items), "items": items})
    return items


def for_reviewer(items: list[dict]) -> list[dict]:
    """What the reviewer sees: the item and what was made of it, never an agent's verdict."""
    return [{k: it[k] for k in ("n", "item", "english", "made")} for it in items]


def submissions(store, job: str) -> list[dict]:
    text = store.read_text(_labels_path(job)) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def submit(store, job: str, labels: list[dict], by: str) -> dict:
    """Keep a person's labels; at least MIN_LABELS, each on an item of the sample."""
    items = {it["n"]: it for it in sample(store, job)}
    seen, clean = set(), []
    for lab in labels:
        n, verdict = lab.get("n"), lab.get("verdict")
        if n not in items or verdict not in VERDICTS or n in seen:
            raise ValueError(f"label {lab!r}: an item of the sample, once, correct or incorrect")
        seen.add(n)
        clean.append({"n": n, "verdict": verdict, "note": str(lab.get("note") or "")[:1000]})
    if len(clean) < min(MIN_LABELS, len(items)):
        raise ValueError(f"at least {MIN_LABELS} items, {len(clean)} labelled")
    line = {"job": job, "by": by, "at": now(), "count": len(clean), "labels": sorted(clean, key=lambda x: x["n"])}
    old = store.read_text(_labels_path(job)) or ""
    store.write_text(_labels_path(job), old + json.dumps(line, ensure_ascii=False) + "\n")
    return score(store, job)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def score(store, job: str) -> dict | None:
    """The latest review of a run, measured: the person's figure and each agent against it. Counts only."""
    subs = submissions(store, job)
    if not subs:
        return None
    last = subs[-1]
    items = {it["n"]: it for it in sample(store, job)}
    labs = [lab for lab in last["labels"] if lab["n"] in items]
    wrong = {lab["n"] for lab in labs if lab["verdict"] == "incorrect"}
    done = {lab["n"] for lab in labs}
    flagged = {n for n in done if items[n]["inspector"]}
    prefix = next((k for k in range(len(items) + 1) if k not in done), len(items))
    check = read_json(store, jf(job, "check.json")) or {}
    est = check.get("error_estimate") or {}
    return {
        "job": job, "at": last["at"], "submissions": len(subs), "labelled": len(labs), "of": len(items),
        "in_order": prefix == len(labs),
        "incorrect": len(wrong), "share_incorrect": _rate(len(wrong), len(labs)),
        "ci95": wilson(len(wrong), len(labs)),
        "inspector": {"flagged": len(flagged), "flagged_incorrect": len(flagged & wrong),
                      "precision": _rate(len(flagged & wrong), len(flagged)),
                      "recall": _rate(len(flagged & wrong), len(wrong))},
        # the check counts requirements, the person items: shown side by side, not as one figure
        "check_estimate": est.get("share"), "check_light": est.get("light"),
    }


def summary(store, jobs: list[str]) -> dict:
    """What the site shows: every reviewed run among ``jobs``, and the reviews pooled."""
    reviews = [s for s in (score(store, j) for j in jobs if store.exists(_labels_path(j))) if s]
    lab = sum(r["labelled"] for r in reviews)
    wrong = sum(r["incorrect"] for r in reviews)
    fl = sum(r["inspector"]["flagged"] for r in reviews)
    tp = sum(r["inspector"]["flagged_incorrect"] for r in reviews)
    return {"size": SIZE, "min_labels": MIN_LABELS, "reviews": reviews[::-1],
            "pooled": {"labelled": lab, "incorrect": wrong, "share_incorrect": _rate(wrong, lab),
                       "ci95": wilson(wrong, lab),
                       "inspector_precision": _rate(tp, fl), "inspector_recall": _rate(tp, wrong)}}
