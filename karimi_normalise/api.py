"""The library over HTTP: FastAPI, on Cloud Run in an EU region.

    KARIMI_DICT=<dictionary folder> KARIMI_STORE=./jobs uvicorn karimi_normalise.api:app --workers 1

Reopened 2026-11-05 next to the library, not in its place: a few dollars of
compute a month for 100,000 requirements (estimated from the measured rate in
`job.py`) makes the cost no reason to refuse it. Every answer is
`process()`'s, so the API and the library cannot disagree.

Two ways in:

* `POST /v1/process` — up to MAX_SYNC postings, the answer at once;
* `/v1/jobs`         — a large run. Open a job, upload the postings as JSONL
  to the URL it returns, start it, ask for its status, fetch the result. On
  GCP the upload and the result are signed bucket URLs and the run is the
  Cloud Run Job `karimi_normalise.job`; locally they are this API and a
  subprocess, so the whole path is tried on one machine first.

Every call is kept and checked. A `/v1/process` call is stored like a job
(`source: process`): results, report, the two CSV tables, and then the check
(`check.py`) runs on it as on a job, so every answer the API ever gave has a
verdict in `history/runs.jsonl`, which `GET /v1/metrics` aggregates for the
site. Nothing in that aggregate is requirement text.

Access, decided 2026-11-05 for the trial: an API key in the `X-API-Key`
header, compared with `KARIMI_API_KEY` (a Secret Manager secret on Cloud
Run). Simpler for the caller than a Google identity; to be replaced by IAM if
the service becomes permanent. Unset locally = no check. `/health`, `/docs`
and `/v1/metrics` are open: the last is what the site reads from the browser.

Settings, all by environment:

* `KARIMI_DICT`       the dictionary folder baked into the image;
* `KARIMI_QUALITY`    the quality card made for it (`quality.py`);
* `KARIMI_STORE`      a local folder or `gs://<bucket>` (`store.py`);
* `KARIMI_RUN_JOB`    `projects/<p>/locations/<region>/jobs/<name>`; unset = a subprocess;
* `KARIMI_RUN_CHECK`  the check job the same way; unset = a subprocess;
* `KARIMI_API_KEY`    the key; unset = open.

One worker per container: the rules keep module-level state, so scaling is by
containers, not threads (Cloud Run `--concurrency=1`). Every request leaves
one JSON log line (method, path, status, milliseconds, counts; no text) that
Cloud Logging indexes, with the trace id Cloud Run gives it.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from . import Dictionary, check, dashboard, exports, normalise_title, process
from .store import LocalStore, jf, now, open_store, read_json, write_json
from .versions import RULES_VERSION

MAX_SYNC = 200                 # postings per /v1/process call; more goes to a job
MAX_UPLOAD_MB = 30             # Cloud Run caps a request body at 32 MiB
FILES = ("results.jsonl", "report.json", "status.json", "check.json", "requirements.csv", "postings.csv")
OPEN = ("/health", "/docs", "/openapi.json", "/redoc", "/v1/metrics")
_JOB_ID = re.compile(r"^[0-9a-f]{16}$")

app = FastAPI(title="karimi-normalise", version=RULES_VERSION,
              description="Split job-ad must_have lists into single requirements; normalise requirements and titles.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
_dict = Dictionary(os.environ["KARIMI_DICT"]) if os.environ.get("KARIMI_DICT") else None
_quality = (json.loads(Path(os.environ["KARIMI_QUALITY"]).read_text(encoding="utf-8"))
            if os.environ.get("KARIMI_QUALITY") and Path(os.environ["KARIMI_QUALITY"]).exists() else None)
_judge_ref = (json.loads(check._reference_file().read_text(encoding="utf-8")) if check._reference_file() else None)
_store = open_store()
_procs: dict[str, subprocess.Popen] = {}     # local runs only: on GCP, Cloud Run knows


class Posting(BaseModel):
    must_have: list[str]
    title: str | None = None
    id: str | int | None = None
    language: str | None = Field(None, description="fallback for very short items, e.g. `Deutsch`")
    must_have_english: list[str] | None = Field(None, description="your own translation, aligned with must_have")

    model_config = {"extra": "allow"}        # other scalar fields travel through to postings.csv


class Run(BaseModel):
    postings: list[Posting]
    translate: bool = True


class JobOptions(BaseModel):
    translate: bool = True

# ---------------------------------------------------------------- access and logging


@app.middleware("http")
async def access_and_log(request: Request, call_next):
    key = os.environ.get("KARIMI_API_KEY")
    path = request.url.path
    if key and not any(path == o or path.startswith(o + "/") for o in OPEN):
        given = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(given, key):
            return JSONResponse({"detail": "missing or wrong X-API-Key"}, status_code=401)
    t0 = time.time()
    response = await call_next(request)
    trace = request.headers.get("x-cloud-trace-context", "").split("/")[0]
    line = {"severity": "INFO" if response.status_code < 500 else "ERROR", "event": "karimi_request",
            "method": request.method, "path": path, "status": response.status_code,
            "ms": round((time.time() - t0) * 1000)}
    if trace and os.environ.get("GOOGLE_CLOUD_PROJECT"):
        line["logging.googleapis.com/trace"] = f"projects/{os.environ['GOOGLE_CLOUD_PROJECT']}/traces/{trace}"
    print(json.dumps(line), flush=True)
    return response


def _postings_out(out: dict) -> list[dict]:
    return [{"id": p["id"], "requirements": [r.to_dict() for r in p["requirements"]],
             "title": p["title"].to_dict() if p["title"] else None} for p in out["postings"]]


@app.get("/health")
def health() -> dict:
    return {"rules_version": RULES_VERSION, "dict_version": _dict.version if _dict else "",
            "jobs": "cloud-run" if os.environ.get("KARIMI_RUN_JOB") else "local",
            "check": "cloud-run" if os.environ.get("KARIMI_RUN_CHECK") else "local",
            "access": "api-key" if os.environ.get("KARIMI_API_KEY") else "open"}


@app.get("/quality")
def quality() -> dict:
    """The quality card of the versions this service runs: measured on human labels."""
    if _quality is None:
        raise HTTPException(404, "no quality card for these versions")
    return _quality


@app.get("/v1/metrics")
def metrics() -> dict:
    """What the site shows: every checked run, as counts, shares and lights. No text."""
    return dashboard.aggregate(_store, _quality, _dict.version if _dict else "", _judge_ref)


@app.post("/v1/process")
def process_now(run: Run, request: Request) -> dict:
    """Up to MAX_SYNC postings, answered at once, with the run report. Kept and
    checked like a job: the answer names the job id its files sit under."""
    if len(run.postings) > MAX_SYNC:
        raise HTTPException(413, f"at most {MAX_SYNC} postings per call; use /v1/jobs for more")
    inputs = [p.model_dump(exclude_none=True) for p in run.postings]
    t0 = time.time()
    out = process(inputs, _dict, translate=run.translate)
    postings = _postings_out(out)
    job = _keep(inputs, postings, out["report"], run.translate, round(time.time() - t0, 1))
    return {"job": job, "postings": postings, "report": out["report"],
            "files": _links(job, _base(request))}


def _keep(inputs: list[dict], postings: list[dict], report: dict, translate: bool, seconds: float) -> str:
    """Store a /v1/process call as a finished job and start its check."""
    job = secrets.token_hex(8)
    _store.write_text(jf(job, "input.jsonl"), "\n".join(json.dumps(p, ensure_ascii=False) for p in inputs) + "\n")
    _store.write_text(jf(job, "results.jsonl"),
                      "\n".join(json.dumps(p, ensure_ascii=False) for p in postings) + "\n")
    write_json(_store, jf(job, "report.json"), report)
    req_csv, post_csv = exports.tables(inputs, postings)
    _store.write_text(jf(job, "requirements.csv"), req_csv)
    _store.write_text(jf(job, "postings.csv"), post_csv)
    write_json(_store, jf(job, "status.json"), {
        "job": job, "source": "process", "state": "done", "created": now(), "finished": now(),
        "translate": translate, "postings_total": len(inputs), "postings_done": len(inputs),
        "seconds": seconds, "rules_version": RULES_VERSION, "dict_version": _dict.version if _dict else ""})
    _launch_check(job)
    return job


@app.post("/v1/title")
def title(t: str) -> dict:
    return normalise_title(t, _dict).to_dict()

# ---------------------------------------------------------------- jobs


def _job(job: str) -> dict:
    if not _JOB_ID.match(job):
        raise HTTPException(404, "no such job")
    s = read_json(_store, jf(job, "status.json"))
    if s is None:
        raise HTTPException(404, "no such job")
    return s


def _base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.url.netloc}"


def _links(job: str, base: str) -> dict:
    return {name.split(".")[0]: _store.download_url(jf(job, name), base)
            for name in ("results.jsonl", "report.json", "requirements.csv", "postings.csv", "check.json")
            if _store.exists(jf(job, name))}


def _launch(job: str) -> str:
    """Start the run. On GCP: one execution of the Cloud Run Job, told its job id
    through the environment. Locally: a subprocess, never a thread, since the
    rules keep module-level state that a request in this process would share."""
    name = os.environ.get("KARIMI_RUN_JOB")
    if name:
        return check.start_cloud_job(name, job)
    env = dict(os.environ, KARIMI_JOB_ID=job)
    _procs[job] = subprocess.Popen([sys.executable, "-m", "karimi_normalise.job"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "local"


def _launch_check(job: str) -> None:
    """The check of a finished run, never in this process: the judge takes minutes."""
    try:
        name = os.environ.get("KARIMI_RUN_CHECK")
        if name:
            check.start_cloud_job(name, job)
        else:
            subprocess.Popen([sys.executable, "-m", "karimi_normalise.check", "--job", job],
                             env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001  the answer is already computed: say so, do not fail it
        check._log("ERROR", event="karimi_check_failed", job=job, error=type(e).__name__)


@app.post("/v1/jobs", status_code=201)
def create_job(opts: JobOptions, request: Request) -> dict:
    """Open a job. The answer says where to PUT the postings, one JSON object per line."""
    job = secrets.token_hex(8)
    write_json(_store, jf(job, "status.json"), {"job": job, "source": "job", "state": "created",
                                              "created": now(), "translate": opts.translate})
    return {"job": job, "state": "created", "upload": _store.upload_url(jf(job, "input.jsonl"), _base(request))}


@app.put("/v1/jobs/{job}/input")
async def upload_input(job: str, request: Request) -> dict:
    """Upload through the API: the local store, or a small file on GCP. A large
    file on GCP goes to the signed URL instead (bodies are capped at 32 MiB)."""
    s = _job(job)
    if s["state"] != "created":
        raise HTTPException(409, f"job is {s['state']}: the input can no longer change")
    body = await request.body()
    if len(body) > MAX_UPLOAD_MB * 2**20:
        raise HTTPException(413, f"more than {MAX_UPLOAD_MB} MB: use the signed upload URL")
    lines = [x for x in body.decode("utf-8").splitlines() if x.strip()]
    for i, line in enumerate(lines, 1):
        try:
            Posting.model_validate_json(line)
        except ValidationError as e:
            raise HTTPException(400, f"line {i} is not a posting: {e.errors()[0]['msg']}")
    _store.write_text(jf(job, "input.jsonl"), "\n".join(lines) + "\n")
    return {"job": job, "postings": len(lines)}


@app.post("/v1/jobs/{job}/start", status_code=202)
def start_job(job: str) -> dict:
    s = _job(job)
    if s["state"] != "created":
        raise HTTPException(409, f"job is already {s['state']}")
    if not _store.exists(jf(job, "input.jsonl")):
        raise HTTPException(409, "no input yet: upload the postings first")
    s.update(state="queued", queued=now())
    write_json(_store, jf(job, "status.json"), s)
    execution = _launch(job)
    # Re-read, never write `s` back: the run may already have moved the status
    # on. It needs seconds to start (models load), this takes milliseconds.
    s = _job(job)
    s["execution"] = execution
    write_json(_store, jf(job, "status.json"), s)
    return s


@app.get("/v1/jobs/{job}")
def job_status(job: str) -> dict:
    """The status, made true first: a run killed for memory or time writes
    nothing, so it is asked whether it is still alive (`check.health`)."""
    s = _job(job)
    p = _procs.get(job)
    change = check.health(s, check.execution_state(s.get("execution")),
                          alive=None if p is None else p.poll() is None)
    if change:
        s = {**s, **change, "updated": now()}
        write_json(_store, jf(job, "status.json"), s)
        check.check(job, _store)          # the dead run is reported like any other
    return s


@app.get("/v1/jobs/{job}/result")
def job_result(job: str, request: Request) -> dict:
    """Links to the run's files, signed on GCP, valid one hour. `check` appears a
    few minutes after the run ends."""
    s = _job(job)
    if s["state"] != "done":
        raise HTTPException(409, f"job is {s['state']}")
    links = _links(job, _base(request))
    return {"job": job, **links, "check": links.get("check")}


@app.get("/v1/jobs/{job}/files/{name}")
def job_file(job: str, name: str) -> FileResponse:
    """The local store's files. On GCP the result URLs point at the bucket instead."""
    _job(job)
    if name not in FILES or not isinstance(_store, LocalStore):
        raise HTTPException(404, "no such file")
    return FileResponse(_store.root / jf(job, name))
