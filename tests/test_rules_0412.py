"""Rules 0.4.12: the user's review of batch 10 (2026-11-26).

    python -m pytest tests/test_rules_0412.py

Batch 10 ran on rules 0.4.11 (yellow, 3.5%); the review found 26 wrong of 100.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402
from karimi_normalise import review  # noqa: E402,F401


def _keys(item: str) -> list[str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    norms = [normalise_req.normalise_requirement(a, True) for a in atoms]
    keep = normalise_req.keep_once(norms)
    return [normalise_req.decompose(n)["key"] for n, k in zip(norms, keep) if k]


@pytest.mark.parametrize("item, keys", [
    ('Interest in security issues and stable, scalable system architectures',
     ['security issues', 'system architectures']),
    ('Experience of conducting research projects using both qualitative and quantitative methodologies',
     ['research projects']),
    ('Ability to write high quality, well tested code',
     ['programming']),
    ('Ability to work independently and take end-to-end ownership',
     ['autonomy', 'take end-to-end ownership']),
    ('Ability to think high-level about user journeys and build campaigns',
     ['user journeys', 'build campaigns']),
    ('Proficiency in writing efficient SQL for databases such as PostgreSQL and Microsoft SQL',
     ['SQL', 'PostgreSQL', 'Microsoft SQL']),
    ('7+ years of product management on developer tools',
     ['Product management', 'developer tools']),
    ('Demonstrable experience building horizontally scalable, mission-critical enterprise software and services',
     ['building enterprise software', 'building services']),
    ('Exemplary customer service skills',
     ['customer service']),
    ('Teamspeler in een jong team',
     ['teamwork']),
    ('Experience deploying Microservice environments using containerisation technologies such as Kubernetes and Docker.',
     ['Microservices', 'Kubernetes', 'Docker']),
    ('Solid Object-Oriented Programming Knowledge in TypeScript, Python or Java',
     ['TypeScript', 'Python', 'Java']),
    ('Strong problem‑solving skills to investigate, reproduce, and resolve issues.',
     ['problem solving']),
    ('Independent and analytical approach to work',
     ['autonomy', 'analytical skills']),
    ('Experience managing multi-channel orchestration across email, push, in-app',
     ['managing multi-channel orchestration']),
    ('Experience with SAP rollouts and system maintenance, ideally ECC or S/4HANA',
     ['SAP', 'system maintenance', 'ECC', 'SAP S/4HANA']),
    ('Advanced English level with excellent grammatical skills',
     ['language: English']),
    ('A sharp eye for detail',
     ['Detail oriented']),
    ('Strong expertise in ETL process and various data model concepts',
     ['ETL', 'data model']),
    ('Excellent communication skills, both verbal and written (English required, Dutch or French desired)',
     ['communication', 'language: English', 'language: Dutch', 'language: French']),
    ('Seven or more years professional experience in software engineering',
     ['Software engineering']),
    ('Prior experience of at least 2 years in similar positions',
     ['prior experience']),
    ('Clear communication skills.',
     ['communication']),
    ('Understanding clean code principles',
     ['clean code principles']),
    ('Experience with component-based development and design systems',
     ['component-based development', 'design systems']),
    ('Proficient in English; Mandarin is a plus',
     ['language: English', 'language: Mandarin']),
    ('Familiarity with tools such as Excel, Word, etc.',
     ['Excel', 'Word']),
])
def test_review_of_batch_10(item, keys):
    assert _keys(item) == keys


def test_ideally_names_stay_optional():
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    s = "Experience with SAP rollouts and system maintenance, ideally ECC or S/4HANA"
    pos.prime([s])
    atoms, _ = atom.route(s)
    assert [a for a in atoms if "ECC" in a or "S/4HANA" in a] == ["Experience with ideally ECC",
                                                                  "Experience with ideally S/4HANA"]


def test_explorer_counts_europe_only():
    from karimi_normalise import explore
    rows = [{"country": "Germany", "src": "job1"}, {"country": "United States", "src": "job1"},
            {"country": "", "src": "export"}, {"country": "", "src": "job1"}, {"country": "India", "src": "export"}]
    assert explore.in_europe(rows) == [rows[0], rows[2]]
