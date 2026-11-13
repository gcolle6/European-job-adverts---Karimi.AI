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


_RUN = ("job", "checked", "source", "state", "overall", "postings", "requirements", "seconds", "lights", "judge",
        "canaries_missed", "rules_version", "dict_version")
_DETAIL = ("signals", "findings", "judge_detail", "canaries", "split_suspects", "to_check", "curator")


def _with_texts(rows: list[dict] | None) -> list[dict]:
    from .errors import CAUSES, ERRORS

    return [{**r, "error_text": ERRORS.get((r["stage"], r["object"]), {}).get(r["error"], r["error"]),
             "cause_text": CAUSES.get(r["cause"], r["cause"])} for r in rows or []]


def _run(store, r: dict) -> dict:
    """One run as the site shows it: the history line, plus its detail.

    A line written before 2026-11-09 has no detail; it is rebuilt from the
    job's `check.json` and `report.json` through `check.run_detail`, which keeps
    only counts and codes. Splitting suspects are where to look, not errors
    (`errors.py`), and the site says so."""
    out = {k: r.get(k) for k in _RUN}
    detail = {k: r.get(k) for k in _DETAIL}
    if r.get("signals") is None and r.get("job") and r.get("state") == "done":
        from .check import run_detail
        from .store import jf, read_json

        c = read_json(store, jf(r["job"], "check.json")) or {}
        detail = {**run_detail(read_json(store, jf(r["job"], "report.json")), c.get("findings") or [],
                               c.get("judge"), c.get("canaries"), c.get("split_suspects")),
                  "curator": c.get("curator")}
    e = r.get("errors")
    out.update(detail, errors={"of": e.get("of"), "rows": _with_texts(e.get("rows"))} if e else None)
    if out.get("split_suspects"):
        out["split_suspects"] = {**out["split_suspects"], "rows": _with_texts(out["split_suspects"].get("rows"))}
    return _too_small(out)


def _too_small(r: dict) -> dict:
    """A run under the smallest reference size, read as `metrics.run_report` now reads it.

    Lines checked before 2026-11-13 carry signal lights against runs ten times
    their size: the one-posting test of 11/11 was red for one one-word
    requirement in nine. Its signals go grey and stop counting towards the
    run's colour; findings from the judge or the run's state still count."""
    from .check import _ORDER
    from .reference import SIZES

    if r.get("postings") is None or r["postings"] >= SIZES[0] or not r.get("lights"):
        return r
    findings = [f for f in r.get("findings") or [] if f.get("level") != "signals"]
    signals = {k: {**v, "light": "grey"} for k, v in (r.get("signals") or {}).items()} or r.get("signals")
    overall = max((f["light"] for f in findings), key=_ORDER.get, default="green") \
        if r.get("findings") is not None else r.get("overall")
    return {**r, "lights": {k: "grey" for k in r["lights"]}, "signals": signals, "findings": findings,
            "overall": overall}


PENDING_HOURS = 24


def _curator(store) -> dict | None:
    from . import curator

    try:
        return curator.summary(store)
    except Exception:   # noqa: BLE001 - the site shows the rest without it
        return None


def _pending(store, seen: set[str]) -> list[dict]:
    """Runs the check has not reached yet, so a call shows on the site when it ends.

    The history gets a run only when its check is done, minutes later
    (2026-11-10: the user saw Chiara's call missing and took it for a broken
    site). These are read from the job's own `status.json`: counts only, no
    lights, marked ``pending``. Older than PENDING_HOURS, a run the check never
    reached is the sweep's business (`check.sweep`), not the site's."""
    import datetime as dt

    from .store import jf, read_json

    out = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=PENDING_HOURS)
    for job in store.jobs():
        if job in seen:
            continue
        s = read_json(store, jf(job, "status.json")) or {}
        when = s.get("finished") or s.get("updated") or s.get("created")
        try:
            recent = when and dt.datetime.fromisoformat(when) >= cutoff
        except ValueError:
            recent = False
        if not recent or s.get("state") not in ("queued", "running", "done"):
            continue
        out.append({**{k: None for k in _RUN}, "job": job, "checked": when, "source": s.get("source"),
                    "state": s.get("state"), "postings": s.get("postings_total"), "seconds": s.get("seconds"),
                    "rules_version": s.get("rules_version"), "dict_version": s.get("dict_version"),
                    "pending": True})
    return out


def aggregate(store, quality: dict | None, dict_version: str, judge_reference: dict | None = None) -> dict:
    text = store.read_text("history/runs.jsonl") or ""
    runs = [_too_small(json.loads(x)) for x in text.splitlines() if x.strip()]
    done = [r for r in runs if r.get("state") == "done"]
    lights = {}
    for r in runs:
        for k, v in (r.get("lights") or {}).items():
            if v == "grey":
                continue
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
        "agents": {"curator": _curator(store)},
        "runs": _pending(store, {r.get("job") for r in runs}) + [_run(store, r) for r in runs[-LAST:]][::-1],
    }
