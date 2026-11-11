"""The check finds what it is built to find, and stays quiet otherwise.

    python -m pytest tests/test_check.py

No model and no GCP: the judge's reply is replaced (`tester._chat`), the
store is a temporary folder. What only the real judge can show is its
calibration (`tester.py`); what only GCP can show is the execution query.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import check, tester  # noqa: E402
from karimi_normalise.store import LocalStore, jf, write_json  # noqa: E402


def _ago(minutes: float) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")


def test_health_finds_dead_runs_only():
    assert check.health({"state": "running", "updated": _ago(check.STALE_MINUTES + 5)})["state"] == "failed"
    assert check.health({"state": "running", "updated": _ago(5)}) is None
    assert check.health({"state": "running", "updated": _ago(5)},
                        execution={"finished": True, "failed": True})["state"] == "failed"
    assert check.health({"state": "running", "updated": _ago(5)}, alive=False)["state"] == "failed"
    assert check.health({"state": "done", "updated": _ago(500)}) is None


def test_judge_light_reads_against_the_reference():
    ref = {"answered": 150, "share": 0.10}
    assert check.judge_light({"answered": 40, "flagged": 4}, ref)[0] == "green"
    assert check.judge_light({"answered": 40, "flagged": 14}, ref)[0] == "red"
    assert check.judge_light({"answered": 5, "flagged": 5}, ref)[0] == "grey"       # too few
    assert check.judge_light({"answered": 40, "flagged": 14}, None)[0] == "grey"    # no reference
    # a reference with no flag at all does not make one flag a certainty
    assert check.judge_light({"answered": 40, "flagged": 1}, {"answered": 150, "share": 0.0})[0] == "green"


def _job(store, job: str, light: str = "green") -> None:
    # Pairs the model is asked about: no digit (a name) and no mere plural (spelling),
    # both of which the code answers without it.
    words = [f"area{chr(97 + i)}" for i in range(30)]
    reqs = [{"core": f"data {w}", "match_via": f"data {w} management", "match": "group" if i % 2 else "topic",
             "head_group": "experience", "atom": f"Experience with data {w}"} for i, w in enumerate(words)]
    write_json(store, jf(job, "status.json"), {"job": job, "state": "done", "postings_total": 30,
                                               "updated": _ago(1)})
    store.write_text(jf(job, "results.jsonl"),
                     "\n".join(json.dumps({"id": i, "requirements": [r], "title": None})
                               for i, r in enumerate(reqs)) + "\n")
    write_json(store, jf(job, "report.json"), {
        "signals": {"share_nuovo": {"value": 0.3, "light": light, "normal_range": [0.1, 0.25]}},
        "to_check": {"requirements_nuovo": [{"requirement": "x", "n": 1}]}})


def _judge(reply: str):
    """A judge that answers the planted pairs right and everything else with ``reply``."""
    known = {(a, b): same for _, a, b, same in check.CANARIES}

    def chat(url, messages, n):
        text = messages[-1]["content"]
        for (a, b), same in known.items():
            if f"a: {a}\n" in text and f"b: {b}\n" in text:
                return "SAME\nplanted" if same else "DIFFERENT\nplanted"
        return reply
    return chat


def test_judge_that_disagrees_makes_the_run_red(tmp_path, monkeypatch):
    store = LocalStore(tmp_path)
    monkeypatch.setattr(tester, "OUT", tmp_path / "tester")
    monkeypatch.setattr(tester, "CACHE", tmp_path / "tester" / "answers.jsonl")
    monkeypatch.setattr(tester, "_chat", _judge("DIFFERENT\nnot the same thing"))
    _job(store, "aaaaaaaaaaaaaaaa")
    ref = {"rates": {"group": {"answered": 150, "share": 0.1}, "topic": {"answered": 100, "share": 0.1}}}
    out = check.check("aaaaaaaaaaaaaaaa", store, judge_url="http://judge", reference=ref)
    assert out["overall"] == "red"
    assert {f["code"] for f in out["findings"]} >= {"judge:group", "judge:topic"}
    assert out["judge"]["group"]["flagged"] == out["judge"]["group"]["answered"] == 15
    assert json.loads(store.read_text(jf("aaaaaaaaaaaaaaaa", "check.json")))["overall"] == "red"


def test_judge_that_agrees_keeps_it_green(tmp_path, monkeypatch):
    store = LocalStore(tmp_path)
    monkeypatch.setattr(tester, "OUT", tmp_path / "tester")
    monkeypatch.setattr(tester, "CACHE", tmp_path / "tester" / "answers.jsonl")
    monkeypatch.setattr(tester, "_chat", _judge("SAME\nsame requirement"))
    _job(store, "bbbbbbbbbbbbbbbb")
    ref = {"rates": {"group": {"answered": 150, "share": 0.1}, "topic": {"answered": 100, "share": 0.1}}}
    out = check.check("bbbbbbbbbbbbbbbb", store, judge_url="http://judge", reference=ref)
    assert out["overall"] == "green" and out["findings"] == []
    assert out["canaries"]["missed"] == 0 and out["canaries"]["pairs"] == len(check.CANARIES)


@pytest.mark.parametrize("reply", ["SAME\nsame", "DIFFERENT\nnot the same", "I cannot answer that"])
def test_judge_that_misses_the_planted_pairs_is_not_read(tmp_path, monkeypatch, capsys, reply):
    # A judge saying one word to everything, or nothing usable, would keep a run
    # green (all SAME) or make it red (all DIFFERENT) on its own say-so.
    store = LocalStore(tmp_path)
    monkeypatch.setattr(tester, "OUT", tmp_path / "tester")
    monkeypatch.setattr(tester, "CACHE", tmp_path / "tester" / "answers.jsonl")
    monkeypatch.setattr(tester, "_chat", lambda url, m, n: reply)
    _job(store, "ffffffffffffffff")
    ref = {"rates": {"group": {"answered": 150, "share": 0.1}, "topic": {"answered": 100, "share": 0.1}}}
    out = check.check("ffffffffffffffff", store, judge_url="http://judge", reference=ref)
    assert out["overall"] == "yellow"
    assert {f["code"] for f in out["findings"]} == {"judge:canaries"}
    assert {v["light"] for v in out["judge"].values()} == {"grey"}
    assert out["canaries"]["missed"] > check.CANARY_MAX_MISSES
    logged = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert {"severity": "ERROR", "event": "karimi_judge_untrusted"}.items() <= logged[-1].items()
    last = json.loads(store.read_text(check.HISTORY).splitlines()[-1])
    assert last["canaries_missed"] == out["canaries"]["missed"]


def test_each_run_carries_its_detail_and_no_text(tmp_path, monkeypatch):
    from karimi_normalise import dashboard

    store = LocalStore(tmp_path)
    monkeypatch.setattr(tester, "OUT", tmp_path / "tester")
    monkeypatch.setattr(tester, "CACHE", tmp_path / "tester" / "answers.jsonl")
    monkeypatch.setattr(tester, "_chat", _judge("DIFFERENT\nnot the same thing"))
    _job(store, "aaaaaaaaaaaaaaaa", light="yellow")
    ref = {"rates": {"group": {"answered": 150, "share": 0.1}, "topic": {"answered": 100, "share": 0.1}}}
    check.check("aaaaaaaaaaaaaaaa", store, judge_url="http://judge", reference=ref)
    run = dashboard.aggregate(store, None, "0.1.0")["runs"][0]
    assert run["signals"]["share_nuovo"] == {"value": 0.3, "normal_range": [0.1, 0.25], "light": "yellow"}
    assert run["judge_detail"]["group"]["flagged"] == 15 and run["canaries"]["missed"] == 0
    assert run["to_check"] == {"requirements_nuovo": 1}
    assert {r["error"] for r in run["errors"]["rows"]} <= {"wrong_group", "wrong_topic"}
    assert all(r["error_text"] and r["cause_text"] for r in run["errors"]["rows"])
    assert "area" not in json.dumps(run)                      # no requirement reaches the site

    # A run checked before the detail reached the history: rebuilt from its files.
    line = json.loads(store.read_text(check.HISTORY))
    store.write_text(check.HISTORY, json.dumps({k: v for k, v in line.items() if k not in dashboard._DETAIL}) + "\n")
    old = dashboard.aggregate(store, None, "0.1.0")["runs"][0]
    assert {k: old[k] for k in dashboard._DETAIL} == {k: run[k] for k in dashboard._DETAIL}


def test_a_run_shows_before_its_check(tmp_path):
    from karimi_normalise import dashboard

    store = LocalStore(tmp_path)
    _job(store, "9999999999999999")
    write_json(store, jf("8888888888888888", "status.json"),          # never finished, a week ago
               {"job": "8", "state": "running", "updated": _ago(7 * 24 * 60)})
    runs = dashboard.aggregate(store, None, "0.1.0")["runs"]
    assert [(r["job"], r["pending"], r["postings"]) for r in runs] == [("9999999999999999", True, 30)]
    check.check("9999999999999999", store)
    runs = dashboard.aggregate(store, None, "0.1.0")["runs"]
    assert [r["job"] for r in runs] == ["9999999999999999"] and not runs[0].get("pending")


def test_canaries_reach_the_model():
    # A planted pair the code answers (`tester.by_code`) tests nothing about the model.
    d = check.canary_pairs()
    groups = {tester.group(k, a, b) for k, a, b in zip(d.kind, d.a, d.b)}
    assert not groups & {"spelling", "different_names", "developer_engineer"}
    assert d.answer.any() and (~d.answer).any()


def test_failed_run_is_red_and_drift_needs_three_in_a_row(tmp_path):
    store = LocalStore(tmp_path)
    write_json(store, jf("cccccccccccccccc", "status.json"), {"job": "c", "state": "failed", "error": "boom"})
    assert check.check("cccccccccccccccc", store)["overall"] == "red"
    codes = []
    for i, job in enumerate(["1111111111111111", "2222222222222222", "3333333333333333"]):
        _job(store, job, light="yellow")
        codes.append({f["code"] for f in check.check(job, store)["findings"]})
    assert "drift:share_nuovo" not in codes[1] and "drift:share_nuovo" in codes[2]
    assert all("x" not in line for line in store.read_text(check.HISTORY).splitlines()
               if "requirement" in line)  # the history holds no requirement text


def test_sweep_marks_the_silent_run_dead(tmp_path):
    store = LocalStore(tmp_path)
    write_json(store, jf("dddddddddddddddd", "status.json"),
               {"job": "d", "state": "running", "updated": _ago(check.STALE_MINUTES + 1)})
    _job(store, "eeeeeeeeeeeeeeee")
    assert check.sweep(store) == ["dddddddddddddddd"]
    s = json.loads(store.read_text(jf("dddddddddddddddd", "status.json")))
    assert s["state"] == "failed" and "no progress" in s["error"]
    assert store.exists(jf("dddddddddddddddd", "check.json"))


def test_shipped_guide_is_the_labellers_guide():
    v = ROOT / "New project" / "validation" / "PAIRS_GUIDE.md"
    if not v.exists():
        pytest.skip("no validation folder on this machine")
    assert tester.GUIDE.read_text(encoding="utf-8") == v.read_text(encoding="utf-8")
