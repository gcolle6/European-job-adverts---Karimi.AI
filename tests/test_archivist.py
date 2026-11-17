"""The archivist agent and the inspector's detectors added 2026-11-16.

    python -m pytest tests/test_archivist.py

Detector cases are batch 1 as the API returned it under rules 0.4.1, the
development batch; each has its control.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import archivist, errors  # noqa: E402


def _r(**kw):
    return {"item": kw.get("atom", ""), "translated": False, "space": "", "core": "", **kw}


@pytest.mark.parametrize("r, flag", [
    (_r(atom="Desirable experience in design", core="Desirable"), "optional_head"),
    (_r(atom="Advantageous knowledge of English", core="Advantageous"), "optional_head"),
    (_r(atom="A plus: experience with Go", core="plus: experience with Go"), "optional_head"),
    (_r(atom="Experience with Go is a plus", core="Go is a plus"), "optional_tail"),
    (_r(atom="English in B2 preferred", core="English in B2 preferred"), "optional_tail"),
    # controls: the marker gone, or a word that only looks like one
    (_r(atom="Preferably Python", core="Python"), None),
    (_r(atom="Experience with Go is a plus", core="Go"), None),
    (_r(atom="Preferred Shares accounting", core="Preferred Shares accounting"), None),
    (_r(atom="Plus500 trading platform", core="Plus500 trading platform"), None),
])
def test_how_much_it_is_wanted_left_in_the_requirement(r, flag):
    assert errors.optional_flag(r) == flag


@pytest.mark.parametrize("r, flag", [
    (_r(atom="深入理解大模型原理"), "untranslated"),
    (_r(atom="sklandi lietuvių ir gera anglų kalba"), "untranslated"),
    (_r(atom="Título en Ingeniería Civil"), "untranslated"),             # not the translator's letters
    (_r(atom="Wykształcenie wyższe w zakresie takim jak Informatyka", translated=True), "translation_failed"),
    # controls: English, a name with an accent, a translated item that came out English
    (_r(atom="Strong knowledge of SQL"), None),
    (_r(atom="Work on site in Łódź"), None),
    (_r(atom="Fluent English", item="Biegły angielski", translated=True), None),
])
def test_a_requirement_left_in_another_language(r, flag):
    assert errors.translation_flag(r) == flag


# the kinds the explorer found on batch 1 (Gemini, 2026-11-16), with controls
@pytest.mark.parametrize("r, flag", [
    # a marker the rules know is not `unknown` (since 0.4.3 they know every one batches 1 and 2 showed)
    (_r(atom="Kafka is considered an asset", core="Kafka is considered an asset"), None),
    (_r(atom="CISSP or CISM certification required", core="CISSP or CISM certification required"), "required_left"),
    (_r(atom="CV in English is a must", core="CV in English is a must"), "required_left"),
    (_r(atom="3+ years as a Data Engineer or similar role", core="Data Engineer or similar role"), "or_similar_left"),
    (_r(atom="LangChain Intermediate", core="LangChain Intermediate"), "level_left"),
    (_r(atom="Python Advanced", core="Python Advanced"), "level_left"),
    # controls
    (_r(atom="Willingness to travel up to 50% when required", core="travel up to 50% when required"), None),
    (_r(atom="Familiarity with C Sharp and Visual Basic", core="C Sharp and Visual Basic"), None),
    (_r(atom="Customer Journey Expert", core="Customer Journey Expert"), None),
    (_r(atom="Advanced analytics", core="Advanced analytics"), None),
    (_r(atom="Experience with Go is a plus", core="Go is a plus"), None),          # optional_tail's, not this
])
def test_a_word_that_adds_nothing_left_in_the_requirement(r, flag):
    assert errors.word_kept_flag(r) == flag


def test_markers_the_rules_learnt_are_a_known_kind_now():
    # batch 1's `also welcome` and `is an added advantage` were unknown to the
    # rules; since 0.4.3 they are taken off, so left in a core they are `optional_tail`
    for core in ("building web services in Go also welcome", "Additional training in safety is an added advantage",
                 "SAP Advantage", "Green Belt appreciated"):
        r = _r(atom=core, core=core)
        assert errors.word_kept_flag(r) is None and errors.optional_flag(r) == "optional_tail", core


def test_higher_education_is_a_degree_the_rules_miss():
    r = _r(atom="Higher Education (Electric Engineering, Automation Engineering)", core="Higher Education")
    assert errors.inspector_flag(r) == "degree_higher_education"
    assert errors.inspector_flag({**r, "space": "education"}) is None


def test_every_detector_has_its_catalogue_entry():
    known = archivist.by_detector()
    assert set(errors.INSPECTOR_DETECTORS) <= set(known)
    for e in archivist.catalogue():
        assert e["status"] in ("open", "resolved") and e["title"] and e["cause"]
        assert e["status"] == "open" or e["resolved_in"], e["id"]
        if e.get("guard"):
            assert (ROOT / e["guard"].split("::")[0]).exists(), e["guard"]


ENTRIES = [
    {"id": "fixed", "title": "t", "cause": "c", "status": "resolved", "resolved_in": "0.4.2",
     "detector": "fixed", "residual": {"rate": 0.001}},
    {"id": "open", "title": "t", "cause": "c", "status": "open", "resolved_in": None, "detector": "open",
     "rule_files": ["karimi/atomise.py"], "fix_hint": "do this"},
]


def _inspected(rows):
    return {"of": {"requirements": 1000},
            "rows": [{"stage": "s", "object": "requirement", "error": "e", "cause": c, "count": n} for c, n in rows],
            "examples": [{"cause": c, "cases": [{"item": "QQZ", "atom": "QQZ", "core": "QQZ", "key": "QQZ"}]}
                         for c, _ in rows]}


def test_the_archivist_reads_a_known_kind_by_the_rules_that_made_the_run():
    rv = archivist.review(_inspected([("fixed", 4)]), "0.4.1", entries=ENTRIES)
    assert rv["found"][0]["verdict"] == "fixed_later" and not rv["findings"]
    rv = archivist.review(_inspected([("fixed", 2)]), "0.4.2", entries=ENTRIES)
    assert rv["found"][0]["verdict"] == "residual"
    rv = archivist.review(_inspected([("fixed", 9)]), "0.4.2", entries=ENTRIES)    # 0.9% > 3 x 0.1%
    assert rv["found"][0]["verdict"] == "recurs" and rv["findings"][0]["light"] == "yellow"
    assert rv["proposals"][0]["id"] == "fixed"


def test_the_archivist_proposes_and_never_publishes_text():
    rv = archivist.review(_inspected([("open", 3), ("nobody_named_it", 1)]), "0.4.2", "job1", entries=ENTRIES)
    assert [f["verdict"] for f in rv["found"]] == ["open", "unknown"]
    draft = rv["proposals"][0]["draft"]
    assert "karimi/atomise.py" in draft and "do this" in draft and "('QQZ', [...])" in draft
    pub = archivist.public(rv)
    assert pub["proposals"] == ["open"] and "QQZ" not in str(pub["found"])
