"""The explorer grows with the runs that pass, and only with what was read right.

    python -m pytest tests/test_explore.py

No model and no GCP: the store is a temporary folder, the judge is not asked
(categories come from the fixed rules or `Other`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import check, explore  # noqa: E402
from karimi_normalise.store import LocalStore, jf, read_json, write_json  # noqa: E402

GOOD = {"canaries": {"trusted": True},
        "findings": [{"level": "signals", "light": "red", "code": "signal:share_nuovo", "what": "share_nuovo = 0.17"},
                     {"level": "signals", "light": "red", "code": "signal:share_titles_nuovo", "what": "0.49"}]}


def test_the_gate_lets_new_adverts_in_and_keeps_bad_reads_out():
    assert explore.gate(GOOD)[0]                                   # new requirements are not an error
    assert not explore.gate(None)[0]
    assert not explore.gate({**GOOD, "canaries": {"trusted": False}})[0]
    assert not explore.gate({"canaries": None, "findings": []})[0]   # no judge ran: nothing verified
    split = {"level": "signals", "light": "red", "code": "signal:share_items_damaged", "what": "x"}
    assert not explore.gate({**GOOD, "findings": GOOD["findings"] + [split]})[0]
    judged = {"level": "judge", "light": "red", "code": "judge:group", "what": "x"}
    assert not explore.gate({**GOOD, "findings": [judged]})[0]


def _r(topic: str, **kw) -> dict:
    return {"req_topic": topic, "req_group": topic, "core": topic, "atom": topic, "route": "rules",
            "counted": True, "match": "known", "space": "", "head_group": "experience", **kw}


def test_only_requirements_read_right_are_kept():
    assert explore.keep(_r("python")) is None
    assert explore.keep(_r("python", route="single")) is None
    assert explore.keep(_r("written and verbal communication", route="llm")) is None   # kept whole, still one
    assert explore.keep(_r("python", route="damaged")) == "damaged"
    assert explore.keep(_r("python", counted=False)) == "not_counted"
    assert explore.keep(_r("", match="empty")) == "no_topic"
    assert explore.keep(_r("technologies")) == "generic"
    # a degree the inspector flags is not counted as a degree it is not
    assert explore.keep(_r("bachelor's degree preferred", atom="Bachelor's degree preferred")) == "degree_suspect"


def test_one_advert_counts_once_whatever_the_run():
    assert explore.advert_key("a1") == explore.advert_key("a1")
    assert explore.advert_key("a1") != explore.advert_key("a2")
    assert explore.advert_key(None, "T", ["x"]) == explore.advert_key("", "T", ["x"])
    rows = [{"k": "1", "src": "export"}, {"k": "1", "src": "job"}, {"k": "2", "src": "job"}]
    assert [r["src"] for r in explore.unique(rows)] == ["export", "job"]


def _row(i: int, topics: list[str], src: str, company: int | None = None) -> dict:
    return {"k": explore.advert_key(f"{src}-{i}"), "c": f"c{company if company is not None else i % 10}",
            "country": "Germany", "sen": "Senior", "role": "Data Engineer", "src": src, "rv": "0.4.1",
            "r": [[t, t, "", "experience", t.title(), "", ""] for t in topics]}


def _run(store, job: str, n: int, topic: str, check_out: dict, ids: str | None = None) -> None:
    ids = ids or job
    inputs = [{"id": f"{ids}-{i}", "title": "Data Engineer", "must_have": [f"Experience with {topic}"],
               "company": f"Co{i % 10}", "country": "DE", "seniority": "Senior"} for i in range(n)]
    results = [{"id": f"{ids}-{i}", "title": {"title_name": "Data Engineer", "rules_version": "0.4.1"},
                "requirements": [_r(topic, core=topic.title()), _r("x and y", route="damaged")]} for i in range(n)]
    store.write_text(jf(job, "input.jsonl"), "".join(json.dumps(p) + "\n" for p in inputs))
    store.write_text(jf(job, "results.jsonl"), "".join(json.dumps(r) + "\n" for r in results))
    write_json(store, jf(job, "check.json"), check_out)


def test_a_passing_run_adds_to_the_explorer_and_a_failing_one_does_not(tmp_path):
    store = LocalStore(tmp_path)
    base = [_row(i, ["python"], "export") for i in range(40)] + [_row(i, ["dbt"], "export2") for i in range(20)]
    store.write_text(explore.BASE, "".join(json.dumps(r) + "\n" for r in base))
    explore.rebuild(store)
    names = {r["name"] for r in read_json(store, explore.INDEX)["requirements"]}
    assert "Python" in names and "Dbt" not in names          # dbt: 20 adverts, under the floor of 30

    _run(store, "aaaaaaaaaaaaaaaa", 15, "dbt", GOOD, ids="dbt")
    d = explore.contribute(store, "aaaaaaaaaaaaaaaa")
    assert d["contributed"] and d["postings"] == 15 and d["dropped"]["damaged"] == 15
    explore.rebuild(store)
    ix = read_json(store, explore.INDEX)
    by = {r["name"]: r for r in ix["requirements"]}
    assert by["Dbt"]["ads"] == 35                              # a new requirement, once enough adverts ask
    assert ix["source"]["from"] == {"export": 60, "runs": 15, "run_jobs": 1}
    assert "x and y" not in {r["name"].lower() for r in ix["requirements"]}

    # the same adverts sent again count once; a run the check failed adds nothing
    _run(store, "bbbbbbbbbbbbbbbb", 15, "dbt", GOOD, ids="dbt")
    explore.contribute(store, "bbbbbbbbbbbbbbbb")
    _run(store, "cccccccccccccccc", 40, "rust", {**GOOD, "canaries": {"trusted": False}})
    refused = explore.contribute(store, "cccccccccccccccc")
    assert not refused["contributed"] and "judge" in refused["why"]
    explore.rebuild(store)
    by = {r["name"]: r for r in read_json(store, explore.INDEX)["requirements"]}
    assert by["Dbt"]["ads"] == 35 and "Rust" not in by
    built = read_json(store, explore.BUILT)
    assert [d["contributed"] for d in built["decisions"]] == [True, True, False]
    assert read_json(store, explore.REQUIREMENTS)[by["Dbt"]["id"]]["roles"][0]["role"] == "Data Engineer"
    assert explore.summary(store)["requirements"] == len(by)


def test_nothing_of_the_advert_text_is_stored(tmp_path):
    store = LocalStore(tmp_path)
    _run(store, "dddddddddddddddd", 3, "kotlin", GOOD)
    explore.contribute(store, "dddddddddddddddd")
    text = store.read_text(f"{explore.RUNS}dddddddddddddddd.jsonl")
    assert "Experience with" not in text and "Co1" not in text and "dddddddddddddddd-1" not in text


def test_the_sweep_decides_runs_checked_before_the_explorer(tmp_path, monkeypatch):
    store = LocalStore(tmp_path)
    store.write_text(explore.BASE, "".join(json.dumps(_row(i, ["python"], "export")) + "\n" for i in range(40)))
    _run(store, "eeeeeeeeeeeeeeee", 5, "go", GOOD)
    write_json(store, jf("eeeeeeeeeeeeeeee", "status.json"), {"job": "eeeeeeeeeeeeeeee", "state": "done"})
    assert explore.pending(store) == ["eeeeeeeeeeeeeeee"]
    check.sweep(store)
    assert explore.pending(store) == []
    assert read_json(store, explore.BUILT)["from"]["runs"] == 5
