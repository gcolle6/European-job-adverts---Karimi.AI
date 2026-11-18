"""Rules 0.4.4: every error the agents found in batch 3 of the new postings (2026-11-17).

    python -m pytest tests/test_rules_044.py

Batch 3 measured rules 0.4.3 and is now development; batch 4 measures. The
inputs are the English the API split (or the item as written where it was not
translated), each with what it holds and the controls beside it.
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


@pytest.mark.parametrize("item, keys", [
    # an engineering school's diploma or a master in computing: two routes, both master level
    ("Bac+5 (Ecole d'Ingénieur ou Master Informatique)",
     ["education: Master (any field)", "education: Master in Informatique"]),
    ("Bac+2 training in Supply Chain and/or Master Data Management",
     ["education: Degree in Supply Chain", "education: Degree in Master Data Management"]),
    ("Good degree in an appropriate subject or significant experience in a Software Engineering environment",
     ["education: Degree (any field)", "Software Engineering environment"]),
    ("Bachelor's degree or equivalent (minimum 12 years) work experience", ["education: Bachelor (any field)", "work"]),
    ("Higher education within business, finance, data science or a related field",
     ["education: Degree in business", "education: Degree in finance", "education: Degree in data science"]),
    ("Hbo work and think level and at least 5 years experience within cybersecurity",
     ["education: Bachelor (any field)", "cybersecurity"]),
    ("Bachelor’s degree with preference for Information Systems or Computer Science",
     ["education: Bachelor in Information Systems", "education: Bachelor in Computer Science"]),
    ("Bachelor's degree or equivalent higher education qualification in Information Technology, Computer Science",
     ["education: Bachelor in Information Technology", "education: Bachelor in Computer Science"]),
    ("Bac+2 training at baccalaureate+5", ["education: Degree (any field)"]),
    ("BS Degree - preferably in a technical discipline", ["education: Bachelor (any field)"]),
    ("A completed MSc or higher professional education degree in geotechnical engineering or related subjects",
     ["education: Master in geotechnical engineering", "education: Bachelor in geotechnical engineering"]),
    ("Master's degree as a statistician, physicist, mathematician or lignnde", ["education: Master (any field)"]),
    ("Bachelor's, Master's, or higher degree in Computer Science, Electrical Engineering",
     ["education: Bachelor in Computer Science", "education: Bachelor in Electrical Engineering",
      "education: Master in Computer Science", "education: Master in Electrical Engineering"]),
    ("Good Bachelor's or Master's degree, ideally with economic relevance",
     ["education: Bachelor (any field)", "education: Master (any field)", "economic relevance"]),
    ("HBO+/WO work and thinking level within IT", ["education: Bachelor in IT", "education: Degree in IT"]),
    ("Current studies at the University of Applied Sciences Upper Austria Campus Hagenberg in the fields of computer "
     "science, software engineering or a similar subject",
     ["education: Student in computer science", "education: Student in software engineering"]),
    ("Prior Fintech experience is not a requirement, but an asset", ["Fintech"]),
    ("Experience in handling system architectures beneficial", ["system architectures"]),
])
def test_degrees_and_words_from_batch_3(item, keys):
    assert _keys(item) == keys


def test_or_similar_role_goes_before_a_comma_too():
    # kept whole for the compound reader, as before; what changed is `or similar role` in the middle
    keys = _keys("Proven experience as a Data Engineer or similar role, ideally with a focus on AI, machine learning")
    assert keys and all("similar" not in k for k in keys)


def test_the_school_leaving_certificate_is_not_a_bachelor():
    en = atom.repair_translation("Bachillerato concluido (High school diploma completed)",
                                 "Bachelor's degree completed (High school diploma completed)")
    assert en.startswith("High school diploma")


@pytest.mark.parametrize("item, code", [
    ("Nivel de inglés mínimo B2", "es"),
    ("Gestión de riesgos tecnológicos asociados a infraestructura", "es"),
    ("HBO+ of WO werk- en denkniveau in Data Science, GIS, Computer Science of vergelijkbare richting", "nl"),
    ("poznavanje C#/.NET-a (ili spremnost na rad u .NET okruženju) i SQL-a", "mul"),
    ("Kandidatuddannelse inden for datalogi, bioinformatik, statistik eller beslægtet fagområde", "da"),
    ("3 à 5 années d'expérience en développement de logiciels embarqués", "fr"),
    # controls
    ("Experience with Kubernetes in a cloud environment", None),
    ("Strong knowledge of SQL and Python", None),
    ("Erfarenhet av programmering med Python", "sv"),
])
def test_languages_batch_3_showed(item, code):
    assert translate.item_code(item) == code


@pytest.mark.parametrize("item, keys", [
    ("Master Data Management", ["Master Data Management"]),
    ("Bachelor's degree in Computer Science or equivalent experience", ["education: Bachelor in Computer Science", ""]),
    ("Experience with Go is a plus", ["Go"]),
])
def test_controls_stay(item, keys):
    assert _keys(item) == keys


# The user's review of batch 2 (100 items, 2026-11-17) and the conventions it
# settled: a name wins over the words around it, NAMED examples are the
# requirements and the category goes, common-noun examples and what
# `including` adds stay with the category.
@pytest.mark.parametrize("item, keys", [
    ("Solid cloud experience (AWS or Azure), including infrastructure as code", ["AWS", "Azure"]),
    ("Experience with ERP systems such as SAP or Oracle", ["SAP", "Oracle"]),
    ("Scripting languages such as Python or Bash", ["Python", "Bash"]),
    ("Knowledge of data protection laws, healthcare IT standards (e.g., HIPAA, GDPR), and cybersecurity "
     "frameworks (e.g., NIST, ISO 27001)", ["data protection laws", "HIPAA", "GDPR", "NIST", "ISO 27001"]),
    ("CAN Protocol, Diagnosis (KwP, UDS), ISO 14229", ["CAN Protocol", "KwP", "UDS", "ISO 14229"]),
    ("Full-stack development experience (Ruby on Rails / React / Typescript / PostgreSQL)",
     ["Ruby on Rails", "React", "Typescript", "PostgreSQL"]),
    ("Experience with relational databases (PostgreSQL, MySQL)", ["PostgreSQL", "MySQL"]),
    ("Knowledge in digital components such as Ethernet switch, memories, modem", ["digital components"]),
    ("Cloud engineering experience on Azure", ["Azure"]),
    ("Good programming knowledge in Python", ["Python"]),
    ("Highly organized with the ability to manage multiple requests",
     ["organized", "manage multiple requests"]),  # `Highly` is the level column
    ("Curious, open-minded, eager to learn", ["Curious", "open-minded", "eager to learn"]),
    ("3 years or more of experience in Java", ["Java"]),
    ("Ability to build and manage a sales pipeline", ["sales pipeline"]),
    ("Experience in Java is given priority", ["Java"]),
    ("WO programme in Computer Science", ["education: Degree in Computer Science"]),
    ("Student Bac+5 in engineering school or university master's degree in computer science",
     ["education: Master in computer science"]),
])
def test_review_of_batch_2(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    # controls: a name beside its category word, a licence class, an interest
    ("Experience in IT project management", ["IT project management"]),
    ("Driving licence B", ["Driving licence"]),
    ("Interest in AI", ["Interest in AI"]),
    ("Lean Explorer certification", ["Lean Explorer certification"]),
    ("Proven experience as a Product Owner", ["Product Owner"]),
    ("Strong testing habits (JUnit, Mockito)", ["JUnit", "Mockito"]),
    ("Master's degree (business, engineering)", ["education: Master in business", "education: Master in engineering"]),
])
def test_review_controls(item, keys):
    assert _keys(item) == keys


def test_one_key_once_per_item():
    assert normalise_req.first_per_key(["Systems thinking", "Systems thinking", "", "", "Python"]) == \
        [True, False, True, True, True]
