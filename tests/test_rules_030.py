"""Rules 0.3.0: the items from the first real trial (2026-11-09) and the user's list of 2026-11-10.

    python -m pytest tests/test_rules_030.py

Splitting as the API runs it (repairs and tagger on, `split_posting`), and the
grouping key: `Experience with Python` and `Knowledge of Python` are one
requirement, a degree is `education: <field>` with the degree in its own column.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi import atomise as atom, config, normalise_req, pos  # noqa: E402


def _split(item: str) -> tuple[list[str], str]:
    config.SPLIT_REPAIRS, config.SPLIT_POS = True, True
    pos.prime([item])
    return atom.route(item)


@pytest.mark.parametrize("item, atoms", [
    ("Solid knowledge and use of SQL", ["Solid knowledge of SQL"]),
    ("Experience using frameworks like Spark, Tensorflow, scikit-learn, pandas",
     ["Experience using Spark", "Experience using Tensorflow", "Experience using scikit-learn",
      "Experience using pandas"]),
    ("Understanding of the Microsoft ecosystem (Azure, data, AI, custom development)",
     ["Understanding of the Microsoft ecosystem"]),
    ("Speak English fluently, in combination with Dutch or French", ["Speak English fluently", "Dutch", "French"]),
    ("Very good knowledge of German and good knowledge of English",
     ["Very good knowledge of German", "good knowledge of English"]),
    ("Very good knowledge of German and English", ["Very good knowledge of German", "Very good knowledge of English"]),
    ("Experience developing firmware using RTOS frameworks such as FreeRTOS or Zephyr",
     ["Experience developing firmware using FreeRTOS", "Experience developing firmware using Zephyr"]),
    ("Proficient with both Windows and Linux OS", ["Proficient with Windows OS", "Proficient with Linux OS"]),
    ("Reliable, proactive, and self-motivated", ["Reliable", "proactive", "self-motivated"]),
    ("2+ years of related experience as a Machine Learning or Software engineer",
     ["2+ years of related experience as a Machine Learning or Software engineer"]),
    ("Proficiency in Python for modelling, data analysis and automation",
     ["Proficiency in Python for modelling, data analysis and automation"]),
    ("Willingness to acquire knowledge in web technologies such as Angular, TypeScript or Next.js",
     ["Willingness to acquire knowledge in Angular", "Willingness to acquire knowledge in TypeScript",
      "Willingness to acquire knowledge in Next.js"]),
])
def test_trial_items_split_as_the_user_reads_them(item, atoms):
    assert _split(item)[0] == atoms


def test_kept_whole_on_purpose_is_single_not_llm():
    # `llm` means "looks compound, could not separate": not what these are.
    assert _split("Solid knowledge and use of SQL")[1] == "single"
    assert _split("2+ years of related experience as a Machine Learning or Software engineer")[1] == "single"


def test_ideally_names_are_kept_and_not_counted():
    atoms, _ = _split("Experience with BI tools, ideally Excel, Qlik Sense or comparable solutions")
    assert atoms[-2:] == ["Ideally Excel", "Ideally Qlik Sense"]
    assert atom.counted(atoms) == [True] * (len(atoms) - 2) + [False, False]


def test_controls_unchanged():
    # coordinated adjectives before a singular noun stay one (2026-10-30)
    assert len(_split("Structured and project-based work")[0]) == 1
    # a bracket of names still expands
    assert len(_split("Experience with integration platforms (Boomi, MuleSoft, Talend)")[0]) == 3
    # `both written and spoken` is one ask
    assert len(_split("Excellent communication, both written and spoken")[0]) == 1


@pytest.mark.parametrize("text, key, head_group", [
    ("Experience with Python", "Python", "experience"),
    ("Knowledge of Python", "Python", "competence"),
    ("Python skills", "Python", "competence"),
    ("Familiar with Docker", "Docker", "competence"),
    ("Good programming knowledge in Python", "Python", "competence"),
    ("Proficiency in Python for modelling, data analysis and automation", "Python", "competence"),
    ("Multi-year experience in platform architecture", "platform architecture", "experience"),
    ("Speak English fluently", "language: English", "language"),
    ("Very good knowledge of German", "language: German", "language"),
])
def test_one_key_however_it_is_asked(text, key, head_group):
    d = normalise_req.decompose(text)
    assert (d["key"], d["head_group"]) == (key, head_group)


@pytest.mark.parametrize("text, key, degree", [
    ("MSc in Physics", "Master in Physics", "master"),
    ("M.Sc. in Physics", "Master in Physics", "master"),
    ("Master's degree in Physics", "Master in Physics", "master"),
    ("PhD in Physics", "PhD in Physics", "phd"),
    ("Doctorate in Physics", "PhD in Physics", "phd"),
    ("Degree in Physics", "Degree in Physics", "degree"),
    ("Completed studies in Computer Science", "Degree in Computer Science", "degree"),
    ("Bachelor's degree in Economics", "Bachelor in Economics", "bachelor"),
    ("BSc in Economics", "Bachelor in Economics", "bachelor"),
    ("MSc (or equivalent) in Telecommunication Engineering", "Master in Telecommunication Engineering", "master"),
    ("Ongoing studies in Data Science", "Student in Data Science", "student"),
    ("Bachelor's degree", "Bachelor (any field)", "bachelor"),
])
def test_each_degree_is_its_own_requirement(text, key, degree):
    # rules 0.4.0, the user's call 2026-11-11: `Master in Business` and `Bachelor in
    # Business` are two requirements; every spelling of one degree is that degree
    d = normalise_req.decompose(text)
    assert (d["key"], d["degree"], d["space"]) == (f"education: {key}", degree, "education")


def test_education_needs_the_degree_in_front():
    assert normalise_req.decompose("Experience in education technology")["head_group"] == "experience"
    assert normalise_req.display("education", "Master in Physics") == "Master in Physics"


# The duplicates the site's explorer showed on 2026-11-10: one requirement, one key.
@pytest.mark.parametrize("texts, key", [
    (["English (B2)", "level of English", "English required", "technical English", "communication in English",
      "You are fluent in English", "with a good knowledge of English", "English (written and spoken)",
      "written and verbal communication skills in English"], "language: English"),
    (["German is a plus", "German (min. C1)", "Very good knowledge of German"], "language: German"),
    (["Golang", "Go"], "Go"),
    (["PowerBI", "Power BI"], "Power BI"),
    (["MS Office", "Office package", "Microsoft Office"], "Microsoft Office"),
    (["Microsoft Excel", "use of Excel", "Excel"], "Excel"),
    (["Microsoft Azure", "Azure"], "Azure"),
    (["Google Cloud Platform", "Google Cloud", "GCP"], "GCP"),
    (["Vue.js", "Vue"], "Vue"),
    (["Driving licence B", "Valid driver's license"], "Driving licence"),
    (["Git version control", "Use of Git", "Git"], "Git"),
    (["version control (Git)", "version control"], "version control"),
])
def test_spellings_of_one_requirement_share_a_key(texts, key):
    assert {normalise_req.decompose(t)["key"] for t in texts} == {key}


@pytest.mark.parametrize("a, b", [
    ("problem-solving", "problem solving"), ("time-management", "time management"),
    ("data modelling", "data modeling"), ("rigour", "Rigor"), ("data platforms", "data platform"),
    ("Infrastructure as Code", "infrastructure-as-code"), ("REST APIs", "RESTful APIs"),
])
def test_spellings_share_a_canonical_form(a, b):
    ka, kb = (normalise_req.decompose(x)["core"] for x in (a, b))
    assert normalise_req.canon(ka) == normalise_req.canon(kb)


@pytest.mark.parametrize("text", ["of", "You have", "Senior-level", "Multi-year", "Minimum", "Ideally"])
def test_debris_names_nothing(text):
    assert normalise_req.decompose(text)["core"] == ""


def test_controls_keep_their_words():
    # a frame only at the start: `access control`, `AI use` are what is asked
    assert normalise_req.decompose("access control")["key"] == "access control"
    assert normalise_req.decompose("AI use")["key"] == "AI use"
    # `Interest in AI` is not the AI skill
    assert normalise_req.decompose("Interest in AI")["key"] == "Interest in AI"
    assert normalise_req.display("", "analytical") == "Analytical skills"
    assert normalise_req.display("", "proactive") == "Proactive"


@pytest.mark.parametrize("text", ["Communicate in English", "High level of English",
                                  "English, both in speech and writing", "Are fluent in English",
                                  "Current professional English, both in writing and oral",
                                  "Clear written and spoken English communication skills", "Business English"])
def test_one_language_with_any_words_around_it(text):
    assert normalise_req.decompose(text)["key"] == "language: English"


@pytest.mark.parametrize("text", ["English literature", "Teach English", "English and German"])
def test_a_language_inside_something_else_is_not_the_language(text):
    assert normalise_req.decompose(text)["key"] != "language: English"


def test_ideally_before_a_language_adds_one():
    # the user's call 2026-11-11: two requirements, both counted
    atoms, _ = _split("Fluent English, ideally German")
    assert atoms == ["Fluent English", "ideally German"] and atom.counted(atoms) == [True, True]


@pytest.mark.parametrize("item, atoms", [
    ("MSc or PhD in Physics", ["MSc in Physics", "PhD in Physics"]),
    ("Bachelor's or Master's degree in Computer Science",
     ["Bachelor's degree in Computer Science", "Master's degree in Computer Science"]),
    ("MSc/PhD in Physics", ["MSc in Physics", "PhD in Physics"]),
    ("BA or MA (or equivalent) in Economics", ["BA (or equivalent) in Economics", "MA (or equivalent) in Economics"]),
])
def test_degrees_in_alternative_share_the_field(item, atoms):
    # rules 0.3.1: with one field the first degree was left bare (`MSc`), since 0.2.0
    assert _split(item)[0] == atoms
