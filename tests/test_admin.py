"""Only the project lead decides on the explorer's kinds: the Google sign-in the API checks.

    python -m pytest tests/test_admin.py

Google's token check is replaced by a stand-in that knows three tokens; the
rest (who may decide, what is written, what the site then shows) is the real code.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("google.oauth2")
from fastapi.testclient import TestClient  # noqa: E402

from karimi_normalise import archivist, dashboard  # noqa: E402
from karimi_normalise.store import jf, write_json  # noqa: E402

LEAD = "lead@example.com"
JOB = "abcdef0123456789"
TOKENS = {"good": {"email": LEAD, "email_verified": True},
          "other": {"email": "someone@example.com", "email_verified": True},
          "unverified": {"email": LEAD, "email_verified": False}}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.delenv("KARIMI_DICT", raising=False)
    monkeypatch.setenv("KARIMI_STORE", str(tmp_path / "jobs"))
    monkeypatch.setenv("KARIMI_API_KEY", "a-key")
    monkeypatch.setenv("KARIMI_OAUTH_CLIENT_ID", "client-1")
    monkeypatch.setenv("KARIMI_ADMIN_EMAILS", LEAD.upper())
    from google.oauth2 import id_token

    def verify(token, request, audience):
        assert audience == "client-1"
        if token not in TOKENS:
            raise ValueError("bad token")
        return TOKENS[token]

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    from karimi_normalise import api as mod
    mod = importlib.reload(mod)
    write_json(mod._store, jf(JOB, "check.json"), {"explorer": {"kinds": [
        {"id": "full_sentence_kept", "title": "Full sentence kept", "shape": "a whole sentence as the key",
         "stage": "normalisation", "catalogue": None, "new": True, "count": 1, "quotes": False,
         "cases": [{"item": "Je kunt schakelen", "what": "a sentence", "made": []}]}]}})
    mod._store.write_text("history/runs.jsonl", json.dumps(
        {"job": JOB, "checked": "2026-11-16T12:00:00+00:00", "state": "done",
         "explorer": {"agent": "explorer", "kinds": [{"id": "full_sentence_kept", "new": True, "count": 1,
                                                      "title": "Full sentence kept", "catalogue": None}]}}) + "\n")
    return mod, TestClient(mod.app)


def _as(token):
    return {"Authorization": f"Bearer {token}"}


def test_only_the_lead_gets_in(api):
    mod, c = api
    assert c.get("/v1/admin/me").status_code == 401                         # no sign-in
    assert c.get("/v1/admin/me", headers=_as("forged")).status_code == 401   # not Google's
    assert c.get("/v1/admin/me", headers=_as("other")).status_code == 403
    assert c.get("/v1/admin/me", headers=_as("unverified")).status_code == 403
    assert c.get("/v1/admin/me", headers={"X-API-Key": "a-key"}).status_code == 401   # Karimi's key is not it
    assert c.get("/v1/admin/me", headers=_as("good")).json() == {"email": LEAD}


def test_nobody_when_not_configured(api, monkeypatch):
    mod, c = api
    monkeypatch.delenv("KARIMI_ADMIN_EMAILS")
    assert c.get("/v1/admin/me", headers=_as("good")).status_code == 503


def test_the_lead_sees_the_cases_the_site_never_does(api):
    mod, c = api
    runs = c.get("/v1/admin/explorer", headers=_as("good")).json()["runs"]
    assert runs[0]["kinds"][0]["cases"][0]["item"] == "Je kunt schakelen"
    assert c.get("/v1/admin/explorer", headers=_as("other")).status_code == 403
    assert "Je kunt" not in json.dumps(dashboard.aggregate(mod._store, None, ""))


def test_a_decision_is_written_and_the_catalogue_takes_it(api):
    mod, c = api
    bad = c.post("/v1/admin/explorer/decide", headers=_as("other"),
                 json={"job": JOB, "kind": "full_sentence_kept", "decision": "confirm"})
    assert bad.status_code == 403 and not archivist.decisions(mod._store)
    assert c.post("/v1/admin/explorer/decide", headers=_as("good"),
                  json={"job": JOB, "kind": "invented", "decision": "confirm"}).status_code == 404
    r = c.post("/v1/admin/explorer/decide", headers=_as("good"),
               json={"job": JOB, "kind": "full_sentence_kept", "decision": "confirm", "note": "yes"})
    assert r.status_code == 200 and r.json()["decision"] == "confirm"
    entry = next(e for e in archivist.catalogue_with(mod._store) if e["id"] == "full_sentence_kept")
    assert entry["status"] == "open" and entry["confirmed"] and entry["detector"] is None
    m = dashboard.aggregate(mod._store, None, "")
    assert m["agents"]["explorer"]["entries"][0]["kinds"][0]["decision"] == "confirm"
    assert m["agents"]["explorer"]["candidates"] == 0
    assert LEAD not in json.dumps(m)                 # who decided stays out of the public page


def test_a_rejected_kind_is_offered_back_as_known():
    from karimi_normalise import explorer

    class Fake:
        model = "fake"
        seen = ""

        def ask(self, system, user):
            if user.startswith("Item:"):
                return json.dumps({"ok": False, "problems": [{"stage": "split", "what": "w", "pattern": "p"}]})
            Fake.seen = system
            return json.dumps({"kinds": [{"id": "x", "title": "t", "shape": "s", "stage": "split",
                                          "catalogue": "old_kind", "members": [0]}]})

    post = {"id": "p", "requirements": [{"item_idx": 0, "item": "A", "atom": "A", "core": "A", "key": "A"}]}
    ex = explorer.explore([post], "j", Fake(), entries=[], rejected=["old_kind"])
    assert "old_kind" in Fake.seen
    assert ex["kinds"][0]["rejected_before"] and not ex["kinds"][0]["new"]
