"""The explorer agent, with a fake model: what it samples, how it groups, what leaves the job's files.

    python -m pytest tests/test_explorer.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import explorer  # noqa: E402


class Fake:
    """Answers each item by a rule, and the grouping call with two kinds."""
    model = "fake"

    def __init__(self):
        self.items = []

    def ask(self, system: str, user: str) -> str:
        if user.startswith("Item:"):
            self.items.append(user)
            if "certification required" in user:
                return json.dumps({"ok": False, "problems": [
                    {"stage": "normalisation", "kind": "new", "what": "required kept",
                     "pattern": "a closing word that says how it is asked"}]})
            if "Python is a plus" in user:
                return json.dumps({"ok": False, "problems": [
                    {"stage": "normalisation", "kind": "optional_tail", "what": "tail", "pattern": "tail"}]})
            return '{"ok": true}'
        return json.dumps({"kinds": [
            {"id": "Required Left", "title": "required kept", "shape": "a closing 'required' kept in the key",
             "stage": "normalisation", "catalogue": None, "members": [0]},
            {"id": "tail", "title": "CISSP certification required", "shape": "quotes the advert",
             "stage": "normalisation", "catalogue": "invented_id", "members": [1]}]})


def _post(pid, items):
    return {"id": pid, "requirements": [
        {"item_idx": k, "item": it, "atom": it, "core": core, "key": core, "space": "", "translated": False}
        for k, (it, core) in enumerate(items)]}


POSTS = [_post("p1", [("CISSP certification required", "CISSP certification"),
                      ("Strong SQL", "SQL")]),
         _post("p2", [("Python is a plus", "Python"), ("Desirable experience in design", "Desirable")])]


def test_it_reads_only_what_no_detector_flagged():
    items = explorer.sample(POSTS, "job1", n=30)
    assert {it["item"] for it in items} == {"CISSP certification required", "Strong SQL", "Python is a plus"}
    assert explorer.sample(POSTS, "job1", n=2) == explorer.sample(POSTS, "job1", n=2)     # seeded by the job


def test_kinds_are_grouped_and_new_ones_are_candidates():
    ex = explorer.explore(POSTS, "job1", Fake(), entries=[{"id": "optional_tail", "detector": "optional_tail",
                                                           "title": "t"}])
    assert ex["sampled"] == 3 and ex["flagged"] == 2
    kinds = {k["id"]: k for k in ex["kinds"]}
    assert kinds["required_left"]["new"] and kinds["required_left"]["count"] == 1
    assert kinds["tail"]["catalogue"] is None          # an id the catalogue does not hold is not trusted
    assert kinds["tail"]["quotes"] and not kinds["required_left"]["quotes"]
    assert kinds["required_left"]["cases"][0]["item"]


def test_no_case_and_no_quote_leaves_the_job():
    ex = explorer.explore(POSTS, "job1", Fake(), entries=[])
    pub = explorer.public(ex)
    text = json.dumps(pub)
    assert "cases" not in text and "CISSP" not in text
    assert any(k["title"] == "required kept" for k in pub["kinds"])


def test_the_site_gets_the_candidates():
    runs = [{"job": "a", "checked": "t", "explorer": explorer.public(explorer.explore(POSTS, "a", Fake(), entries=[]))}]
    s = explorer.summary(runs)
    assert s["runs"] == 1 and s["candidates"] == 2 and s["entries"][0]["job"] == "a"


def test_off_unless_asked(monkeypatch):
    monkeypatch.delenv("KARIMI_EXPLORER", raising=False)
    assert not explorer.enabled()
    monkeypatch.setenv("KARIMI_EXPLORER", "vertex")
    assert explorer.enabled()


def test_the_check_runs_it_and_never_fails_on_it(tmp_path, monkeypatch):
    from karimi_normalise import check
    from karimi_normalise.store import LocalStore, jf, read_json
    from tests.test_check import _job

    store = LocalStore(tmp_path)
    _job(store, "eeeeeeeeeeeeeeee")
    monkeypatch.setenv("KARIMI_EXPLORER", "vertex")
    monkeypatch.setattr(explorer, "vertex_client", lambda: Fake())
    check.check("eeeeeeeeeeeeeeee", store)
    c = read_json(store, jf("eeeeeeeeeeeeeeee", "check.json"))
    assert c["explorer"]["agent"] == "explorer"

    def boom():
        raise RuntimeError("no credentials")

    _job(store, "ffffffffffffffff")
    monkeypatch.setattr(explorer, "vertex_client", boom)
    out = check.check("ffffffffffffffff", store)
    assert out["explorer"] is None
