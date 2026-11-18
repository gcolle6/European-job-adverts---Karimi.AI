"""Rules 0.4.3: every error the agents found in batch 2 of the new postings (2026-11-17).

    python -m pytest tests/test_rules_043.py

Batch 2 is now development (the user's process: each batch's errors are all
fixed before the next batch measures). The inputs are the English the API
split; each case is what it holds, as the API splits and names it, with the
controls that must not change beside them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402
from karimi_normalise import translate  # noqa: E402


def _keys(item: str) -> list[str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    return [normalise_req.decompose(normalise_req.normalise_requirement(a, True))["key"] for a in atoms]


def _counted(item: str) -> list[bool]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    atoms, _ = atom.route(item)
    return atom.counted(atoms)


@pytest.mark.parametrize("item, keys", [
    # degrees the rules did not read
    ("Bac + 3 / L3 in Accounting/Finance", ["education: Bachelor in Accounting/Finance"]),
    ("B.E. / B.Tech or equivalent in Computer Science (CS), Information Science (IS), or Electronics & "
     "Communication Engineering",
     ["education: Bachelor in Computer Science", "education: Bachelor in Information Science",
      "education: Bachelor in Electronics & Communication Engineering"]),
    ("Bac+5 course in computer science with specialization in cybersecurity", ["education: Master in computer science"]),
    ("Bachelor's degree (Graduate)", ["education: Bachelor (any field)"]),
    ("Master's degree required; PhD strongly preferred in Biology, Genetics",
     ["education: Master (any field)", "education: PhD in Biology", "education: PhD in Genetics"]),
    ("Bachelor’s degree required, Master’s preferred, in Computer Science, IT",
     ["education: Bachelor in Computer Science", "education: Bachelor in IT",
      "education: Master in Computer Science", "education: Master in IT"]),
    ("Bachelor’s or Master’s degree with deep technical knowledge on AI ML products",
     ["education: Bachelor (any field)", "education: Master (any field)", "AI ML products"]),
    ("Completed HBO or WO training in a technical direction, e.g. Electrical engineering or Technical Informatics",
     ["education: Bachelor in Electrical engineering", "education: Bachelor in Technical Informatics",
      "education: Degree in Electrical engineering", "education: Degree in Technical Informatics"]),
    ("Completed HBO or WW training in IT, Business Administration or a similar direction",
     ["education: Bachelor in IT", "education: Bachelor in Business Administration",
      "education: Degree in IT", "education: Degree in Business Administration"]),
    ("HBO work and thinking level towards Electrical engineering, Mechatronics, or similar",
     ["education: Bachelor in Electrical engineering", "education: Bachelor in Mechatronics"]),
    ("HBO Technique or comparable level of work and thinking", ["education: Bachelor in Technique"]),
    ("Hbo- or wo-work- and think-level", ["education: Bachelor (any field)", "education: Degree (any field)"]),
    ("Master's degree/triennial degree in Engineering or Economics",
     ["education: Master in Engineering", "education: Master in Economics",
      "education: Bachelor in Engineering", "education: Bachelor in Economics"]),
    ("A PhD or equivalent research experience in machine learning, computer science",
     ["education: PhD in machine learning", "education: PhD in computer science", "research"]),
    ("Bac +3 training minimum, ideally in trade", ["education: Bachelor in trade"]),
    ("Bachelor's degree+5 or engineering school in Data, Statistics or Computer Science",
     ["education: Master in Data", "education: Master in Statistics", "education: Master in Computer Science"]),
    ("Bachelor’s degree or 8+ years of directly related professional experience", ["education: Bachelor (any field)", ""]),
    ("Bachelor's degree in Computer Science or suitable combination of education, experience, and training",
     ["education: Bachelor in Computer Science", ""]),
    ("Bachelor’s or equivalent in User Experience, Design, or STEM",
     ["education: Bachelor in User Experience", "education: Bachelor in Design", "education: Bachelor in STEM"]),
    ("BSE (EE, ECE, CS, or similar) required",
     ["education: Bachelor in EE", "education: Bachelor in ECE", "education: Bachelor in CS"]),
    ("Higher education (optional in economic, marketing or logistics)", ["education: Degree (any field)"]),
    ("Master's degree (or equivalent) with experience in Microsoft Power Platform and Microsoft 365 environments",
     ["education: Master (any field)", "Microsoft Power Platform and Microsoft 365 environments"]),
    ("Bachelor’s degree in Computer Science or related degree", ["education: Bachelor in Computer Science"]),
    # read while checking every change on batches 1 and 2
    ("Master's degree with engineering, scientific or economic direction",
     ["education: Master in engineering", "education: Master in scientific", "education: Master in economic"]),
    ("A completed Bachelor's degree in business administration or similar (beta) training",
     ["education: Bachelor in business administration"]),
    ("Bachelor’s Degree or higher in Electrical & Electronics/ECE",
     ["education: Bachelor in Electrical & Electronics/ECE"]),
    ("Bachelor's degree in IT or equivalent through experience", ["education: Bachelor in IT", ""]),
])
def test_degrees_from_batch_2(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    # how much it is wanted, in the translator's words
    ("Experience in SAP Advantage", ["SAP"]),
    ("Green Belt appreciated", ["Green Belt"]),
    ("Experience with Cisco Meraki is an express plus", ["Cisco Meraki"]),
    ("Very good German and English; other national languages of advantage",
     ["language: German", "language: English", "other national languages"]),
    ("Cloud Services (Azure, Microsoft 365) Advantage", ["Cloud Services"]),
    ("Experience with AWS or Azure is a plus, but not required", ["AWS", "Azure"]),
    ("Lean Explorer certification, desired", ["Lean Explorer certification"]),
    # named examples are the requirements since 0.4.4 (the user's call of 2026-11-17)
    ("Relevant certifications preferred (e.g., ISO 27001 Lead Auditor/Implementer, CISM, CISSP, CISA)",
     ["ISO 27001 Lead Auditor/Implementer", "CISM", "CISSP", "CISA"]),
    ("Desirable experience in design", ["design"]),
    ("Advantageous knowledge of English", ["language: English"]),
    # `required`, `or similar`, a level after the name
    ("U.S. Citizenship is required", ["U.S. Citizenship"]),
    ("English B2+ required", ["English B2+"]),
    ("Graduation is mandatory", ["Graduation"]),
    ("Proven experience as a Product Owner or similar role", ["Product Owner"]),
    ("Practical knowledge of Ansible, Terraform or similar", ["Ansible", "Terraform"]),
    ("Some experience in Python, R or similar", ["Python", "R"]),
    ("LangChain Intermediate", ["LangChain"]),
    ("Python Advanced", ["Python"]),
    # the explorer's kinds, confirmed by the user's process of 2026-11-17
    ("Experience in design, deployment and support of network solutions",
     ["design, deployment and support of network solutions"]),
    ("Experience gathering, structuring, and documenting functional requirements", ["functional requirements"]),
    ("Practical knowledge about microservices and REST API", ["microservices", "REST APIs"]),
    ("Qualifications/experience/knowledge of data science is a major advantage", ["data science"]),
    ("CATIA V6-Knowledge Advantageous", ["CATIA V6"]),
    ("At least five years of progressively responsible experience in software analysis, design, development and "
     "programming", ["software analysis", "design", "development", "programming"]),
    ("I hear English is very fluent in reading and writing.", ["language: English"]),
    ("7+ years in technology delivery, with 4+ years as a Scrum Master, Delivery Lead, Agile PM, or similar",
     ["technology delivery", "Scrum Master", "Delivery Lead", "Agile PM"]),
    ("Master's Pack Office", ["Master's Pack Office"]),       # kept for repair_translation, below
])
def test_words_that_add_nothing_and_the_explorers_kinds(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    ("Visual Basic", ["Visual Basic"]),
    ("Advanced analytics", ["analytics"]),          # a level in front, as before 0.4.3
    ("Willingness to travel when required", ["Willingness to travel when required"]),
    ("Competitive advantage analysis", ["Competitive advantage analysis"]),
    ("Experience with Kubernetes, ideally on AWS", ["Kubernetes"]),
    ("Bachelor's degree in Computer Science or equivalent experience", ["education: Bachelor in Computer Science", ""]),
    ("Ability to pass Basic Plus or equal safety training", ["pass Basic Plus", "pass equal safety training"]),
])
def test_controls_stay(item, keys):
    assert _keys(item) == keys


def test_optional_ones_are_marked_and_counted_by_the_convention():
    # optional as a whole still counts (2026-10-30); beside a required one it does not
    for item in ("Desirable experience in design", "Lean Explorer certification, desired", "Green Belt appreciated"):
        config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
        atoms, _ = atom.route(item)
        assert len(atoms) == 1 and atom.nice_to_have(atoms[0]) and _counted(item) == [True], item
    assert _counted("Master's degree required; PhD strongly preferred in Biology") == [True, False]
    assert _counted("Graduation is mandatory") == [True]


def test_the_translations_put_right():
    assert atom.repair_translation("Maîtrise Pack office", "Master's Pack Office") == "Strong knowledge of Pack Office"
    assert normalise_req.decompose("Strong knowledge of Pack Office")["key"] == "Microsoft Office"
    assert atom.repair_translation("Minimum de 5 ans d'expérience en maîtrise d'œuvre",
                                   "Minimum of 5 years of Master of Works experience") == \
        "Minimum of 5 years of construction project management experience"


@pytest.mark.parametrize("item, code", [
    ("Erfaring med at afdække behov og omsætte dem til krav", "da"),
    ("Kokemusta yleisimmistä ohjelmointikielistä esim. JavaScript, TypeScript, Node.js", "fi"),
    ("Halua ja kykyä toimia yhteistyössä kansainvälisessä ympäristössä", "fi"),
    ("Anglický jazyk na komunikativní úrovni", "cs"),
    ("Déploiement CI/CD (Docker) Confirmé", "fr"),
    ("Erfarenhet av programmering med Python", "sv"),       # Swedish stays Swedish
    ("Experience in a fast-paced environment", None),       # English stays as written
    ("Kenntnisse des Systems und gute Deutschkenntnisse", "de"),
])
def test_languages_batch_2_showed_go_to_their_own_model(item, code):
    assert translate.item_code(item) == code
    if code in ("da", "fi", "cs"):
        assert translate.model_for(code) == f"opus-mt-{code}-en"


def test_an_acronym_ending_in_s_keeps_its_s():
    assert normalise_req.canon("IDMS") == "idms" and normalise_req.canon("HRIS") == "hris"
    assert normalise_req.canon("data platforms") == "data platform"
