"""Rules 0.4.10: the agents' findings on batch 8 and the user's review of it (2026-11-24).

    python -m pytest tests/test_rules_0410.py

Batch 8 ran on rules 0.4.9 (yellow, 3.9%); the review found 14 wrong of 100
(batch 7: 22). Two calls by the user the same days: a passion for X and Y is two
passions; a soft skill has one group however it is written (autonomy, teamwork,
analytical skills, adaptability, problem solving).
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
    ('Expert-level SQL with experience in BigQuery and MariaDB',
     ['SQL', 'BigQuery', 'MariaDB']),
    ('Knowledge of data structuring for real-time business evaluation',
     ['data structuring']),
    ('At least 5+ years’ experience in industry, with at least 2 years at Engineer level in the nuclear industry or other highly regulated sector',
     ['industry experience', 'Engineer level in the nuclear industry']),
    ('At least proficient in C and proficient in C++/Python programming languages',
     ['C', 'C++', 'Python']),
    ('Experience implementing engineering practices including Git, CI/CD, infrastructure as code, automated testing, monitoring and incident management.',
     ['Git', 'CI/CD', 'Infrastructure as Code', 'automated testing', 'monitoring', 'incident management']),
    ("Currently enrolled in a Master's program at an engineering school",
     ['education: Master in Engineering']),
    ('Comfortable being the primary interface with technical, security-sensitive, or public-sector customers',
     ['interface with clients']),
    ('An understanding of how modern, component-based sites are built, so you design with the build in mind',
     ['component-based sites']),
    ('Ability to adapt to a rapidly changing environment',
     ['adaptability']),
    ('Pleasure to Solve Problems',
     ['problem solving']),
    ('Team spirit and appreciation of collaboration',
     ['teamwork']),
    ('Practical experience building LLM-powered or agentic applications, ideally with LangGraph or LangChain.',
     ['LLM-powered', 'agentic applications']),
    ('Certification for TOGAF and ArchiMate',
     ['TOGAF', 'ArchiMate']),
    ('Strong business analysis and communication skills with 4+ years of experience',
     ['business analysis', 'communication']),
    ("Doctor's degree in Computer Science",
     ['education: PhD in Computer Science']),
    ('Currently enrolled (full time) in a Masters program in Data Science',
     ['education: Master in Data Science']),
    ('Comfortable working across IT, OT, and cloud environments',
     ['IT', 'OT', 'cloud environments']),
    ('Exceptional academic track record',
     ['academic track record']),
    ('About 5 years of experience as a Product Owner, with a solid experience of eCommerce environments and flows',
     ['Product Owner', 'eCommerce environments', 'flows']),
    ('Experience in predictive modeling to support demand planning',
     ['predictive modeling']),
    ('Ability to monitor and manage network availability, performance, and capacity',
     ['monitor network availability', 'manage network availability', 'monitor performance', 'manage performance', 'monitor capacity', 'manage capacity']),
    ('Deep JVM internals: memory model, garbage collection, JIT',
     ['JVM internals']),
    ('Detail-oriented with a structured approach to work',
     ['Detail-oriented', 'structured approach to work']),
    ('Experience designing and deploying services across Linux and Windows',
     ['services across Linux', 'services across Windows']),
    ('Self-motivated with a passion for renewable energy and sustainability',
     ['Self-motivated', 'renewable energy', 'passion for sustainability']),
])
def test_review_and_agents_of_batch_8(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("row, kind", [
    ({"core": "Team spirit", "atom": "Team spirit"}, "soft_skill_ungrouped"),
    ({"core": "C++/Python", "atom": "proficient in C++/Python"}, "names_slashed"),
    ({"core": "SQL with experience in BigQuery", "atom": "Expert-level SQL with experience in BigQuery"},
     "named_tail_left"),
    ({"core": "Certification", "extra": "for TOGAF", "atom": "Certification for TOGAF"}, "certification_key"),
])
def test_review8_detectors(row, kind):
    assert errors.review8_flag(row) == kind


@pytest.mark.parametrize("row", [
    {"core": "teamwork"}, {"core": "CI/CD"}, {"core": "PL/SQL"}, {"core": "TOGAF", "extra": "certification"},
])
def test_review8_detectors_quiet(row):
    assert errors.review8_flag(row) is None
