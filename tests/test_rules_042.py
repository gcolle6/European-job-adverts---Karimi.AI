"""Rules 0.4.2: degrees read wrong in the first batch of new postings (2026-11-15).

    python -m pytest tests/test_rules_042.py

Cases from batch 1 only, the development batch; batch 2 measures. Each case
is what an employer wrote and the requirements it holds, as the API splits
and names them, with the controls that must not change beside them.
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
    return [normalise_req.decompose(normalise_req.normalise_requirement(a, False))["key"] for a in atoms]


@pytest.mark.parametrize("item, keys", [
    # degree names the rules did not know
    ("BA/BS Degree in STEM or Business Administration",
     ["education: Bachelor in STEM", "education: Bachelor in Business Administration"]),
    ("B.E. / B.Tech / MCA in Computer Science or related field",
     ["education: Bachelor in Computer Science", "education: Master in Computer Science"]),
    ("BS in Computer Science", ["education: Bachelor in Computer Science"]),
    ("MS in Computer Science", ["education: Master in Computer Science"]),
    ("HBO or WO degree in marketing", ["education: Bachelor in marketing", "education: Degree in marketing"]),
    ("Completed HBO", ["education: Bachelor (any field)"]),
    ("BS / BA degree or equivalent years of experience", ["education: Bachelor (any field)", ""]),
    # how much it is wanted, closing the degree
    ("Ph.D. preferred", ["education: PhD (any field)"]),
    ("Master's strongly preferred", ["education: Master (any field)"]),
    ("PhD is a plus", ["education: PhD (any field)"]),
    ("MBA or other relevant advanced degree preferred", ["education: MBA (any field)"]),
    ("Bachelor's degree preferred (Engineering, Computer Science, Analytics)",
     ["education: Bachelor in Engineering", "education: Bachelor in Computer Science",
      "education: Bachelor in Analytics"]),
    ("Bachelor's / Undergraduate Degree (Computer Science, Systems Engineering, or related field)",
     ["education: Bachelor in Computer Science", "education: Bachelor in Systems Engineering"]),
    # an experience as the other route, or beside the degree
    ("Bachelor’s degree or relevant experience", ["education: Bachelor (any field)", ""]),
    ("Degree in Economics, Statistics or related experience",
     ["education: Degree in Economics", "education: Degree in Statistics", ""]),
    ("Master's degree and 4 years of relevant experience", ["education: Master (any field)", ""]),
    ("Master's degree 2–3 years of relevant experience", ["education: Master (any field)", ""]),
    ("Bachelor’s with 10+ years", ["education: Bachelor (any field)", ""]),
    ("Bachelor’s degree or equivalent experience, Master’s Degree Preferred",
     ["education: Bachelor (any field)", "", "education: Master (any field)"]),
    # words in front of degrees in alternative
    ("Relevant bachelor's or master's degree in Computer Science, Machine Learning",
     ["education: Bachelor in Computer Science", "education: Bachelor in Machine Learning",
      "education: Master in Computer Science", "education: Master in Machine Learning"]),
    ("Bachelor's degree student +4/5 in Business School", ["education: Student (any field)"]),
    # read off the inspector's flags left on batch 1 after the fixes above
    ("Bachelor's degree required in Statistics", ["education: Bachelor in Statistics"]),
    ("A bachelor's degree, or equivalent in Information Technology", ["education: Bachelor in Information Technology"]),
    ("A completed Master's degree, preferably in Data Science or a related field",
     ["education: Master in Data Science"]),
    ("HBO work and thinking level", ["education: Bachelor (any field)"]),
    ("Degree in Computer Science, Engineering or related field or experience",
     ["education: Degree in Computer Science", "education: Degree in Engineering", ""]),
    ("BA/BS degree", ["education: Bachelor (any field)"]),
])
def test_degrees_from_the_first_batch(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("item, keys", [
    ("Master data management", ["Master data management"]),
    ("Experience with BS 7799", ["BS 7799"]),
    ("MS Office", ["Microsoft Office"]),
    ("Be in the office 3 days a week", ["Be in the office 3 days a week"]),
    ("Digital asset management", ["Digital asset management"]),
    ("Bachelor's degree in Physics and Mathematics", ["education: Bachelor in Physics", "education: Bachelor in Mathematics"]),
    ("Bachelor's degree in Computer Science or equivalent experience", ["education: Bachelor in Computer Science", ""]),
])
def test_controls_stay(item, keys):
    assert _keys(item) == keys


@pytest.mark.parametrize("text, key", [
    ("Python is a plus", "Python"), ("Python preferred", "Python"), ("Python (preferred)", "Python"),
    ("German is strongly preferred", "language: German"), ("Ansible is a plus", "Ansible"),
    ("Kafka would be an advantage", "Kafka"), ("Desirable", ""),
    ("TwinCAT software preferred", "TwinCAT"),  # the name wins since 0.4.4 ("M-Files will be advantageous", "M-Files"),
    ("Microsoft Purview; this is a plus", "Microsoft Purview"),
    # the marker inside a bracket that names something stays for the bracket rule
    ("cloud infrastructure (AWS preferred)", "cloud infrastructure"),
    ("Master's degree with specialisation in business economics", "education: Master in business economics"),
])
def test_how_much_it_is_wanted_is_not_the_requirement(text, key):
    assert normalise_req.decompose(text)["key"] == key


def test_preferred_closing_an_atom_is_optional():
    assert atom.counted(["Bachelor's degree in Computer Science", "Master's preferred"]) == [True, False]
    assert atom.nice_to_have("PhD a plus") and atom.nice_to_have("Python (preferred)")
    assert not atom.nice_to_have("Preferred Shares accounting")
    assert not atom.nice_to_have("Confidence in working with cloud infrastructure (AWS preferred)")


def test_a_masters_student_is_a_student():
    # the 0.4.1 test closed on a backspace, not `\b`, so it never fired
    assert normalise_req.decompose("Master's student in Physics")["degree"] == "student"


def test_no_rule_source_holds_a_control_character():
    """The 0.4.1 patches went through a shell heredoc, which turned `\\b` into a
    backspace in two patterns: one rule and one guard dead without a sound."""
    from karimi_normalise import versions

    for rel in versions.RULE_SOURCES + ["karimi_normalise/errors.py", "karimi_normalise/curator.py"]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        bad = [ch for ch in text if ord(ch) < 32 and ch not in "\n\r\t"]
        assert not bad, rel
