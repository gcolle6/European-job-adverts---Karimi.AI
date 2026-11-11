"""Every pattern in PATTERNS.md, pinned by its own examples and controls.

    python "New project/test_patterns.py"

The splitter is meant to run on `must_have` text nobody has seen yet, so a
change that silently breaks one pattern while improving another is the main
risk. Each case is a sentence used to build or check a rule (2026-10-29/31),
with the requirement COUNT the conventions give (`atom.counted`, so optional
parts do not add). Pipeline as in `split_must_have.py`: English input, repairs
and tagger on. Exits non-zero on any failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from karimi import atomise as atom  # noqa: E402
from karimi import config  # noqa: E402

# (pattern, text, expected count)
CASES = [
    # P1 head + list, and its limits
    ("P1", "3+ years in helpdesk or IT support", 2),
    ("P1", "Experience with Docker and Kubernetes", 2),
    ("P1 between", "Ability to switch between vision and detail", 1),
    ("P1 between", "Strong product instincts with ability to make trade-offs between scope, quality and timeline", 1),
    ("P1 between", "A communicator who moves easily between researchers, engineers, and hardware teams", 1),
    ("P1 between", "Strong communication skills and ability to switch smoothly between business and IT", 2),
    ("P1 within", "2-5 years of experience in supply chain management within operations or planning", 1),
    ("P1 within", "Experience within banking, insurance or retail", 3),
    ("P1 number", "Experience working in environments with at least 100,000 endpoints", 1),
    # P2 shared tail
    ("P2", "Good control of Linux and Windows operating systems", 2),
    ("P2", "Hands-on experience with open-source and commercial deception platforms", 2),
    ("P2", "Knowledge of networking and security protocols", 2),
    ("P2", "Strong analytical and problem-solving competences", 2),
    ("P2", "Linux and Unix experience", 2),
    ("P2 singular", "Structured and project-based work", 1),
    ("P2 singular", "A calm, methodical, and pragmatic approach", 1),
    ("P2 control", "Experience with gap analysis and remediation planning", 2),
    ("P2 control", "Proficiency with Git and collaborative development workflows", 2),
    ("P2 control", "Ability to communicate clearly with customers and non-technical stakeholders", 2),
    ("P2 control", "Good knowledge of Linux and Windows Server administration", 2),
    ("P2a modes", "Excellent written and verbal communication", 1),
    ("P2a modes", "Strong written and verbal communication skills in English", 1),
    ("P2 skills", "Strong communication and interpersonal skills", 2),
    # P3 alternatives in the head
    ("P3", "Bachelor's or Master's degree in Computer Science or Software Engineering", 4),
    # P4 coordinated verbs
    ("P4", "Ability to recruit, grow, and retain top talent", 1),
    ("P4", "Demonstrated ability to design, run, and debug real production systems", 1),
    ("P4", "Experience designing and deploying services across Linux and Windows", 2),
    ("P4", "Ability to install, re-seat, and swap GPU/PCIe cards, NICs, PSUs, and drives", 4),
    ("P4 control", "Ability to document defects and communicate with project teams", 2),
    ("P4 control", "Skills in prospecting, lead generation and closing deals", 3),
    ("P4 control", "Experience in sales, marketing and business development", 3),
    ("P4 ability", "Proven ability to analyze software requirements and derive clear architectural specifications", 2),
    # P6 qualifiers
    ("P6", "Expertise in Power BI, particularly in complex data modeling", 1),
    ("P6", "5-8 years of experience in SAP master data, ideally within life sciences or healthcare operations", 1),
    ("P6 both", "Excellent communicative skills, both in Dutch and English.", 2),
    ("P6 both", "Very good knowledge of Swedish and English, both in speech and writing.", 2),
    # a second language after `ideally` is a requirement of its own (the user, 2026-11-11)
    ("P6 control", "Fluent English, ideally German", 2),
    ("P6 control", "Ability to communicate clearly with customers", 1),
    # P8 fillers and alternative paths
    ("P8", "Degree in Computer Science or a related field", 1),
    ("P8", "Degree in Computer Science or equivalent experience", 2),
    ("P8", "Experience with Python, Java and related frameworks", 2),
    ("P8", "Demonstrated familiarity with the SAVOIR FDIR Handbook and related reference architectures", 1),
    # P9 languages
    ("P9", "Fluent in French and English", 2),
    # nice to have
    ("plus", "Fluent in English; Dutch is a strong plus", 1),
    ("plus", "Background in IT support and maintenance experience is a plus", 1),
    ("plus", "Experience with Zendesk Apps Framework is a plus", 1),
    # P10-P15, from the first sales sample (2026-11-02); controls from software
    ("P13", "The ability to operate effectively across a complex, fast‑paced and multidisciplinary environment", 1),
    ("P13", "Ability to create a welcoming and inclusive customer experience", 1),
    ("P14", "Business or customer-related experience", 2),
    ("P15", "Experience designing REST APIs and building data pipelines", 2),
    ("P15", "Demonstrated success in building regional sales strategies and consistently meeting or exceeding revenue objectives", 2),
    ("P15 control", "Experience building and maintaining CI/CD pipelines", 1),
    ("P11b", "Comfortable discussing APIs, webhooks, and cloud patterns", 3),
    ("controls", "Bachelor's or Master's degree", 2),
    ("controls", "Rigor and analytical spirit", 2),
    ("controls", "Teamwork and communication skills", 2),
    ("controls", "Sales experience and comfort with targeting new business", 2),
]

# Wording, where the count was already right and the atoms were not: (text, atoms)
ATOM_CASES = [
    ("Willingness to work in the afternoon, in the evening and on Saturdays",
     ["Willingness to work in the afternoon", "Willingness to work in the evening",
      "Willingness to work on Saturdays"]),
    ("Ability to effectively influence across functions and across sites",
     ["Ability to effectively influence across functions", "Ability to effectively influence across sites"]),
    ("A willingness to learn and good communication skills",
     ["A willingness to learn", "good communication skills"]),
    ("Analytical skills with data-driven approach and CRM system experience",
     ["Analytical skills with data-driven approach", "CRM system experience"]),
    ("Comfortable discussing APIs, webhooks, and cloud patterns",
     ["Comfortable discussing APIs", "Comfortable discussing webhooks", "Comfortable discussing cloud patterns"]),
    ("Experience designing REST APIs and building data pipelines",
     ["Experience designing REST APIs", "Experience building data pipelines"]),
    ("Experience with Docker and Kubernetes", ["Experience with Docker", "Experience with Kubernetes"]),
]


# Job titles (`karimi/normalise_title.py`): (title, role key, level)
TITLE_CASES = [
    ("data scientist", "data scientist", ""),
    ("Data Scientist", "data scientist", ""),
    ("Engineer of data", "data engineer", ""),
    ("Data Engineer", "data engineer", ""),
    # A feminine ending on the word is gender; a level phrase after a dash is a level.
    ("Stagiair(e) IT Support", "it support", "intern"),
    ("Data Analyst - Alternance", "analyst data", "intern"),
    ("Lehrstelle Logistiker", "logistiker", "intern"),
    ("Senior Data Engineer (m/w/d)", "data engineer", "senior"),
    ("(Senior) Data Engineer", "data engineer", "senior"),
    ("Lead Data Engineer", "data engineer", "lead"),
    ("Data Analyst - Internship", "analyst data", "intern"),
    ("Internship - Data Science", "data science", "intern"),
    ("Medior/Senior Front-End Developer", "developer end front", "mid|senior"),
    ("Software Engineer II", "engineer software", "grade 2"),
    ("Incident Support Engineer - SAPIENT", "engineer incident support", ""),
    # controls: a role word stays where it is the role
    ("Tech Lead", "lead tech", ""),
    ("Battery Integration Expert", "battery expert integration", ""),
    ("Research Associate", "associate research", ""),
    ("Head of Data", "data head", ""),
]
# Spelling variants that must join, and roles that must never join.
TITLE_SAME = [("Full-Stack Engineer", "Fullstack Engineer"), ("Systems Engineer", "System Engineer"),
              ("Site Reliability Engineer", "SRE"), ("Software Developer", "Software Engineer"),
              ("Backend Developer", "Engineer Backend")]
TITLE_DIFFERENT = [("Data Analyst", "Data Scientist"), ("Data Engineer", "Data Scientist"),
                   ("Data Analyst", "Analytics Engineer"), ("Data Engineer", "Head of Data"),
                   ("Business Developer", "Business Engineer"), ("Developer Platform Engineer", "Platform Engineer"),
                   # Developer = Engineer only for the X the user listed (2026-11-04).
                   ("System Developer", "Systems Engineer"), ("Solution Developer", "Solutions Engineer"),
                   ("Platform Developer", "Platform Engineer"), ("IT Developer", "IT Engineer"),
                   ("Developer", "Engineer"), ("Analytics Developer", "Analytics Engineer")]
TITLE_SAME += [("Fullstack Developer", "Full Stack Engineer"), ("Backend Java Developer", "Java Backend Engineer"),
               ("PLSQL Developer", "PL/SQL Engineer"), ("iOS Developer", "iOS Engineer")]


# Normalised wording (`karimi/normalise_req.py`): (text, translated?, expected)
NORM_CASES = [
    ("Experience building and maintaining CI/CD pipelines", False, "Experience with CI/CD pipelines"),
    ("3+ years of experience designing, building and deploying microservices", False,
     "3+ years of experience with microservices"),
    ("Experience working with distributed systems", False, "Experience with distributed systems"),
    ("Experience working in agile teams", False, "Experience in agile teams"),
    ("Experience leading engineering teams", False, "Experience leading engineering teams"),
    ("Experience in marketing and sales", False, "Experience in marketing and sales"),
    ("Experience in marketing campaigns", False, "Experience in marketing campaigns"),
    ("Experience designing", False, "Experience designing"),
    ("Flowing knowledge of German in word and writing", True, "Fluent knowledge of German written and spoken"),
    ("Negotiable knowledge of German", True, "Business-fluent knowledge of German"),
    ("Safe handling of MS Office", True, "Confident use of MS Office"),
    ("Flowing water systems", False, "Flowing water systems"),
    ("Experience with logging solutions", False, "Experience with logging solutions"),
    ("Experience designing and implementing monitoring solutions using Prometheus", False,
     "Experience with monitoring solutions using Prometheus"),
    ("Experience contributing to risk management", False, "Experience contributing to risk management"),
    ("Experience working as a peer to product managers", False,
     "Experience working as a peer to product managers"),
    ("Experience turning AI/LLM capabilities into practical workflows", False,
     "Experience turning AI/LLM capabilities into practical workflows"),
]


# Decomposition (`normalise_req.decompose`): (text, expected key, expected level, years_min)
KEY_CASES = [
    ("3+ years of strong hands-on experience with Kubernetes", "Kubernetes", "strong", 3),
    ("Strong knowledge of SQL", "SQL", "strong", None),
    ("Proficiency in SQL", "SQL", "advanced", None),
    ("Familiarity with SQL", "SQL", "basic", None),
    ("SQL skills", "SQL", "", None),
    ("Minimum of 3 years' experience in data engineering", "data engineering", "", 3),
    ("5 years in software development", "software development", "", 5),
    ("Expertise in Power BI, particularly in complex data modeling", "Power BI", "expert", None),
    ("Fluent knowledge of German written and spoken", "language: German", "strong", None),
    ("Excellent written and verbal English skills", "language: English", "strong", None),
    ("Native German", "language: German", "expert", None),
    ("Excellent written and verbal communication", "written and verbal communication", "strong", None),
    ("Python", "Python", "", None),
    ("Fluency in English", "language: English", "strong", None),
    ("in English", "language: English", "", None),
    ("Strong problem-solving skills with excellent attention to detail", "problem-solving", "strong", None),
    ("Analytical mindset with the ability to structure", "Analytical mindset with the ability to structure", "", None),
]


def main() -> int:
    from karimi import normalise_req

    config.SPLIT_REPAIRS = True
    config.SPLIT_POS = True
    failed = 0
    for pattern, text, want in CASES:
        atoms = atom.route(text)[0]
        got = sum(atom.counted(atoms))
        if got != want:
            failed += 1
            print(f"FAIL {pattern:12s} want {want} got {got}: {text}\n     {atoms}")
    for text, want in ATOM_CASES:
        got = atom.route(text)[0]
        if got != want:
            failed += 1
            print(f"FAIL atoms        want {want}\n                  got  {got}")
    for text, translated, want in NORM_CASES:
        got = normalise_req.normalise_requirement(text, translated)
        if got != want:
            failed += 1
            print(f"FAIL norm         want {want!r}\n                  got  {got!r}")
    for text, key, level, years in KEY_CASES:
        d = normalise_req.decompose(text)
        if (d["key"], d["level"], d["years_min"]) != (key, level, years):
            failed += 1
            print(f"FAIL key          want {(key, level, years)}\n                  got  "
                  f"{(d['key'], d['level'], d['years_min'])}  <- {text}")
    from karimi import normalise_title as nt
    for title, want_key, want_level in TITLE_CASES:
        d = nt.decompose(title)
        if (d["key"], d["level"]) != (want_key, want_level):
            failed += 1
            print(f"FAIL title        want {(want_key, want_level)}\n                  got  "
                  f"{(d['key'], d['level'])}  <- {title}")
    acr = {"sre": "site reliability engineer"}
    for pairs, same in ((TITLE_SAME, True), (TITLE_DIFFERENT, False)):
        for a, b in pairs:
            ra, rb = nt.decompose(a)["role"], nt.decompose(b)["role"]
            g = nt.group_titles([ra, rb], acr)
            if (g[nt.key(ra, acr)] == g[nt.key(rb, acr)]) != same:
                failed += 1
                print(f"FAIL title group  {a!r} and {b!r} should {'' if same else 'not '}join")
    total = (len(CASES) + len(ATOM_CASES) + len(NORM_CASES) + len(KEY_CASES) + len(TITLE_CASES)
             + len(TITLE_SAME) + len(TITLE_DIFFERENT))
    print(f"{total - failed}/{total} pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
