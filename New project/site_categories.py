"""A category for each requirement of the site's explorer, so the list can be browsed by kind.

    python "New project/site_categories.py"        # print the categories of the current explorer list

Asked for by the user on 2026-11-10: 800 requirements in one alphabetical list
are hard to search. The method is the one Week 1 validated for requirement
types (`karimi/classify_embed.py`): a few example phrases per category, their
mean embedding as the category's prototype, and each requirement goes to the
nearest one, or to `Other` when no prototype is near enough. No labels needed,
and a wrong seed is visible and fixable here. Languages and degrees are not
guessed: their space says what they are (`normalise_req.space`).

For browsing only. The categories are not a finding and nothing downstream
counts by them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import embed  # noqa: E402

LANGUAGES, EDUCATION, OTHER = "Languages", "Education", "Other"
MIN_SIMILARITY = 0.35     # below it, `Other`: set by reading the list, 2026-11-11

# The order is the order the site shows them in.
SEEDS: dict[str, list[str]] = {
    "Programming languages": ["Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "Kotlin",
                              "Scala", "PHP", "Ruby", "Swift", "R", "Bash", "PowerShell", "programming languages"],
    "Frameworks & libraries": ["React", "Angular", "Vue", "Spring Boot", "Django", ".NET", "Node.js", "Pandas",
                               "PyTorch", "TensorFlow", "Flutter", "FastAPI", "Hibernate", "scikit-learn"],
    "Data & AI": ["machine learning", "data analysis", "data engineering", "statistics", "LLMs", "deep learning",
                  "data modeling", "data visualization", "Spark", "ETL", "data science", "NLP", "AI",
                  "data pipelines", "data governance", "Databricks", "analytics"],
    "Databases": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "Oracle database", "relational databases", "NoSQL",
                  "Snowflake", "data warehouse", "Redis", "SQL Server"],
    "Cloud & DevOps": ["AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "CI/CD", "DevOps", "Linux",
                       "Infrastructure as Code", "monitoring", "Ansible", "cloud platforms", "Jenkins",
                       "observability", "virtualization"],
    "Security & networks": ["cybersecurity", "network security", "firewalls", "IAM", "TCP/IP", "ISO 27001",
                            "networking", "encryption", "SIEM", "routing", "vulnerability management",
                            "access management"],
    "Software engineering": ["software engineering", "system design", "microservices", "APIs", "testing",
                             "software architecture", "debugging", "clean code", "object-oriented programming",
                             "design patterns", "REST APIs", "Git", "unit testing", "distributed systems",
                             "backend development", "frontend development", "embedded systems"],
    "Tools & business software": ["Excel", "Microsoft Office", "Jira", "SAP", "Power BI", "Tableau", "Salesforce",
                                  "Confluence", "ServiceNow", "PowerPoint", "ERP", "CRM", "SharePoint"],
    "Methods & management": ["Agile methodologies", "Scrum", "project management", "stakeholder management",
                             "product management", "ITIL", "risk management", "requirements management",
                             "change management", "people management", "planning", "Kanban"],
    "Business & industry": ["finance", "banking", "sales", "consulting", "telecommunications", "automotive",
                            "compliance", "healthcare", "supply chain", "marketing", "GDPR", "insurance",
                            "business development", "regulations", "logistics"],
    "Soft skills": ["communication", "teamwork", "problem-solving", "autonomy", "leadership",
                    "attention to detail", "curiosity", "flexibility", "proactive", "analytical skills",
                    "organizational skills", "willingness to learn", "work independently", "sense of responsibility",
                    "rigor", "creativity", "customer orientation", "time management"],
}
ORDER = list(SEEDS) + [LANGUAGES, EDUCATION, OTHER]


CACHE = HERE / "output" / "site_categories.json"
BATCH = 20
# A degree by its name, when the batch did not put it in the education space.
# `master` only as a degree: `Master data management` is data.
_DEGREE_NAME = re.compile(r"^(?:education|bachelor|master(?:'s|’s)\b|master\s+(?:degree|in|of)\b|bac\+\d|msc|bsc|"
                          r"phd|completed hbo|hbo|degree|studies|completed studies|technical degree|"
                          r"currently enrolled|successful completion of studies|training in|completed it training)\b",
                          re.I)
# Read on the list the model made, 2026-11-11: where it is wrong on a name the
# list shows often, the category is written here and wins. A closed list.
OVERRIDES = {
    "Git": "Software engineering", "GitHub": "Software engineering", "GitLab": "Software engineering",
    "ITIL": "Methods & management", "ITIL processes": "Methods & management", "Scrum": "Methods & management",
    "TOGAF": "Methods & management", "Docker": "Cloud & DevOps", "GCP": "Cloud & DevOps",
    "Helm": "Cloud & DevOps", "Prometheus": "Cloud & DevOps", "Grafana": "Cloud & DevOps",
    "Confluence": "Tools & business software", "Snowflake": "Databases", "Kafka": "Data & AI",
    "RabbitMQ": "Software engineering", "Spark": "Data & AI", "PySpark": "Data & AI", "BigQuery": "Databases",
    "Redshift": "Databases", "DynamoDB": "Databases", "Elasticsearch": "Databases", "Hibernate": "Frameworks & libraries",
    "Spring Boot": "Frameworks & libraries", "Selenium": "Software engineering", "Playwright": "Software engineering",
    "Postman": "Software engineering", "JUnit": "Software engineering", "Entra ID": "Security & networks",
    "JWT": "Security & networks", "OAuth": "Security & networks", "Windows Server": "Cloud & DevOps",
    "Analytical skills": "Soft skills", "Analytical mind": "Soft skills",
    "Analytical thinking and problem-solving skills": "Soft skills", "Computer Science": "Software engineering",
    "SEO": "Business & industry", "BGP": "Security & networks", "Talend": "Data & AI", "Airflow": "Data & AI",
    "Dbt": "Data & AI", "Looker": "Data & AI", "Tableau": "Data & AI", "Power BI": "Data & AI",
    "Master data management": "Data & AI", "CI/CD pipeline creation": "Cloud & DevOps", "Firmware": "Software engineering",
    "Lambda": "Cloud & DevOps", "Operating systems": "Software engineering", "Mobile development": "Software engineering",
    "Frontend": "Software engineering", "Frontend development": "Software engineering", "IOS": "Software engineering",
    "Android": "Software engineering", "MATLAB": "Programming languages", "Microsoft Fabric": "Data & AI",
    "Windows": "Cloud & DevOps", "Windows environments": "Cloud & DevOps", "Windows Server": "Cloud & DevOps",
    "Object-oriented programming": "Software engineering", "Visual Studio": "Software engineering",
    "Node.js": "Frameworks & libraries", "Read technical drawings": "Business & industry",
    "Open-source": "Software engineering", "Driving licence": OTHER,
}
_RETRY = 5   # names the model left unanswered are asked again, five at a time
# What each category holds, for the model: the seeds above are examples, this is the rule.
_MEANING = {
    "Programming languages": "a programming, scripting or markup language (Python, Bash, HTML)",
    "Frameworks & libraries": "a software framework or library (React, Spring Boot, Pandas)",
    "Data & AI": "data analysis, data engineering, statistics, machine learning, AI, and their platforms",
    "Databases": "a database or database technology (SQL, PostgreSQL, Snowflake, MongoDB)",
    "Cloud & DevOps": "cloud providers, containers, CI/CD, infrastructure, monitoring (AWS, Docker, Terraform)",
    "Security & networks": "cybersecurity, identity, networking and its protocols (firewalls, TCP/IP, IAM)",
    "Software engineering": "how software is designed, built and tested (APIs, microservices, testing, Git)",
    "Tools & business software": "office and business applications (Excel, Jira, SAP, Power BI, Salesforce)",
    "Methods & management": "ways of working and managing (Agile, Scrum, project management, ITIL)",
    "Business & industry": "knowledge of an industry or business area (finance, sales, GDPR, automotive)",
    "Soft skills": "personal and interpersonal qualities (communication, teamwork, autonomy)",
    OTHER: "anything else: licences, travel, availability, or a phrase that names nothing",
}


def _ask(url: str, names: list[str]) -> dict[str, str]:
    """One batch of names to the local model; {name: category} for the answers it gave validly."""
    import json as _json
    import urllib.request

    cats = "\n".join(f"- {c}: {m}" for c, m in _MEANING.items())
    listing = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names))
    msg = (f"Put each job requirement into exactly one category.\n\nCategories:\n{cats}\n\n"
           f"Requirements:\n{listing}\n\nAnswer with one line per requirement, `<number>. <category>`, "
           f"using the category names exactly as written. /no_think")
    body = _json.dumps({"messages": [{"role": "user", "content": msg}], "temperature": 0,
                        "max_tokens": 40 * len(names)}).encode()
    req = urllib.request.Request(f"{url}/v1/chat/completions", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        text = _json.loads(r.read())["choices"][0]["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    valid = {c.casefold(): c for c in _MEANING}
    out = {}
    for m in re.finditer(r"^\s*(\d+)\.\s*(.+?)\s*$", text, re.M):
        k, cat = int(m.group(1)) - 1, valid.get(m.group(2).strip(" *`").casefold())
        if 0 <= k < len(names) and cat:
            out[names[k]] = cat
    return out


def categorise(names: list[str], spaces: list[str], model=None, judge_url: str | None = None) -> list[str]:
    """One category per requirement name; ``spaces`` from the batch (`language`, `education`, "").

    With ``judge_url`` (the project's local model, `llama-server`), the model
    decides, in batches, cached in CACHE so a rerun asks only for new names:
    product names carry no meaning an embedding can read (`Snowflake` landed
    in `Other`, `Jira` in `Cloud & DevOps`, measured 2026-11-11). The
    prototypes stay for what the model leaves unanswered, and when it is off."""
    import json as _json

    fixed = {n: LANGUAGES if s == "language" else EDUCATION
             for n, s in zip(names, spaces) if s in ("language", "education") or _DEGREE_NAME.match(n)}
    asked: dict[str, str] = _json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if judge_url:
        for size in (BATCH, _RETRY):
            todo = [n for n in names if n not in fixed and n not in asked and n not in OVERRIDES]
            for i in range(0, len(todo), size):
                asked.update(_ask(judge_url, todo[i:i + size]))
        CACHE.write_text(_json.dumps(asked, ensure_ascii=False, indent=1), encoding="utf-8")
    rest = [n for n in names if n not in fixed and n not in asked and n not in OVERRIDES]
    by_proto = dict(zip(rest, _prototypes(rest, model))) if rest else {}
    return [fixed.get(n) or OVERRIDES.get(n) or asked.get(n) or by_proto[n] for n in names]


def _prototypes(names: list[str], model=None) -> list[str]:
    """Nearest category prototype (mean embedding of its seeds), or `Other` below MIN_SIMILARITY."""
    model = model or embed.load_model(embed.DEFAULT_MODEL)
    cats = list(SEEDS)
    protos = []
    for c in cats:
        v = embed.encode(model, SEEDS[c]).astype(np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        m = v.mean(axis=0)
        protos.append(m / np.linalg.norm(m))
    p = np.stack(protos)
    x = embed.encode(model, names).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    sims = x @ p.T
    out = []
    for s in sims:
        j = int(s.argmax())
        out.append(cats[j] if s[j] >= MIN_SIMILARITY else OTHER)
    return out


if __name__ == "__main__":
    import json
    from collections import defaultdict

    ix = json.loads((HERE.parent.parent / "karimi-normalise-site" / "public" / "data" / "explore" / "index.json")
                    .read_text(encoding="utf-8"))
    by = defaultdict(list)
    for r in ix["requirements"]:
        by[r.get("category", "?")].append(r["name"])
    for c in ORDER + ["?"]:
        if by.get(c):
            print(f"\n== {c} ({len(by[c])})\n   " + " | ".join(sorted(by[c], key=str.casefold)))
