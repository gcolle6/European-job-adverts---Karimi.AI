"""The API answers exactly what the library answers, and a job runs end to end.

    python -m pytest tests/test_api.py

All local: the store is a temporary folder, the run and the check happen in
this process (`_launch`, `_launch_check` replaced), so nothing here needs GCP
or a judge. What only GCP can show (signed URLs, the Cloud Run Jobs) is
checked by hand once, as `deploy/gcp_setup.sh` says.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise.freeze import STORE  # noqa: E402

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

KEY = "test-key-123"
POSTINGS = [
    {"id": "a1", "title": "Senior Data Engineer (m/w/d)", "company": "ACME",
     "must_have": ["3+ years of Python and SQL", "Experience with Docker and Kubernetes"]},
    {"id": "a2", "title": "Frontend Developer",
     "must_have": ["Solid knowledge of React", "Fluent English"]},
]


@pytest.fixture()
def api(tmp_path, monkeypatch):
    dicts = sorted(STORE.glob("*/manifest.json")) if STORE.exists() else []
    if not dicts:
        pytest.skip("no frozen dictionary on this machine")
    monkeypatch.setenv("KARIMI_DICT", str(dicts[-1].parent))
    monkeypatch.setenv("KARIMI_STORE", str(tmp_path / "jobs"))
    monkeypatch.setenv("KARIMI_API_KEY", KEY)
    monkeypatch.delenv("KARIMI_RUN_JOB", raising=False)
    monkeypatch.delenv("KARIMI_RUN_CHECK", raising=False)
    from karimi_normalise import api as mod
    mod = importlib.reload(mod)
    from karimi_normalise import check, job

    # The run and the check in this process, at once: the test reads the result straight after.
    monkeypatch.setattr(mod, "_launch", lambda j: (job.run(j, mod._store, mod._dict), "inline")[1])
    monkeypatch.setattr(mod, "_launch_check", lambda j: check.check(j, mod._store))
    monkeypatch.setattr(job, "after", lambda j, s: check.check(j, s))
    return mod, TestClient(mod.app, headers={"X-API-Key": KEY})


def _library(mod) -> list[dict]:
    from karimi_normalise import process
    out = process(POSTINGS, mod._dict, translate=False)
    return mod._postings_out(out)


def _path(url: str) -> str:
    return url.split("testserver", 1)[1]


def test_key_is_required_except_on_open_paths(api):
    mod, c = api
    bare = TestClient(mod.app)
    assert bare.get("/health").status_code == 200
    assert bare.get("/v1/metrics").status_code == 200
    assert "def main" in bare.get("/try_api.py").text
    assert bare.get("/API.md").text.startswith("# karimi-normalise API")
    assert bare.post("/v1/process", json={"postings": POSTINGS}).status_code == 401
    assert bare.post("/v1/process", json={"postings": POSTINGS}, headers={"X-API-Key": "wrong"}).status_code == 401


def test_process_equals_library_and_is_kept_and_checked(api):
    mod, c = api
    r = c.post("/v1/process", json={"postings": POSTINGS, "translate": False})
    assert r.status_code == 200
    body = r.json()
    assert body["postings"] == json.loads(json.dumps(_library(mod)))
    assert body["report"]["versions"]["dict_version"] == mod._dict.version
    # kept like a job, with the two CSV tables, and checked at once (inline here)
    assert set(body["files"]) >= {"results", "report", "requirements", "postings", "check"}
    s = c.get(f"/v1/jobs/{body['job']}").json()
    assert (s["source"], s["state"], s["postings_total"]) == ("process", "done", 2)
    chk = c.get(_path(body["files"]["check"])).json()
    assert chk["job"] == body["job"] and chk["overall"] in ("green", "yellow", "red")
    rows = list(csv.DictReader(io.StringIO(c.get(_path(body["files"]["postings"])).text)))
    assert [r["id"] for r in rows] == ["a1", "a2"]
    assert rows[0]["company"] == "ACME"                      # the caller's own column travels through
    assert int(rows[0]["n_requirements"]) == len(body["postings"][0]["requirements"])
    reqs = list(csv.DictReader(io.StringIO(c.get(_path(body["files"]["requirements"])).text)))
    assert len(reqs) == sum(len(p["requirements"]) for p in body["postings"])
    assert {r["posting_id"] for r in reqs} == {"a1", "a2"}
    # and the site's aggregate sees it, with no requirement text
    m = c.get("/v1/metrics").json()
    assert m["totals"]["runs"] == 1 and m["runs"][0]["source"] == "process"
    assert "Python" not in json.dumps(m)


def test_too_many_postings_go_to_a_job(api):
    mod, c = api
    r = c.post("/v1/process", json={"postings": [POSTINGS[0]] * (mod.MAX_SYNC + 1)})
    assert r.status_code == 413


def test_job_round_trip(api):
    mod, c = api
    r = c.post("/v1/jobs", json={"translate": False})
    assert r.status_code == 201
    job, up = r.json()["job"], r.json()["upload"]
    assert c.post(f"/v1/jobs/{job}/start").status_code == 409          # no input yet
    body = "\n".join(json.dumps(p) for p in POSTINGS)
    r = c.put(_path(up["url"]), content=body, headers=up["headers"])
    assert r.json() == {"job": job, "postings": 2}
    assert c.post(f"/v1/jobs/{job}/start").status_code == 202
    s = c.get(f"/v1/jobs/{job}").json()
    assert (s["state"], s["postings_done"], s["postings_total"]) == ("done", 2, 2)
    res = c.get(f"/v1/jobs/{job}/result").json()
    lines = c.get(_path(res["results"])).text.splitlines()
    assert [json.loads(x) for x in lines] == json.loads(json.dumps(_library(mod)))
    report = c.get(_path(res["report"])).json()
    assert report["summary"]["postings"] == 2
    chk = c.get(_path(res["check"])).json()      # the check ran after the job
    assert chk["job"] == job and chk["overall"] in ("green", "yellow", "red")
    assert c.get(_path(res["postings"])).text.startswith("id,")
    assert c.post(f"/v1/jobs/{job}/start").status_code == 409          # once only
    m = c.get("/v1/metrics").json()
    assert m["totals"]["postings"] == 2 and m["runs"][0]["job"] == job


def test_job_refuses_bad_input_and_unknown_ids(api):
    mod, c = api
    job = c.post("/v1/jobs", json={}).json()["job"]
    r = c.put(f"/v1/jobs/{job}/input", content='{"title": "no must_have"}')
    assert r.status_code == 400 and "line 1" in r.json()["detail"]
    assert c.get("/v1/jobs/../../etc").status_code == 404
    assert c.get("/v1/jobs/0123456789abcdef").status_code == 404
    assert c.get(f"/v1/jobs/{job}/files/input.jsonl").status_code == 404  # only results leave
