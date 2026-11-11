"""The check: after every job, is the run sound, and what should a person read?

    python -m karimi_normalise.check --job <id>            # one job, after it ends
    python -m karimi_normalise.check --sweep               # every job: find the dead ones
    python -m karimi_normalise.check --reference 0.1.0     # the judge's reference, on our data

Four levels, cheapest first. The first three never correct anything: they
say what they found, and a person changes the rules, with a new version.

1. **health**   — did the run end? A container killed for memory or time
   writes nothing, so its status would say `running` for ever: the Cloud Run
   execution is asked, and a status silent for STALE_MINUTES is dead;
2. **signals**  — the run report's lights (`metrics.run_report`): does the
   run look like the data the quality card was measured on;
3. **judge**    — a sample of the decisions taken BY SIMILARITY (a group at
   cosine 0.90+, a topic at 0.80-0.90, a title found as a variant), each put
   to the calibrated judge (`tester.py`, prompt `v5`) next to the known core
   or role it was placed by. Its "different" share is read against the share
   the same judge gives on our own data (`reference`), with a one-sided
   binomial test: a run is flagged when the judge disagrees with it MORE than
   with ours, not when it disagrees at all;
   With every check the judge also answers `CANARIES`, planted pairs whose
   answer is known: a judge that misses more than CANARY_MAX_MISSES is not
   read, its lights go grey and a yellow finding says why;
4. **drift**    — one line per job in `history/runs.jsonl`, no text: a signal
   off green in the last DRIFT_RUNS jobs in a row is a slow change no single
   run shows.

Thresholds fixed 2026-11-05, BEFORE any reference or run was judged:
red at p < 0.01, yellow at p < 0.05; under MIN_PAIRS pairs of a kind, no
light (too few to read), nor under REF_MIN_PAIRS in the reference (added
after the first reference, before any run: it held 14 title variants);
dead after STALE_MINUTES without progress.

What it writes: `jobs/<id>/check.json` (findings, with the flagged pairs'
text, so it lives and dies with the job's files) and one JSON log line whose
`severity` Cloud Logging reads: ERROR on red. A log-based metric on that line
is what emails you (`deploy/gcp_setup.sh` step 16). The log line carries
codes and counts, never requirement text.

What 50 pairs can say: a share of 10% is known to about +-8 points, so the
judge level sees a large problem or a clear worsening, not two points.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

from . import curator, errors
from .store import jf, now, open_store, read_json, write_json

STALE_MINUTES = 90          # a chunk of 500 postings takes 5-15 minutes; 90 is six chunks of silence
SAMPLE = {"group": 40, "topic": 30, "variant": 20}
REFERENCE_SAMPLE = {"group": 150, "topic": 100, "variant": 60}
MIN_PAIRS = 10
REF_MIN_PAIRS = 30         # added 2026-11-05: the first reference had 14 title variants
P_RED, P_YELLOW = 0.01, 0.05
DRIFT_RUNS = 3
JUDGE_PROMPT = "v5"
JUDGE_NAME = os.environ.get("KARIMI_JUDGE_NAME", "qwen3_4b")
QUESTION = {"group": "strict", "topic": "theme", "variant": "role"}
HISTORY = "history/runs.jsonl"
_ORDER = {"green": 0, "grey": 0, "yellow": 1, "red": 2}

# Planted pairs whose answer is known, put to the judge with every check and
# never counted in its rates. They test the JUDGE, not the run: a judge that
# has stopped working (another model behind the URL, a server answering
# nonsense, a judge that says SAME to everything) would otherwise keep every
# light green. Clear cases on purpose, both answers, all routed to the model
# (`tester.by_code` answers none of them), none taken from the prompt or the
# calibration sources. Checked 2026-11-07: qwen3_4b / v5 answers all 21.
# Fixed the same day, BEFORE any run used them: more than CANARY_MAX_MISSES
# wrong and the judge's lights go grey, with a yellow finding. On GCP the
# answers cache is the execution's own /tmp, so they are asked every time;
# a local run with a warm cache reads them back instead.
CANARIES = [
    # (sample, a, b, the right answer: same?)
    ("group", "project management", "risk management", False),
    ("group", "data visualization", "data protection", False),
    ("group", "driving licence", "willingness to travel", False),
    ("group", "customer support", "software testing", False),
    ("group", "night shift availability", "remote work", False),
    ("group", "communication skills", "skills in communication", True),
    ("group", "attention to detail", "detail-oriented", True),
    ("group", "ability to work independently", "ability to work autonomously", True),
    ("group", "working in a team", "teamwork", True),
    ("topic", "project management", "risk management", False),
    ("topic", "data visualization", "data protection", False),
    ("topic", "remote work", "customer support", False),
    ("topic", "testing", "automated testing", True),
    ("topic", "machine learning", "machine learning models", True),
    ("topic", "cloud security", "security", True),
    ("variant", "Data Analyst", "Data Architect", False),
    ("variant", "Embedded Software Engineer", "Cloud Engineer", False),
    ("variant", "QA Tester", "QA Manager", False),
    ("variant", "Data Scientist", "Data Science Specialist", False),
    ("variant", "ML Engineer", "Machine Learning Engineer", True),
    ("variant", "BI Developer", "Business Intelligence Developer", True),
]
CANARY_MAX_MISSES = 1

# ---------------------------------------------------------------- 1. health


def start_cloud_job(name: str, job: str) -> str:
    """One execution of a Cloud Run Job, told which job it is for through its environment."""
    from google.cloud import run_v2

    o = run_v2.RunJobRequest.Overrides
    op = run_v2.JobsClient().run_job(request=run_v2.RunJobRequest(
        name=name, overrides=o(container_overrides=[o.ContainerOverride(
            env=[run_v2.EnvVar(name="KARIMI_JOB_ID", value=job)])])))
    return getattr(op.metadata, "name", "") or "cloud-run"



def _age_minutes(ts: str | None) -> float | None:
    if not ts:
        return None
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)).total_seconds() / 60


def execution_state(name: str | None) -> dict | None:
    """How a Cloud Run execution ended, or None when there is none to ask."""
    if not name or not name.startswith("projects/"):
        return None
    from google.cloud import run_v2

    ex = run_v2.ExecutionsClient().get_execution(name=name)
    return {"finished": bool(getattr(ex, "completion_time", None)),
            "failed": int(ex.failed_count) + int(ex.cancelled_count) > 0}


def health(s: dict, execution: dict | None = None, alive: bool | None = None) -> dict | None:
    """The change that makes a dead run's status true, or None when it is not dead.

    ``execution``: the Cloud Run execution's end (`execution_state`); ``alive``:
    a local subprocess's (the API's own record). Either beats the clock."""
    if s.get("state") not in ("queued", "running"):
        return None
    if execution and execution["finished"]:
        why = "the run was stopped (memory, time or a crash)" if execution["failed"] else \
              "the run ended without writing its results"
        return {"state": "failed", "error": why, "finished": now()}
    if alive is False:
        return {"state": "failed", "error": "the run process ended without writing its results",
                "finished": now()}
    age = _age_minutes(s.get("updated") or s.get("queued"))
    if age is not None and age > STALE_MINUTES:
        return {"state": "failed", "error": f"no progress for {age:.0f} minutes", "finished": now()}
    return None

# ---------------------------------------------------------------- 3. judge


def pairs_from_results(postings: list[dict]) -> pd.DataFrame:
    """Every decision taken by similarity, as a pair the judge can read."""
    rows = []
    for p in postings:
        for r in p.get("requirements") or []:
            if r.get("match") in ("group", "topic") and r.get("match_via"):
                rows.append({"sample": r["match"], "kind": "requirement", "a": r["core"], "b": r["match_via"],
                             "context": r.get("head_group") or "(no head)", "a_example": r.get("atom", ""),
                             "item": r.get("item", ""), "translated": bool(r.get("translated"))})
        t = p.get("title")
        if t and t.get("match") == "variant" and t.get("title_name"):
            rows.append({"sample": "variant", "kind": "role", "a": t["title_role"], "b": t["title_name"],
                         "context": "", "a_example": t.get("title", ""), "item": t.get("title", ""),
                         "translated": False})
    d = pd.DataFrame(rows, columns=["sample", "kind", "a", "b", "context", "a_example", "item", "translated"])
    return d.drop_duplicates(["sample", "a", "b"]).reset_index(drop=True)


def draw(pairs: pd.DataFrame, sizes: dict, seed: str) -> pd.DataFrame:
    """The same job always draws the same pairs: a re-check asks nothing new."""
    s = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    parts = [g.sample(min(len(g), sizes[k]), random_state=s) for k, g in pairs.groupby("sample")]
    return pd.concat(parts, ignore_index=True) if parts else pairs.iloc[:0]


def judge(pairs: pd.DataFrame, url: str, name: str = JUDGE_NAME) -> pd.DataFrame:
    from . import tester

    d = pairs.assign(id=[f"p{i}" for i in range(len(pairs))], b_example="",
                     question=[QUESTION[k] for k in pairs["sample"]],
                     group=[tester.group(k, a, b) for k, a, b in zip(pairs.kind, pairs.a, pairs.b)])
    a = tester.ask(url, name, JUDGE_PROMPT, d)
    return d.merge(a[["id", "judge_same", "by", "text"]], on="id")


def canary_pairs() -> pd.DataFrame:
    rows = [{"sample": s, "kind": "role" if s == "variant" else "requirement", "a": a, "b": b,
             "context": "" if s == "variant" else "(no head)", "a_example": "", "answer": same}
            for s, a, b, same in CANARIES]
    return pd.DataFrame(rows)


def canary_result(judged: pd.DataFrame) -> dict:
    """How many planted pairs the judge got wrong; unanswered counts as wrong."""
    wrong = judged[judged.judge_same.isna() | (judged.judge_same != judged.answer)]
    return {"pairs": int(len(judged)), "missed": int(len(wrong)), "max_misses": CANARY_MAX_MISSES,
            "trusted": bool(len(wrong) <= CANARY_MAX_MISSES),
            "missed_pairs": wrong[["sample", "a", "b", "answer", "text"]].to_dict("records")}


def rates(judged: pd.DataFrame) -> dict:
    out = {}
    for k, g in judged.groupby("sample"):
        ok = g[g.judge_same.notna()]
        flagged = ok[~ok.judge_same.astype(bool)]
        out[k] = {"pairs": int(len(g)), "answered": int(len(ok)), "flagged": int(len(flagged)),
                  "share": round(len(flagged) / len(ok), 4) if len(ok) else None,
                  "by_code": int((g.by == "code").sum())}
    return out


def binomial_tail(n: int, k: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def judge_light(rate: dict, ref: dict | None) -> tuple[str, float | None]:
    if ref is None or rate["answered"] < MIN_PAIRS or ref.get("answered", 0) < REF_MIN_PAIRS:
        return "grey", None
    # A reference with no flagged pair would make any flag "impossible": floor it.
    p_ref = max(ref["share"] or 0.0, 0.5 / max(ref["answered"], 1))
    p = binomial_tail(rate["answered"], rate["flagged"], p_ref)
    return ("red" if p < P_RED else "yellow" if p < P_YELLOW else "green"), round(p, 4)


def _reference_file() -> Path | None:
    p = os.environ.get("KARIMI_JUDGE_REFERENCE") or (
        str(Path(os.environ["KARIMI_DICT"]) / "judge_reference.json") if os.environ.get("KARIMI_DICT") else None)
    return Path(p) if p and Path(p).exists() else None

# ---------------------------------------------------------------- 4. drift


def _drift(store, line: dict) -> list[dict]:
    old = store.read_text(HISTORY) or ""
    store.write_text(HISTORY, old + json.dumps(line, ensure_ascii=False) + "\n")
    last = [json.loads(x) for x in (old.splitlines() + [json.dumps(line)])[-DRIFT_RUNS:]]
    if len(last) < DRIFT_RUNS:
        return []
    out = []
    for sig in line.get("lights", {}):
        if all(x.get("lights", {}).get(sig, "green") != "green" for x in last):
            out.append({"level": "drift", "light": "yellow", "code": f"drift:{sig}",
                        "what": f"{sig} off green in the last {DRIFT_RUNS} jobs"})
    return out

# ---------------------------------------------------------------- the check


def _log(severity: str, **fields) -> None:
    # One JSON line on stdout: Cloud Logging reads `severity` and keeps the rest
    # as jsonPayload. Codes and counts only.
    print(json.dumps({"severity": severity, **fields}, ensure_ascii=False), flush=True)


def run_detail(report: dict | None, findings: list[dict], judged: dict | None, canaries: dict | None,
               suspects: dict | None) -> dict:
    """What the site shows for ONE run, beside the totals: counts, shares and codes, never text.

    Read off the same objects the check writes to the job's private files, so
    `dashboard.py` can rebuild it from `check.json` and `report.json` for a run
    checked before these fields reached the history (2026-11-09)."""
    return {
        "signals": {k: {"value": v.get("value"), "normal_range": v.get("normal_range"), "light": v.get("light")}
                    for k, v in ((report or {}).get("signals") or {}).items()},
        # `what` is built from a signal name and numbers; a health finding's can
        # carry an exception message, which may quote the input, so it is dropped
        "findings": [{"level": f.get("level"), "light": f.get("light"), "code": f.get("code"),
                      "what": f.get("what") if f.get("level") != "health" else None} for f in findings],
        "judge_detail": {k: {x: v.get(x) for x in ("pairs", "answered", "flagged", "share", "reference_share",
                                                   "light")} for k, v in (judged or {}).items()},
        "canaries": {"pairs": canaries["pairs"], "missed": canaries["missed"]} if canaries else None,
        "split_suspects": {"of": suspects.get("of"), "rows": suspects.get("rows")} if suspects else None,
        "to_check": {k: len(v) if isinstance(v, list) else v
                     for k, v in ((report or {}).get("to_check") or {}).items()},
    }


def check(job: str, store=None, judge_url: str | None = None, reference: dict | None = None) -> dict:
    store = store or open_store()
    s = read_json(store, jf(job, "status.json")) or {"job": job, "state": "unknown"}
    findings: list[dict] = []

    # 1. health
    if s.get("state") != "done":
        findings.append({"level": "health", "light": "red", "code": f"state:{s.get('state')}",
                         "what": s.get("error", f"the run is {s.get('state')}")})
    report = read_json(store, jf(job, "report.json")) if s.get("state") == "done" else None

    # 2. signals
    lights = {}
    for k, v in (report or {}).get("signals", {}).items():
        lights[k] = v["light"]
        if v["light"] in ("red", "yellow"):
            findings.append({"level": "signals", "light": v["light"], "code": f"signal:{k}",
                             "what": f"{k} = {v['value']}, normal {v['normal_range'][0]}-{v['normal_range'][1]}"})

    # 3. judge
    judged, canaries, postings, j = {}, None, None, None
    if report is not None:
        with store.open_read(jf(job, "results.jsonl")) as f:
            postings = [json.loads(x) for x in f if x.strip()]
    if report is not None and judge_url:
        sample = draw(pairs_from_results(postings), SAMPLE, job)
        j = judge(sample, judge_url) if len(sample) else sample.assign(judge_same=None, by="", text="")
        canaries = canary_result(judge(canary_pairs(), judge_url))
        if not canaries["trusted"]:
            findings.append({"level": "judge", "light": "yellow", "code": "judge:canaries",
                             "what": f"the judge got {canaries['missed']} of {canaries['pairs']} planted "
                                     f"pairs wrong: its verdicts on this run are not read"})
        ref = reference if reference is not None else (
            json.loads(_reference_file().read_text(encoding="utf-8")) if _reference_file() else None)
        for k, rate in rates(j).items():
            light, p = judge_light(rate, (ref or {}).get("rates", {}).get(k))
            if not canaries["trusted"]:
                light = "grey"
            judged[k] = {**rate, "reference_share": ((ref or {}).get("rates", {}).get(k) or {}).get("share"),
                         "p": p, "light": light,
                         "flagged_pairs": j[(j["sample"] == k) & (j.judge_same == False)]  # noqa: E712
                         [["a", "b", "context", "text"]].head(10).to_dict("records")}
            if light in ("red", "yellow"):
                findings.append({"level": "judge", "light": light, "code": f"judge:{k}",
                                 "what": f"the judge calls {rate['flagged']} of {rate['answered']} {k} "
                                         f"decisions wrong, against {judged[k]['reference_share']} on our data"})

    # The run's errors: normalisation, on the judge's sample, and only from a
    # judge that passed its planted pairs. Splitting errors are measured per
    # version on hand counts (`errors.py` says why); per run the shape rules
    # only mark suspects, kept here and never counted.
    err = err_examples = suspects = None
    if postings is not None:
        norm = errors.normalise_errors(j) if j is not None and len(j) and canaries["trusted"] else None
        err, err_examples = errors.table(norm), errors.examples(norm)
        sp = errors.split_suspects(postings)
        suspects = {"of": sp["of"], "rows": errors.table(sp)["rows"], "examples": errors.examples(sp)}

    # The curator agent's proposals for this run (`curator.py`), put to the
    # judge only if it passed its planted pairs: otherwise they wait, detected.
    cur = None
    if postings is not None:
        try:
            cur = curator.resolve(store, job, judge_url if canaries and canaries["trusted"] else None)
        except Exception as e:  # noqa: BLE001 - the agent never fails the check
            _log("WARNING", event="karimi_curator_failed", job=job, error=type(e).__name__)

    # 4. drift. The history line carries this run's own verdict (levels 1-3);
    # a drift finding can only add yellow, so it is read off the line, not in it.
    own = max((f["light"] for f in findings), key=_ORDER.get, default="green")
    findings += _drift(store, {"job": job, "checked": now(), "source": s.get("source", "job"),
                               "state": s.get("state"), "overall": own,
                               "postings": s.get("postings_total"),
                               "requirements": ((report or {}).get("summary") or {}).get("requirements"),
                               "seconds": s.get("seconds"), "lights": lights,
                               "judge": {k: v["share"] for k, v in judged.items()},
                               "canaries_missed": canaries["missed"] if canaries else None,
                               "errors": err,
                               **run_detail(report, findings, judged, canaries, suspects),
                               "curator": cur,
                               "rules_version": s.get("rules_version"), "dict_version": s.get("dict_version")})

    overall = max((f["light"] for f in findings), key=_ORDER.get, default="green")
    out = {"job": job, "checked": now(), "overall": overall, "findings": findings, "judge": judged,
           "canaries": canaries, "errors": err, "error_examples": err_examples,
           "split_suspects": suspects, "curator": cur,
           "judge_model": JUDGE_NAME if judge_url else None, "judge_prompt": JUDGE_PROMPT if judge_url else None,
           "to_check": {k: len(v) for k, v in (report or {}).get("to_check", {}).items()},
           "thresholds": {"p_red": P_RED, "p_yellow": P_YELLOW, "min_pairs": MIN_PAIRS, "ref_min_pairs": REF_MIN_PAIRS,
                          "stale_minutes": STALE_MINUTES}}
    write_json(store, jf(job, "check.json"), out)
    _log({"red": "ERROR", "yellow": "WARNING"}.get(overall, "INFO"), event="karimi_check", job=job,
         overall=overall, findings=[f["code"] for f in findings])
    if canaries and not canaries["trusted"]:
        # The run is only yellow, but every later check is blind until a person
        # looks at the judge: this line is what emails (`gcp_setup.sh` step 16).
        _log("ERROR", event="karimi_judge_untrusted", job=job, missed=canaries["missed"],
             pairs=canaries["pairs"])
    return out


def sweep(store=None) -> list[str]:
    """Every job still queued or running is asked whether it is alive; the dead are marked and reported."""
    store = store or open_store()
    dead = []
    for job in store.jobs():
        s = read_json(store, jf(job, "status.json")) or {}
        change = health(s, execution_state(s.get("execution")))
        if change:
            write_json(store, jf(job, "status.json"), {**s, **change, "updated": now()})
            check(job, store)
            dead.append(job)
    _log("INFO", event="karimi_sweep", dead=len(dead))
    return dead

# ---------------------------------------------------------------- reference


def reference(dict_version: str, judge_url: str) -> dict:
    """The judge's "different" share on OUR data, the yardstick of every check.

    The same 90/10 lookup the run-report bands come from (`reference.py`), dev
    postings only: decisions the dictionary took on postings it had not seen,
    exactly as on a user's run. Needs the batch, so it runs here, never on GCP.
    """
    import numpy as np

    from karimi import embed

    from . import reference as rf
    from .freeze import BATCH, HOLDOUT, STORE

    batch, d_dir = Path(BATCH), STORE / dict_version
    manifest = json.loads((d_dir / "manifest.json").read_text(encoding="utf-8"))
    atoms = pd.read_parquet(batch / "must_have_atoms.parquet",
                            columns=["posting_id", "item_idx", "atom", "route", "translated",
                                     "req_head_group", "req_space", "req_core", "req_group", "req_topic"])
    titles = pd.read_parquet(batch / "titles.parquet")
    hold = set(json.loads(Path(HOLDOUT).read_text(encoding="utf-8"))["software_holdout"])
    atoms, titles = atoms[~atoms.posting_id.isin(hold)], titles[~titles.posting_id.isin(hold)]
    phrases, vecs = embed.load_corpus(batch / "core_embeddings.npz")
    idx = {p: i for i, p in enumerate(phrases)}
    cores = atoms.req_core[atoms.req_core.str.strip() != ""].unique()
    v = vecs[[idx[c] for c in cores]].astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    acronyms = json.loads((batch / "titles_summary.json").read_text(encoding="utf-8"))["acronyms_learned"]
    b, d, held = rf.simulated_matches(atoms, titles, dict(zip(cores, v)),
                                      {k: manifest[k] for k in ("dict_version", "group_threshold",
                                                                "topic_threshold")}, acronyms)
    req = b[b.status.isin(["group", "topic"]) & (b.via != "")]
    rows = [{"sample": r.status, "kind": "requirement", "a": r.req_core, "b": r.via,
             "context": r.req_head_group or "(no head)", "a_example": r.atom} for r in req.itertuples()]
    for t in titles[titles.posting_id.isin(held)].itertuples():
        _, _, name, status = d.lookup_title(t.title_role)
        if status == "variant" and name:
            rows.append({"sample": "variant", "kind": "role", "a": t.title_role, "b": name,
                         "context": "", "a_example": t.job_title if hasattr(t, "job_title") else ""})
    pairs = pd.DataFrame(rows).drop_duplicates(["sample", "a", "b"]).reset_index(drop=True)
    j = judge(draw(pairs, REFERENCE_SAMPLE, f"reference-{dict_version}"), judge_url)
    out = {"dict_version": dict_version, "judge_model": JUDGE_NAME, "judge_prompt": JUDGE_PROMPT,
           "made": now(), "made_from": {"held_postings": len(held), "pairs_available":
                                        pairs["sample"].value_counts().to_dict()},
           "rates": rates(j)}
    path = Path(os.environ.get("KARIMI_TESTER_OUT", batch / "tester")) / f"judge_reference_{dict_version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    j.to_csv(path.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"-> {path}")
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    # On Cloud Run the batch job passes the id in the environment (`start_cloud_job`).
    g.add_argument("--job", default=os.environ.get("KARIMI_JOB_ID"))
    g.add_argument("--sweep", action="store_true")
    g.add_argument("--reference", metavar="DICT_VERSION")
    p.add_argument("--judge-url", default=os.environ.get("KARIMI_JUDGE_URL"))
    args = p.parse_args(argv)
    if not (args.job or args.sweep or args.reference):
        p.error("one of --job (or KARIMI_JOB_ID), --sweep, --reference")
    if args.reference:
        print(json.dumps(reference(args.reference, args.judge_url or "http://127.0.0.1:8080")["rates"], indent=2))
    elif args.sweep:
        sweep()
    else:
        # Exit 0 whatever the light: a red run is a finding, not a failed check.
        # The alert comes from the log line, not from the execution failing.
        check(args.job, judge_url=args.judge_url)


if __name__ == "__main__":
    main()
