"""Rules 0.4.7: the agents' findings on batch 5 (2026-11-23), read row by row.

    python -m pytest tests/test_rules_047.py

Batch 5 ran on rules 0.4.6 (red, 6.7%). Every inspector flag outside the
degrees was read by hand (520 rows, 472 real); the degrees (140) too. The
kinds no detector named became detectors (`errors.object_flag`,
`names_dropped` in `errors.item_flags`). Written while the user reviewed the
same batch's 100 rows: the review measures 0.4.6 and the detectors, and its
own new kinds go into the next version.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402
from karimi_normalise import errors  # noqa: E402


def _keys(item: str) -> list[str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    norms = [normalise_req.normalise_requirement(a, True) for a in atoms]
    keep = normalise_req.keep_once(norms)
    return [normalise_req.decompose(n)["key"] for n, k in zip(norms, keep) if k]


@pytest.mark.parametrize("item, keys", [
    # clauses, each with its own frame: split before the list rules run
    ("3+ years of experience in Python, SQL and Spark, strong knowledge of Docker and Kubernetes, "
     "and experience with cloud platforms (AWS, GCP, Azure)",
     ["Python", "SQL", "Spark", "Docker", "Kubernetes", "AWS", "GCP", "Azure"]),
    ("Knowledge of Python and experience with AWS", ["Python", "AWS"]),
    ("Knowledge and experience of SQL", ["SQL"]),
    # names before a category that lists more
    ("Proficiency in HTML5, CSS3, JavaScript, and frameworks like Angular or React",
     ["HTML", "CSS", "JavaScript", "Angular", "React"]),
    ("Knowledge of Java and frameworks like Spring", ["Java", "Spring Framework"]),  # rules 0.4.11: the merges of 2026-11-26
    # `Header: a, b, c`
    ("Strong backend fundamentals: PostgreSQL, async workflows, queues, observability, CI/CD",
     ["PostgreSQL", "async workflows", "queues", "observability", "CI/CD"]),
    ("Microservices design patterns: CQRS, event sourcing, saga, API gateway",
     ["CQRS", "event sourcing", "saga", "API gateway"]),
])
def test_split_047(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("atom_, core, degree", [
    ("Currently enrolled in a bachelor’s degree program in business", "Student in business", "student"),
    ("Currently pursuing a degree or diploma in IT", "Student in Information Technology", "student"),  # rules 0.4.11: the merges of 2026-11-26
    ("Currently a candidate for a Master’s or PhD in Computer Science", "Student in Computer Science", "student"),
    ("Be a graduate of a Master's degree in Computer Science", "Master in Computer Science", "master"),
    ("Hold a PhD in Artificial Intelligence", "PhD in Artificial Intelligence", "phd"),
    ("Possession of a post graduate diploma in HR", "Master in HR", "master"),
    ("High School Diploma", "High school diploma", "school"),
    ("Masters’ Degree in Food Science & Technology", "Master in Food Science & Technology", "master"),
    ("STEM degree", "Degree in STEM", "degree"),
    ("A computer science degree (or in a related field)", "Degree in computer science", "degree"),
    ("Bac +5 en Data", "Master in Data", "master"),
    ("Hbo Food technology", "Bachelor in Food technology", "bachelor"),
    ("Relevant diploma Information Technology", "Degree in Information Technology", "degree"),
    ("Very good degree in computer science", "Degree in computer science", "degree"),
    ("Enrolled/Fresh graduated in a master’s degree in Industrial Engineering", "Student in Industrial Engineering",
     "student"),
    ("Master’s degree from a top-tier business school", "Master (any field)", "master"),
    ("6+ years of experience with a Bachelor’s degree in Computer Science", "Bachelor in Computer Science",
     "bachelor"),
])
def test_degrees_047(atom_, core, degree):
    d = normalise_req.decompose(atom_)
    assert (d["core"], d["degree"]) == (core, degree)


@pytest.mark.parametrize("atom_", ["Master Data Management", "Experience as Scrum Master", "High degree of resilience"])
def test_not_degrees(atom_):
    assert normalise_req.decompose(atom_)["space"] != "education"


@pytest.mark.parametrize("atom_, core, level", [
    ("High proficiency in Python", "Python", "strong"),
    ("Perfect command of French", "French", "expert"),
    ("Foundational knowledge of SQL", "SQL", "basic"),
    ("Deep understanding of SOLID", "SOLID", "strong"),
    ("Expert-level knowledge of VSAT Terminals", "VSAT Terminals", "expert"),
    ("Implementation experience with Scala", "Scala", ""),
    ("Real estate operations experience", "Real estate operations", ""),
    ("Passion for development", "Passion for development", ""),
    ("Experience building dashboards within eFront Invest", "eFront Invest", ""),
    ("Control of Dutch at European CEFR level C2", "Dutch", "strong"),
])
def test_cores_047(atom_, core, level):
    d = normalise_req.decompose(atom_)
    assert (d["core"], d["level"]) == (core, level)


# The user's review of batch 5 (2026-11-23, 23 of 100 wrong): what the notes asked for
@pytest.mark.parametrize("item, keys", [
    ("Detail-oriented with a focus on design iteration", ["Detail-oriented"]),
    ("Ability to work independently and effectively in a dynamic environment", ["autonomy"]),
    ("Extensive experience as a Senior, Staff or Lead Software Engineer", ["Software engineering"]),  # rules 0.4.11: the merges of 2026-11-26
    ("Proven record of shipping and iterating on impactful products", ["shipping products"]),
    ("Knowledge of responsible AI engineering", ["AI engineering"]),
    ("Motivated by the quality of work", ["Motivated"]),
    ("Recent hands-on experience with Braze is preferable", ["Braze"]),
    ("Basic knowledge of costing and ability to negotiate as required", ["costing", "negotiation"]),
    ("Practical experience building applications with Generative AI and LLMs", ["Generative AI", "LLMs"]),
    ("Strong experience in software development with a focus on application security", ["software development"]),
    ("Passion for development", ["Passion for development"]),
    ("Strong problem-solving and critical thinking skills", ["problem solving", "critical thinking"]),  # rules 0.4.10, the user's review of batch 8: one group
    ("Willingness to travel to the United States for business purposes",
     ["Willingness to travel to the United States"]),
    ("1 year minimum with Boomi", ["Boomi"]),
    ("Strong computer literacy: comfortable administering Windows and/or Linux workstations",
     ["computer literacy", "Windows", "Linux"]),
])
def test_review_of_batch_5(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("atom_, lo, hi", [
    ("3.5+ Years of experience with Java", 3, None),
    ("5/7 years of experience as programmer", 5, 7),
    ("Two to three years of experience in sales", 2, 3),
    ("From 4 to 7 years of experience in IT", 4, 7),
])
def test_years_047(atom_, lo, hi):
    d = normalise_req.decompose(atom_)
    assert (d["years_min"], d["years_max"]) == (lo, hi)


def test_detectors_047():
    assert errors.object_flag({"core": "", "extra": "of VSAT Terminals", "counted": True}) == "object_in_extra"
    assert errors.object_flag({"core": "", "extra": "", "counted": True}) is None
    assert errors.review_flag({"core": "eye for detail", "atom": "eye for detail", "space": ""}) is None
    assert errors.review_flag({"core": "Scrum Master", "atom": "Scrum Master", "space": ""}) is None
    reqs = [{"item_split": "Knowledge of HTML5, CSS3, JavaScript, and frameworks like Angular or React",
             "atom": "Knowledge of Angular", "core": "Angular"},
            {"atom": "Knowledge of React", "core": "React"}]
    assert "names_dropped" in errors.item_flags(reqs).values()
