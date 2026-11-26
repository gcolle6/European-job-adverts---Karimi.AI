"""Rules 0.4.11: the user's review of batch 9, the agents' findings, and the merges of 2026-11-26.

    python -m pytest tests/test_rules_0411.py

Batch 9 ran on rules 0.4.10 (yellow, 5.5%, the first with 100 topic pairs); the
review found 20 wrong of 100. The same day the user approved the merges of near
duplicates the explorer showed: the same thing written another way takes the
name that says it best; a soft skill keeps its first spelling; a role is read as
its field; a degree's field keeps its full name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402
from karimi_normalise import explore  # noqa: E402


def _keys(item: str) -> list[str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    norms = [normalise_req.normalise_requirement(a, True) for a in atoms]
    keep = normalise_req.keep_once(norms)
    return [normalise_req.decompose(n)["key"] for n, k in zip(norms, keep) if k]


@pytest.mark.parametrize("item, keys", [
    ('Deep hands-on capability in AVEVA solution configuration and integration',
     ['AVEVA']),
    ('Proficiency in at least one scripting or programming language (Python preferred) for network automation tasks',
     ['Scripting languages', 'programming languages', 'Python', 'network automation']),
    ('Subject matter expertise in AML and compliance',
     ['AML', 'compliance']),
    ('Degree or strong background in Italian linguistics, computational linguistics, or a related field',
     ['education: Degree in Italian linguistics', 'education: Degree in computational linguistics']),
    ('Experience working in cross-functional and international project environments',
     ['experience in cross-functional project environments', 'experience in international project environments']),
    ('Enthusiasm for AI backed by practical results',
     ['AI']),
    ('Swiss citizenship or valid Swiss employment permit',
     ['Swiss citizenship', 'valid Swiss employment permit']),
    ('Foundational understanding of operating systems (Windows/Mac/Linux)',
     ['Windows', 'Mac', 'Linux']),
    ('Ability to present cybersecurity risk to Boards and executive management',
     ['present cybersecurity risk']),
    ('University or engineering background with a specialization in Information Systems Security',
     ['education: Degree in Information Systems Security']),
    ('Experience with GPU acceleration technologies (e.g., NVIDIA CUDA) in containerized environments.',
     ['GPU acceleration technologies', 'NVIDIA CUDA']),
    ('Commercial mindset with experience contributing to proposals and business development activities',
     ['Commercial mindset']),
    ("Maintain a professional attitude that reflects the brand's values",
     ['professional attitude']),
    ('Highest level of technical expertise in cybersecurity',
     ['Cybersecurity']),
    ('passed knowledge test of RWTH Aachen for MaTSE applicants',
     ['RWTH Aachen']),
    ('Extensive knowledge and experience of ensuring compliance with regulatory and organisational policy',
     ['compliance']),
    ('Accurate and reliable work',
     ['Accurate', 'reliable']),
    ('Experience solving hardware and software problems',
     ['solving hardware problems', 'solving software problems']),
    ('Strong SQL skills on DB2 for i and Microsoft SQL Server',
     ['SQL', 'DB2', 'SQL Server']),
    ('Experience with Node.js & NPM',
     ['Node.js', 'NPM']),
    ('Proficiency in programming languages (e.g., Java, C/C++, Python)',
     ['Java', 'C', 'C++', 'Python']),
    ('Experience building backend services and APIs using .NET/C# or Python',
     ['.NET', 'C#', 'Python']),
    ('Proficiency in Python, with practical experience building applications using LLMs',
     ['Python', 'building applications using LLMs']),
    ('Experience with cloud infrastructure, including Kubernetes, Google Cloud Platform, and Amazon Web Services',
     ['Kubernetes', 'GCP', 'AWS']),
    ('Experience with Git/GitHub and Agile/Scrum',
     ['Git', 'GitHub', 'Agile methodologies', 'Scrum']),
    ('Experience in Research & Development',
     ['Research & Development']),
    ('Experience in API development and integration',
     ['API development', 'integration']),
    ('Structured and project-based work',
     ['Structured and project-based work']),
    ('Experience in banking, insurance and financial services',
     ['banking', 'insurance', 'financial services']),
    ('Experience designing and deploying services across Linux and Windows',
     ['services across Linux', 'services across Windows']),
    ('Experience with Unix/Linux',
     ['Linux/Unix']),
    ('Cyber Security',
     ['Cybersecurity']),
    ('Experience as a Data Engineer',
     ['Data engineering']),
    ('Take initiative',
     ['Initiative']),
    ('Communication across non-technical stakeholders',
     ['communication']),
    ("Master's degree in AI",
     ['education: Master in Artificial Intelligence']),
])
def test_review_agents_and_merges_of_batch_9(item, keys):
    assert _keys(item) == keys


def test_level_kept_when_the_frame_says_highest():
    d = normalise_req.decompose("Highest level of technical expertise in cybersecurity")
    assert (d["key"], d["level"]) == ("Cybersecurity", "expert")


def test_explorer_merges_old_runs_too():
    assert explore._merged("team spirit") == "teamwork"
    assert explore._merged("cyber security") == "cybersecurity"
    assert explore._merged("python") == "python"
