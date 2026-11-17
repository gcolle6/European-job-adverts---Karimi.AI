"""A person's review of a run: the sample, the labels, and the agents measured against them.

    python -m pytest tests/test_review.py
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import dashboard, review  # noqa: E402
from karimi_normalise.store import LocalStore, jf, write_json  # noqa: E402

JOB = "0123456789abcdef"


def _run(store, n_items: int = 120) -> None:
    # every 4th item opens on 'Desirable' and keeps only that word: the inspector flags it
    posts = []
    for i in range(n_items):
        bad = i % 4 == 0
        atom = f"Desirable experience in topic{i}" if bad else f"Experience with Tool{i}"
        core = "Desirable" if bad else f"Tool{i}"
        posts.append({"id": f"p{i}", "requirements": [
            {"item_idx": 0, "item": atom, "atom": atom, "core": core, "key": core, "space": "",
             "translated": False, "counted": True}]})
    store.write_text(jf(JOB, "results.jsonl"), "".join(json.dumps(p) + "\n" for p in posts))
    write_json(store, jf(JOB, "check.json"), {"error_estimate": {"share": 0.031, "light": "yellow"}})


def test_the_sample_is_random_kept_and_blind(tmp_path):
    store = LocalStore(tmp_path)
    _run(store)
    a = review.sample(store, JOB)
    assert len(a) == review.SIZE and review.sample(store, JOB) == a           # drawn once, kept
    assert [it["n"] for it in a] == list(range(review.SIZE))
    seen = review.for_reviewer(a)
    assert all(set(it) == {"n", "item", "english", "made"} for it in seen)    # no agent's verdict
    assert any(it["inspector"] for it in a)


def _labels(items, k, wrong_if_flagged=True):
    return [{"n": it["n"], "verdict": "incorrect" if (it["inspector"] and wrong_if_flagged) else "correct",
             "note": "sentence QQZNOTE"} for it in items[:k]]


def test_at_least_fifty_and_the_latest_counts(tmp_path):
    store = LocalStore(tmp_path)
    _run(store)
    items = review.sample(store, JOB)
    with pytest.raises(ValueError):
        review.submit(store, JOB, _labels(items, 49), "lead")
    with pytest.raises(ValueError):
        review.submit(store, JOB, [{"n": 999, "verdict": "correct"}] * 60, "lead")
    s = review.submit(store, JOB, _labels(items, 50), "lead")
    assert s["labelled"] == 50 and s["in_order"]
    s = review.submit(store, JOB, _labels(items, 100), "lead")
    assert s["labelled"] == 100 and s["submissions"] == 2


def test_the_agents_are_measured_against_the_person(tmp_path):
    store = LocalStore(tmp_path)
    _run(store)
    items = review.sample(store, JOB)
    labels = _labels(items, 100)
    # one wrong item the inspector did not flag, and one of its flags the person calls right
    plain = next(lab for lab, it in zip(labels, items) if not it["inspector"])
    plain["verdict"] = "incorrect"
    flagged = next(lab for lab, it in zip(labels, items) if it["inspector"])
    flagged["verdict"] = "correct"
    s = review.submit(store, JOB, labels, "lead")
    f = s["inspector"]["flagged"]
    assert s["incorrect"] == f and s["inspector"]["flagged_incorrect"] == f - 1
    assert s["inspector"]["precision"] == round((f - 1) / f, 4)
    assert s["inspector"]["recall"] == round((f - 1) / f, 4)
    lo, hi = s["ci95"]
    assert lo < s["share_incorrect"] < hi and s["check_estimate"] == 0.031


def test_skipping_items_is_said(tmp_path):
    store = LocalStore(tmp_path)
    _run(store)
    items = review.sample(store, JOB)
    s = review.submit(store, JOB, _labels(items[10:], 60), "lead")
    assert not s["in_order"]


def test_the_site_gets_numbers_never_items_or_notes(tmp_path):
    store = LocalStore(tmp_path)
    _run(store)
    store.write_text("history/runs.jsonl", json.dumps({"job": JOB, "state": "done", "requirements": 120}) + "\n")
    review.submit(store, JOB, _labels(review.sample(store, JOB), 60), "lead@example.com")
    m = dashboard.aggregate(store, None, "")
    text = json.dumps(m["review"])
    assert m["review"]["reviews"][0]["labelled"] == 60 and m["review"]["pooled"]["labelled"] == 60
    assert "QQZNOTE" not in text and "Tool" not in text and "lead@" not in text


@pytest.fixture()
def api(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("google.oauth2")
    from fastapi.testclient import TestClient
    from google.oauth2 import id_token

    monkeypatch.delenv("KARIMI_DICT", raising=False)
    monkeypatch.setenv("KARIMI_STORE", str(tmp_path / "jobs"))
    monkeypatch.setenv("KARIMI_OAUTH_CLIENT_ID", "client-1")
    monkeypatch.setenv("KARIMI_ADMIN_EMAILS", "lead@example.com")
    monkeypatch.setattr(id_token, "verify_oauth2_token",
                        lambda t, r, a: {"email": "lead@example.com" if t == "good" else "x@example.com",
                                         "email_verified": True})
    from karimi_normalise import api as mod
    mod = importlib.reload(mod)
    _run(mod._store)
    mod._store.write_text("history/runs.jsonl", json.dumps(
        {"job": JOB, "state": "done", "requirements": 120, "checked": "2026-11-17T09:00:00+00:00"}) + "\n")
    return mod, TestClient(mod.app)


def test_only_the_lead_reviews(api):
    mod, c = api
    good, other = {"Authorization": "Bearer good"}, {"Authorization": "Bearer other"}
    assert c.get(f"/v1/admin/review/{JOB}", headers=other).status_code == 403
    runs = c.get("/v1/admin/review", headers=good).json()
    assert runs["runs"][0]["job"] == JOB and runs["runs"][0]["labelled"] == 0 and runs["min_labels"] == 50
    s = c.get(f"/v1/admin/review/{JOB}", headers=good).json()
    assert len(s["items"]) == 100 and "inspector" not in s["items"][0]
    labels = [{"n": it["n"], "verdict": "correct", "note": ""} for it in s["items"][:40]]
    assert c.post(f"/v1/admin/review/{JOB}", headers=good, json={"labels": labels}).status_code == 400
    labels = [{"n": it["n"], "verdict": "correct", "note": ""} for it in s["items"][:55]]
    assert c.post(f"/v1/admin/review/{JOB}", headers=other, json={"labels": labels}).status_code == 403
    r = c.post(f"/v1/admin/review/{JOB}", headers=good, json={"labels": labels})
    assert r.status_code == 200 and r.json()["labelled"] == 55
    assert len(c.get(f"/v1/admin/review/{JOB}", headers=good).json()["labels"]) == 55   # to go on from
