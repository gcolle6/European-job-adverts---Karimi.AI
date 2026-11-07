"""Rules 0.2.0's input cleaning, and the error table the site shows.

    python -m pytest tests/test_errors.py

No dictionary and no model: the casing map and the dictionary are built from
a few cores in memory (`Dictionary.from_tables`), and the encoder is never
reached because every lookup here is found word for word.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import Dictionary, errors  # noqa: E402
from karimi_normalise.dashboard import _error_table  # noqa: E402
from karimi_normalise.dictionary import casing  # noqa: E402
from karimi_normalise.requirements import clean_item, clean_items  # noqa: E402

CASING = {"python": "Python", "sql": "SQL", "azure": "Azure", "ci/cd": "CI/CD", "english": "English"}


def test_clean_item_removes_what_is_around_the_requirement():
    assert clean_item("- Strong SQL skills.") == "Strong SQL skills"
    assert clean_item("• Python;") == "Python"
    assert clean_item("2) Experience  with   Docker") == "Experience with Docker"
    assert clean_item("Tools such as Jira, Confluence, etc.") == "Tools such as Jira, Confluence, etc."
    assert clean_item("e.g. Python") == "e.g. Python"


def test_clean_item_restores_capitals_only_when_there_are_none():
    assert clean_item("experience with python and azure", CASING) == "Experience with Python and Azure"
    assert clean_item("fluent english, ci/cd pipelines", CASING) == "Fluent English, CI/CD pipelines"
    # The employer used capitals: theirs are kept, even where the map would differ.
    assert clean_item("Experience with python", CASING) == "Experience with python"
    assert clean_item("experience with python") == "experience with python"     # no dictionary, no map


def test_each_language_gets_its_own_capitals():
    casing = {"en": CASING, "de": {"erfahrung": "Erfahrung", "ki": "KI", "llms": "LLMs"}}
    out = clean_items(["praktische erfahrung mit llms und generativer ki."], casing)
    assert out["praktische erfahrung mit llms und generativer ki."] == (
        "Praktische Erfahrung mit LLMs und generativer KI", "de")
    # In its own posting; inside a German one, a short item takes the posting's language.
    assert clean_items(["fluent english"], casing)["fluent english"] == ("Fluent English", None)


def test_casing_takes_names_only_and_not_the_first_word():
    cores = ["Experience with Python", "Python", "knowledge of Python", "use Python daily", "Python and SQL",
             "strong Python", "Python scripting", "write Python", "good Python", "Data pipelines",
             "data pipelines", "build data pipelines", "Go", "go", "ready to go", "Go", "Go", "Go"]
    m = casing(cores * 2)
    assert m.get("python") == "Python"
    assert "data" not in m           # capital only at the start of a core
    assert "go" not in m             # written both ways: no evidence


def _dictionary():
    cores = pd.DataFrame({"req_head_group": ["experience", ""], "req_core": ["Microsoft Azure", "Python"],
                          "req_group": ["experience: microsoft azure", "competence: python"],
                          "req_topic": ["cloud", "python"], "n": [10, 10]})
    manifest = {"dict_version": "test", "group_threshold": 0.9, "topic_threshold": 0.8}
    titles = pd.DataFrame({"title_key": [], "title_group": [], "title_name": []})
    return Dictionary.from_tables(manifest, cores, np.eye(2, 4, dtype=np.float32), titles, {})


def test_known_core_is_found_in_other_capitals():
    d = _dictionary()
    m = d.lookup_requirements([("experience", "microsoft azure"), ("experience", "MICROSOFT AZURE")])
    assert [x.status for x in m] == ["known", "known"]
    assert {x.group for x in m} == {"experience: microsoft azure"}


def _req(item, atom, idx=0, head="", route="rules", translated=False):
    return {"item_idx": idx, "item": item, "atom": atom, "head_group": head, "route": route,
            "translated": translated}


def test_split_suspects_and_causes():
    postings = [{"requirements": [
        _req("Experience with AWS, Azure", "Experience with AWS", 0, "experience"),
        _req("Experience with AWS, Azure", "Azure", 0),
        _req("python and sql and teamwork", "python and sql and teamwork", 1, route="llm"),
        _req("Strong communication skills", "communication skills", 2),
    ]}]
    s = errors.split_suspects(postings)
    assert s["of"] == {"items": 3, "requirements": 4}
    assert s["counts"] == {("splitting", "requirement", "fragment", "head_not_repeated"): 1,
                           ("splitting", "requirement", "merged", "lowercase"): 1}
    t = errors.table(s, None)
    assert all("item" not in r and "atom" not in r for r in t["rows"])      # no text in the table


def test_split_profile_reads_the_hand_count():
    rows = [
        # the library found 1 where the human counted 2: merged, and the rule says why
        {"item": "Python and SQL and teamwork", "translated": False, "human": 3,
         "requirements": [_req("x", "Python and SQL and teamwork", route="llm")]},
        # 2 where the human counted 1, with an optional part counted
        {"item": "Experience with Kubernetes, ideally on AWS", "translated": False, "human": 1,
         "requirements": [_req("x", "Experience with Kubernetes"), _req("x", "ideally on AWS")]},
        {"item": "Python", "translated": False, "human": 1, "requirements": [_req("x", "Python")]},
    ]
    p = errors.split_profile(rows)
    assert p["of"] == {"items_hand_counted": 3}
    assert p["counts"] == {("splitting", "requirement", "merged", "list_not_separated"): 1,
                           ("splitting", "requirement", "over_split", "optional_part"): 1}


def test_normalisation_errors_and_the_site_table():
    j = pd.DataFrame([
        {"sample": "group", "kind": "requirement", "a": "data protection", "b": "data visualization",
         "item": "Data protection", "translated": False, "judge_same": False},
        {"sample": "topic", "kind": "requirement", "a": "testing", "b": "automated testing",
         "item": "testing", "translated": False, "judge_same": True},
        {"sample": "variant", "kind": "role", "a": "Data Analyst", "b": "Data Architect",
         "item": "Data Analyst (m/f/d)", "translated": False, "judge_same": False},
    ])
    n = errors.normalise_errors(j)
    assert n["of"] == {"judged_requirements": 2, "judged_roles": 1}
    assert n["counts"] == {("normalisation", "requirement", "wrong_group", "share_a_word"): 1,
                           ("normalisation", "role", "wrong_role", "different_job_word"): 1}
    t = errors.table(n)
    card = {"rules_version": "0.2.0", **errors.table({"of": {"items_hand_counted": 115}, "counts": {
        ("splitting", "requirement", "merged", "other"): 3}})}
    site = _error_table({(r["stage"], r["object"], r["error"], r["cause"]): r["count"] for r in t["rows"]},
                        t["of"], 1, card)
    role = next(r for r in site["rows"] if r["object"] == "role")
    assert (role["count"], role["of"], role["share"]) == (1, 1, 1.0)
    assert role["cause_text"] == errors.CAUSES["different_job_word"]
    split = next(r for r in site["rows"] if r["stage"] == "splitting")
    assert (split["count"], split["of"]) == (3, 115)
