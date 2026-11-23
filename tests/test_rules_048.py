"""Rules 0.4.8: the agents' findings on batch 6 and the user's review of it (2026-11-23).

    python -m pytest tests/test_rules_048.py

Batch 6 ran on rules 0.4.7 (yellow, 5.8%); the review found 20 wrong of 100.
Three conventions changed that day, by the user's call on the review's notes:
coordinated verbs over a generic object are one requirement per verb and keep
the verb (reversing 2026-10-29); a list of areas after the object are
requirements; an attitude goes when what follows stands alone and is not one
generic word (`Passion for development` stays).
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
    # verbs kept, one per verb, over a generic object; a name still wins
    ("Proven experience in designing and implementing complex solutions on multiple platforms",
     ["designing complex solutions", "implementing complex solutions"]),
    ("Experience in developing urban plans", ["developing urban plans"]),
    ("Demonstrated ability to design and communicate complex technical solutions",
     ["design complex technical solutions", "communicate complex technical solutions"]),
    ("Used to design and implement networks", ["design networks", "implement networks"]),
    ("Proven experience supporting production systems with high availability", ["supporting production systems"]),
    ("Experience building and maintaining CI/CD pipelines", ["CI/CD"]),
    ("Experience working in agile teams", ["agile teams"]),
    # areas after the object are requirements
    ("Strong interpersonal skills and ease working with Business, IT, Security, Risk, Legal, Finance",
     ["interpersonal", "Business", "IT", "Security", "Risk", "Legal", "Finance"]),
    # the rest of the notes
    ("Clear written and verbal communication skills", ["communication skills"]),
    ("Technical and transverse leadership", ["leadership"]),
    ("Experience with Business Intelligence projects using BI tools", ["BI tools"]),
    ("Strong understanding of how data architecture influences data quality", ["data architecture"]),
    ("Sufficient technical depth in machine learning, data systems, or applied ML",
     ["machine learning", "data systems", "applied ML"]),
    # the agents' findings
    ("Meaningful experience with data connectors, integrations, ETL/ELT, data platforms",
     ["data connectors", "integrations", "ETL/ELT", "data platforms"]),
    ("Strong Microsoft knowledge in .NET, Visual Studio and SQL Server", [".NET", "Visual Studio", "SQL Server"]),
    ("Education: Bachelor's degree in Computer Science, Mathematics, Physics",
     ["education: Bachelor in Computer Science", "education: Bachelor in Mathematics",
      "education: Bachelor in Physics"]),
    ("L2/L3 Protocols: BGP, OSPF, VLAN", ["BGP", "OSPF", "VLAN"]),
    ("At least 3 years of experience in fraud, risk and compliance", ["fraud", "risk", "compliance"]),
    ("Database knowledge, for example in Oracle, Azure or AWS", ["Oracle", "Azure", "AWS"]),
    # `Learning` was cut from what it belongs to (the user's question, 2026-11-23)
    ("Strong expertise in Deep Learning", ["Deep Learning"]),
    ("Deep understanding of Machine Learning projects lifecycle", ["Machine Learning"]),
    ("Strong capacity to learn", ["learning ability"]),
])
def test_review_of_batch_6(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("atom_, core, degree", [
    ("Completed WO Master's degree in Data Science", "Master in Data Science", "master"),
    ("Bachelor`s degree in computer science", "Bachelor in computer science", "bachelor"),
    ("Degree/Master in computer science", "Master in computer science", "master"),
    ("Bachelor's degree completed or currently in the final semester in Finance", "Bachelor in Finance",
     "bachelor"),
])
def test_degrees_048(atom_, core, degree):
    d = normalise_req.decompose(atom_)
    assert (d["core"], d["degree"]) == (core, degree)


@pytest.mark.parametrize("atom_, lo, hi", [
    ("Max. 2 years of work experience", None, 2),
    ("Experience of 5 years in project management", 5, 5),
])
def test_years_048(atom_, lo, hi):
    d = normalise_req.decompose(atom_)
    assert (d["years_min"], d["years_max"]) == (lo, hi)


def test_detectors_048():
    assert errors.review5_flag({"core": "written and verbal communication skills", "atom": "x"}) == "modes_left"
    assert errors.review5_flag({"core": "keen eye for spotting patterns", "atom": "x"}) == "attitude_left"
    assert errors.review5_flag({"core": "eye for detail", "atom": "x"}) is None
    assert errors.review_flag({"core": "able to work in a team", "atom": "x", "space": ""}) is None
