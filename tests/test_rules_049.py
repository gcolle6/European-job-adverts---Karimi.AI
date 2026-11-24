"""Rules 0.4.9: the agents' findings on batch 7 and the user's review of it (2026-11-23).

    python -m pytest tests/test_rules_049.py

Batch 7 ran on rules 0.4.8 (red, 6.6%); the review found 22 wrong of 100. A `/`
in a note separates the requirements the user wants (2026-11-23), and what is not
the requirement (level, years, the setting) stays in its own column.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402


def _keys(item: str) -> list[str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    norms = [normalise_req.normalise_requirement(a, True) for a in atoms]
    keep = normalise_req.keep_once(norms)
    return [normalise_req.decompose(n)["key"] for n, k in zip(norms, keep) if k]


@pytest.mark.parametrize("item, keys", [
    ('You study digital management, data science, computer science or another relevant discipline.',
     ['education: Student in digital management', 'education: Student in data science', 'education: Student in computer science']),
    ('Ability to work independently and within a team environment',
     ['autonomy', 'teamwork']),
    ('Strong written communication and attention to detail',
     ['communication', 'attention to detail']),
    ('Experience developing and maintaining SAP interfaces and integrations',
     ['SAP']),
    ('Comfortable in a scientific domain',
     ['scientific domain']),
    ('People manager & customer focused',
     ['People manager', 'customer focused']),
    ('Minimum 7+ years of experience in Multinational Company environment',
     ['experience in Multinational Company environment']),
    ('Experience leading and shipping large scope technical projects in collaboration with multiple experienced engineers',
     ['leading technical projects', 'shipping technical projects']),
    ('Good analytical and problem solving capabilities',
     ['analytical skills', 'problem solving']),  # rules 0.4.10: one group per soft skill (the user, 2026-11-24)
    ('Technical degree (preference in network system administration)',
     ['education: Degree in technical field']),
    ('Very good Python knowledge as well as experience with machine learning, statistics, data analysis and Databricks/Spark',
     ['Python', 'machine learning', 'statistics', 'data analysis', 'Databricks', 'Spark']),  # rules 0.4.10, the user's review of batch 8: names split at the slash
    ('Self-motivated with a passion for renewable energy and sustainability',
     ['Self-motivated', 'renewable energy', 'passion for sustainability']),  # rules 0.4.10: two passions (the user, 2026-11-23)
    ("Bachelor's degree +5 in the field of Artificial Intelligence, Data Science, Computer Science or related discipline",
     ['education: Master in Artificial Intelligence', 'education: Master in Data Science', 'education: Master in Computer Science']),
    ('Technological know-how',
     ['Technological know-how']),
    ('Hands-on experience working with both in-house teams and external agencies',
     ['experience with in-house teams and external agencies']),
    ('Strong stakeholder management and collaboration skills across teams and domains',
     ['stakeholder management', 'teamwork']),  # rules 0.4.10: one group per soft skill (the user, 2026-11-24)
    ('3–6 years as a software engineer, solutions engineer, or technical partner/integration role',
     ['software engineer', 'solutions engineer', 'technical partner/integration role']),
    ('5+ years of experience as a Product Owner or in a similar role within Identity & Access Management (IAM)',
     ['Product Owner', 'Identity & Access Management']),
    ('Strong knowledge and experience in Linux development',
     ['Linux']),
    ('Strong Python skills and hands-on experience with ML libraries',
     ['Python', 'ML libraries']),
    ('Active knowledge of French',
     ['language: French']),
    ('Junit Knowledge for Unitary Tests',
     ['Junit']),
    ('Strong written and verbal communication skills',
     ['communication']),
    ('At least 60 months of experience in software development',
     ['software development']),
    ('7 years+ experience in Oracle Forms',
     ['Oracle Forms']),
    ('7+ years across Data Science',
     ['Data Science']),
    ('Minimum two-year experience in data engineering',
     ['data engineering']),
    ('Minimum 4-year experience in Java / Javascript',
     ['Java / Javascript']),
    ('4-year degree in Computer Science',
     ['education: Degree in Computer Science']),
    ('A clear understanding of data structures, algorithms and design patterns',
     ['data structures', 'algorithms', 'design patterns']),
    ('A first successful experience in testing automation',
     ['testing automation']),
    ('Interest or experience with LLMs (e.g. GPT, BERT, Llama)',
     ['LLMs', 'GPT', 'BERT', 'Llama']),
    ('Interest and experience with Ubuntu Linux, Kubernetes and Ceph',
     ['Ubuntu Linux', 'Kubernetes', 'Ceph']),
    ('Experience applying thorough testing, observability and security practices',
     ['testing', 'observability', 'security practices']),
    ('Skilled in using project management tools',
     ['project management tools']),
    ('Experience leveraging AI agents as a force multiplier',
     ['AI agents']),
    ('Experience working in agile teams',
     ['agile teams']),
])
def test_review_and_agents_of_batch_7(item, keys):
    assert _keys(item) == keys


def test_years_kept_in_their_column():
    d = normalise_req.decompose("At least 60 months of experience in software development")
    assert (d["key"], d["years_min"]) == ("software development", 5)
    d = normalise_req.decompose("Minimum two-year experience in data engineering")
    assert (d["key"], d["years_min"]) == ("data engineering", 2)


def test_context_kept_aside():
    d = normalise_req.decompose("Strong written communication")
    assert (d["key"], d["level"]) == ("communication", "strong")
    d = normalise_req.decompose("leading large scope technical projects in collaboration with multiple experienced engineers")
    assert d["key"] == "leading technical projects" and "in collaboration with" in d["extra"]


def test_placeholder_never_leaks():
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    s = "5+ years of experience as a Product Owner or in a similar role within Identity & Access Management (IAM)"
    pos.prime([s])
    atoms, _ = atom.route(s)
    assert not any("@@" in a for a in atoms)


@pytest.mark.parametrize("core, group", [
    # one group per soft skill (the user, 2026-11-24, rules 0.4.10)
    ("Independent working methods", "autonomy"), ("work independently", "autonomy"), ("autonomous", "autonomy"),
    ("Collaborative mindset", "teamwork"), ("Team spirit", "teamwork"), ("team player", "teamwork"),
    ("collaboration", "teamwork"), ("work in multidisciplinary teams", "teamwork"),
    ("Analytical spirit", "analytical skills"), ("analytical thinking", "analytical skills"),
    # not the same thing: leading a team, a product, a field
    ("leading teams", "leading teams"), ("team management", "team management"), ("Microsoft Teams", "Microsoft Teams"),
    ("analytics", "analytics"), ("analytical problem-solving", "analytical problem-solving"),
])
def test_soft_skill_groups(core, group):
    assert normalise_req.soft_group(core) == group
