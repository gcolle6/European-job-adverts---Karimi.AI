"""What the public site shows: aggregates over every run, never a requirement.

    GET /v1/metrics            (no key: the site fetches it from the browser)

Built from `history/runs.jsonl` (one line per checked run, written by
`check.py`), the quality card of the version in service, and the judge's
reference. Counts, shares, lights and versions only. The site is a reader of
this one object; whatever it draws, it draws from here.
"""

from __future__ import annotations

import json

from .store import now
from .versions import RULES_VERSION

LAST = 60


def _quality_summary(q: dict | None) -> dict | None:
    if not q:
        return None
    s = q.get("split_count", {}).get("blind_half", {})
    pairs = q.get("pairs", {}).get("blind", {})
    lv = (q.get("lookup_vs_batch") or {}).get("by_match", {})

    def rate(cell):
        return round(cell["errors"] / cell["pairs"], 4) if cell and cell.get("pairs") else None

    return {
        "generated": q.get("generated"), "release": q.get("release"),
        "tests_passed": q.get("tests", {}).get("passed"), "tests_total": q.get("tests", {}).get("total"),
        "split_exact": s.get("exact"), "split_exact_ci95": s.get("exact_ci95"), "split_items": s.get("items"),
        "requirement_wrong_merges": rate(pairs.get("requirement_group", {}).get("merged")),
        "requirement_missed_merges": rate(pairs.get("requirement_group", {}).get("apart")),
        "role_wrong_merges": rate(pairs.get("role", {}).get("merged")),
        "role_missed_merges": rate(pairs.get("role", {}).get("apart")),
        "lookup_group_agrees": (lv.get("group") or {}).get("same_group"),
        "lookup_topic_agrees": (lv.get("topic") or {}).get("same_topic"),
        "parity_with_batch": (q.get("parity_with_batch") or {}).get("share_identical"),
    }


def _error_table(counts: dict, of: dict, runs: int, split: dict | None) -> dict:
    """The error table, each row with the denominator it is a share of.

    Normalisation: every run's judged errors summed, out of the decisions the
    judge was shown, per object. Splitting: the version's own measure on the
    hand-counted items (``split``, `score_split_errors.py` via the quality
    card), out of those items; `errors.py` says why it is not per run."""
    from .errors import CAUSES, ERRORS

    counts = dict(counts)
    for row in (split or {}).get("rows") or []:
        counts[(row["stage"], row["object"], row["error"], row["cause"])] = row["count"]
    denominator = {("splitting", "requirement"): ((split or {}).get("of") or {}).get("items_hand_counted", 0),
                   ("normalisation", "requirement"): of.get("judged_requirements", 0),
                   ("normalisation", "role"): of.get("judged_roles", 0)}
    rows = []
    for (stage, obj, error, cause), n in sorted(counts.items(), key=lambda x: -x[1]):
        d = denominator.get((stage, obj), 0)
        rows.append({"stage": stage, "object": obj, "error": error,
                     "error_text": ERRORS.get((stage, obj), {}).get(error, error),
                     "cause": cause, "cause_text": CAUSES.get(cause, cause),
                     "count": n, "of": d, "share": round(n / d, 4) if d else None})
    return {"runs": runs, "of": {**of, "items_hand_counted": denominator[("splitting", "requirement")]},
            "rows": rows, "splitting": {k: (split or {}).get(k) for k in ("rules_version", "per_run_instruments")}
            if split else None}


def aggregate(store, quality: dict | None, dict_version: str, judge_reference: dict | None = None) -> dict:
    text = store.read_text("history/runs.jsonl") or ""
    runs = [json.loads(x) for x in text.splitlines() if x.strip()]
    done = [r for r in runs if r.get("state") == "done"]
    lights = {}
    for r in runs:
        for k, v in (r.get("lights") or {}).items():
            lights.setdefault(k, {"green": 0, "yellow": 0, "red": 0})
            lights[k][v] = lights[k].get(v, 0) + 1
    errors, of, with_errors = {}, {}, 0
    for r in done:
        e = r.get("errors")
        if not e:
            continue
        with_errors += 1
        for k, v in (e.get("of") or {}).items():
            of[k] = of.get(k, 0) + (v or 0)
        for row in e.get("rows") or []:
            key = (row["stage"], row["object"], row["error"], row["cause"])
            errors[key] = errors.get(key, 0) + row["count"]
    judge = {}
    for r in done:
        for k, v in (r.get("judge") or {}).items():
            if v is not None:
                judge.setdefault(k, []).append(v)
    return {
        "generated": now(),
        "versions": {"rules_version": RULES_VERSION, "dict_version": dict_version},
        "quality": _quality_summary(quality),
        "judge_reference": {k: v.get("share") for k, v in (judge_reference or {}).get("rates", {}).items()}
        if judge_reference else None,
        "totals": {
            "runs": len(runs), "runs_done": len(done), "runs_failed": sum(r.get("state") == "failed" for r in runs),
            "postings": sum(r.get("postings") or 0 for r in done),
            "requirements": sum(r.get("requirements") or 0 for r in done),
            "overall": {c: sum(r.get("overall") == c for r in runs) for c in ("green", "yellow", "red")},
        },
        "signals": lights,
        "judge": {k: {"runs": len(v), "mean_flagged_share": round(sum(v) / len(v), 4)} for k, v in judge.items()},
        "errors": _error_table(errors, of, with_errors, (quality or {}).get("split_errors")),
        "runs": [{k: r.get(k) for k in ("job", "checked", "source", "state", "overall", "postings", "requirements",
                                        "seconds", "lights", "judge", "canaries_missed", "rules_version",
                                        "dict_version")}
                 for r in runs[-LAST:]][::-1],
    }
