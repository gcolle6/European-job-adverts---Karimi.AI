"""Rules 0.4.5: the user's review of batch 3 (2026-11-18, 100 items, 41 wrong).

    python -m pytest tests/test_rules_045.py

That review read the output of rules 0.4.3: 0.4.4 already changed 18 of the 41.
These are the rest, under the conventions of 2026-11-17 (a name wins, named
examples are the requirements) and the review's own notes. Batch 3 is
development; batch 4 measures.
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
    # the frame around a name goes
    ("Experienced in programming with Java", ["Java"]),
    ("Experience programming in Python, Java, JavaScript/TypeScript, or similar languages",
     ["Python", "Java", "JavaScript/TypeScript"]),
    ("Experience leveraging AI agents as a force multiplier", ["AI agents"]),
    ("Confidence using AI coding tools as part of daily workflow", ["AI coding tools"]),
    ("Several years of professional experience in Cloud Architecture with a strong focus on Microsoft Azure",
     ["Azure"]),
    ("Practical experience with microservices architecture and Docker-based deployments",
     ["microservices architecture", "Docker"]),
    ("Infrastructure as Code with Bicep (or Terraform, with willingness to learn)", ["Bicep", "Terraform"]),
    ("Hands-on experience designing and operating data pipelines in AWS with services like S3, Athena, DMS and Glue",
     ["AWS"]),
    ("Understanding the concepts of virtualization and containerization (VMware, Docker, Kubernetes)",
     ["VMware", "Docker", "Kubernetes"]),
    # what only praises goes to `extra`
    ("In-depth understanding of databases and popular Web frameworks", ["databases", "Web frameworks"]),
    ("Hands-on experience with scalable, highly available distributed systems", ["distributed systems"]),
    ("Interest in cloud platforms, software architecture, and modern development practices",
     ["cloud platforms", "software architecture", "development practices"]),
    ("Exhibit excellent programming skills and a strong ability to troubleshoot and resolve issues",
     ["programming", "troubleshoot", "resolve issues"]),
    ("Basic programming skills to support scripting and configuration tasks", ["programming"]),
    ("Excellent communication skills targeted towards engineering, product, or other stakeholders",
     ["communication"]),
    # one soft skill, one word
    ("Ability to work independently and collaboratively", ["autonomy", "teamwork"]),  # rules 0.4.10: one group per soft skill (the user, 2026-11-24)
    ("Ability to solve problems and autonomy", ["problem solving", "autonomy"]),  # rules 0.4.10: one group per soft skill (the user, 2026-11-24)
    ("Ability to work as a team", ["teamwork"]),
    ("Teamwork & Communication Strength", ["teamwork", "Communication"]),  # rules 0.4.10: one group per soft skill (the user, 2026-11-24)
    ("Ability to write clear, accurate, and actionable product specifications", ["writing"]),
    ("Minimum 3 years of relevant work experience", ["work experience"]),
    ("Proven experience in leading CoE / practice / large delivery teams",
     ["CoE", "practice", "large delivery teams"]),
    # degrees
    ("Bachelor’s or Master’s degree in industrial Automation, IT Systems or another relevant discipline",
     ["education: Bachelor in industrial Automation", "education: Bachelor in IT Systems",
      "education: Master in industrial Automation", "education: Master in IT Systems"]),
    ("Registered studies in mechanical engineering, automotive engineering or a comparable course of study",
     ["education: Student in mechanical engineering", "education: Student in automotive engineering"]),
    ("Successful completion of studies in computer science, electrical engineering or comparable qualification",
     ["education: Degree in computer science", "education: Degree in electrical engineering"]),
    ("Graduate and above, information systems, e-commerce, software engineering or related professions",
     ["education: Bachelor in information systems", "education: Bachelor in e-commerce",
      "education: Bachelor in software engineering"]),
])
def test_review_of_batch_3(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    # an acronym in brackets only abbreviates
    ("5+ years of experience in Master Data Management (MDM)", ["Master Data Management"]),
    ("Familiarity with high-performance computing (HPC)", ["high-performance computing"]),
    # a category name keeps the noun after it
    ("Experience in API development and integration", ["API development", "integration"]),
    ("API development", ["API development"]),
    ("Desirable ITIL Foundations", ["ITIL Foundations"]),
    ("Good foundations in Python", ["Python"]),
    # a trait list is not a name
    ("Communicative, team-capable and with high quality awareness",
     ["Communicative, team-capable and with high quality awareness"]),
    ("Strong communication skills in English and Dutch, both written and verbal",
     ["language: English", "language: Dutch"]),
])
def test_review_of_batch_3_controls(item, keys):
    assert _keys(item) == keys
