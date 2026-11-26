"""Rules 0.4.6: the user's review of batch 4 (2026-11-18, 100 items, 37 wrong).

    python -m pytest tests/test_rules_046.py

The first review of a run made with the rules in production (0.4.5). The
inspector had flagged 2 of the 37; each kind became a detector
(`errors.review_flag`, `errors.item_flags`), measured on this review and on
the reviews of batches 2 and 3 (`New project/score_review_detectors.py`).
Batch 4 is development; batch 5 measures.
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
    # languages
    ("Minimum English level C1", ["language: English"]),
    ("Fluent in either French or Dutch, with excellent English understanding",
     ["language: French", "language: English", "language: Dutch"]),
    ("sufficient mastery of Dutch to understand and discuss technical information", ["language: Dutch"]),
    # where and what for go to `extra`
    ("Experience in leading technical projects in a fast paced environment", ["leading technical projects"]),
    ("Strong understanding of industry challenges within technology, fintech, or regulated environments",
     ["industry challenges"]),
    ("Strong verbal and written communication skills to interact with stakeholders and project owners",
     ["communication"]),  # 2026-11-23: the modes set aside; rules 0.4.9 drops `skills` too (batch 7)
    ("4-6 years of experience in testing domain, with a minimum of 3 years in test automation",
     ["Software testing", "test automation"]),  # rules 0.4.11: the merges of 2026-11-26
    # the name wins over a word that adds nothing
    ("Python software development experience with large projects", ["Python"]),
    ("Advanced command of SQL Domain", ["SQL"]),
    ("Data Analytics Methodologies", ["Data analytics"]),  # rules 0.4.11: the merges of 2026-11-26
    ("IT affinity (SQL knowledge)", ["SQL"]),
    ("Experience with Jenkins and SonarQube for CI/CD and code quality", ["Jenkins", "SonarQube"]),
    ("Proficiency in orchestrating hybrid-cloud infrastructures (AWS, Azure, VMware)", ["AWS", "Azure", "VMware"]),
    # activities before one object; one soft skill, one word
    ("Demonstrated experience training and evaluating machine learning models",
     ["training machine learning models", "evaluating machine learning models"]),  # changed 2026-11-23: verbs kept, one per verb (the user's review of batch 6)
    ("Spirit of analysis", ["analysis"]),
    ("Easy contact with colleagues", ["teamwork"]),
    ("Strong commitment and desire to learn and grow", ["commitment", "Willingness to learn", "willingness to grow"]),  # rules 0.4.11: the merges of 2026-11-26
    ("AI literacy, including effective use of AI tools, prompt engineering, automation, and agent-based workflows",
     ["AI"]),
    # degrees
    ("Master ' s degree in computer science", ["education: Master in computer science"]),
    ("Master's degree or above in Power Electronics/Electrical/Mechatronics",
     ["education: Master in Power Electronics", "education: Master in Electrical", "education: Master in Mechatronics"]),
])
def test_review_of_batch_4(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    ("Fluency in English", ["language: English"]),
    ("Previous experience in a role within IT / Data", ["role within IT / Data"]),
    ("Strong skills in digital solutions like Microsoft Office and CAFM/FMIS tools",
     ["Microsoft Office", "CAFM/FMIS"]),
    ("Experience in planning and organizing", ["planning", "organizing"]),
])
def test_review_of_batch_4_controls(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("record, flag", [
    ({"core": "C1", "space": "", "extra": ""}, "language_as_skill"),
    ({"core": "leading technical projects in a fast paced environment", "space": "", "extra": ""}, "context_left"),
    ({"core": "SQL Domain", "space": "", "extra": ""}, "name_not_taken"),
    ({"core": "take", "space": "", "extra": ""}, "bare_verb"),
    ({"core": "orchestrating hybrid-cloud infrastructures", "space": "", "extra": "AWS, Azure, VMware"},
     "names_in_extra"),
    ({"core": "training and evaluating machine learning models", "space": "", "extra": ""}, "verb_run_left"),
    # controls
    ({"core": "business", "space": "", "extra": ""}, None),
    ({"core": "backend services in production environments", "space": "", "extra": ""}, None),
    ({"core": "English", "space": "language", "extra": ""}, None),
])
def test_the_inspector_sees_batch_4s_shapes(record, flag):
    assert errors.review_flag(record) == flag


def test_shapes_across_one_item():
    reqs = [{"core": "banking products"}, {"core": "national"}, {"core": "EU financing mechanisms"}]
    assert errors.item_flags(reqs) == {1: "shared_tail_lost"}
    ok = [{"core": "documentation"}, {"core": "architectural modelling"}]
    assert errors.item_flags(ok) == {}


def test_the_items_years_reach_every_part():
    from karimi_normalise import requirements
    rs = requirements.split("5+ years of Enterprise software QA and test automation experience", translate=False)
    assert [r.years_min for r in rs] == [5] * len(rs) and len(rs) >= 2
    # a degree is not qualified by the years beside it
    rs = requirements.split("Any degree and 8+ years of relevant experience", translate=False)
    assert [r.years_min for r in rs if r.space == "education"] == [None]


# Roles in alternative (the user's call, 2026-11-18): one role written several
# ways is that role; different roles are separate requirements.
@pytest.mark.parametrize("item, keys", [
    ("Experience working as an Azure Cloud Architect, Lead Architect or Design Architect", ["Cloud Architect"]),
    ("3+ years of experience as a Senior Backend Developer or Software Engineer", ["Backend Developer"]),
    ("Experience as a Data Engineer or Data Scientist", ["Data engineering", "Data science"]),  # rules 0.4.11: the merges of 2026-11-26
    ("Experience as Product Owner or Business Analyst", ["Product Owner", "Business Analyst"]),
    ("Experience as a Salesforce Developer or Business Developer", ["Salesforce Developer", "Business Developer"]),
])
def test_roles_in_alternative(item, keys):
    assert [k.lower() for k in _keys(item)] == [k.lower() for k in keys]


def test_the_inspector_sees_roles_left_together():
    rec = {"core": "Data Engineer or Data Scientist", "space": "experience", "extra": ""}
    assert errors.review_flag(rec) == "roles_in_key"
    assert errors.review_flag({**rec, "core": "Cloud Architect"}) is None
    assert errors.review_flag({**rec, "core": "Python or Java"}) is None
