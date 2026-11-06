"""The data behind the site's explorer: how each requirement is asked for, where.

    python "New project/site_requirements.py" "../karimi-normalise-site/public/data/explore"

Aggregates only, from the batch (`must_have_atoms.parquet`, `titles.parquet`)
and the export (country, company id): counts of adverts, never text, never a
company. Per requirement: the role families and roles that ask for it most
(as a share of that family's or role's adverts, so a big family does not win
by size), how it is asked (experience, competence, ...), level, years,
countries, and the requirements that come with it.

A requirement here is a `req_topic` without its head (`competence: python`
and `experience: python` are both Python), the unit a reader means by
"Python". Listed only if at least MIN_ADS adverts from at least MIN_COMPANIES
companies ask for it: one employer's template posted 131 times (`fof`,
`ddx`, ...) is not a trend. Generic objects that name nothing (`technical`,
`equivalent`) are left out by an explicit list.

Role families do not exist in the data: they are read off the role name by
the keyword rules in FAMILIES, first match wins, and are provisional. The
share of adverts each one takes, and the share left in "Altro", is printed.
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXPORT = HERE.parent / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"

MIN_ADS = 30
MIN_COMPANIES = 8
MIN_ROLE_ADS = 40
MIN_COUNTRY_ADS = 100
MIN_JOINT = 20
TOP_ROLES, TOP_COUNTRIES, TOP_WITH = 12, 8, 10

# Objects that name no requirement on their own: fragments of the frame.
GENERIC = {
    "technical", "equivalent", "work", "it", "development", "business", "experience", "data", "engineering",
    "tools", "team", "industry", "standards", "management", "services", "processes", "organization",
    "structured", "commercial", "production", "frameworks", "relational", "similar application",
    "similar role", "thinking level", "data-management role", "design", "integration", "programming",
    "architecture", "infrastructure", "platform", "systems", "solutions", "technology", "technologies",
    "skills", "knowledge", "environment", "environments", "methods", "concepts", "principles",
}

# (family, regex on the lower-case role name). First match wins.
FAMILIES = [
    ("Sicurezza", r"secur|cyber|\bsoc\b|penetration|pentest|\biam\b|identity"),
    ("Dati e AI", r"data scien|machine learning|\bml\b|\bai\b|artificial intelligence|\bnlp\b|computer vision|"
                  r"\bllm|deep learning|research scientist|applied scientist"),
    ("Data engineering", r"data engineer|analytics engineer|big data|\betl\b|data platform|data architect|"
                         r"databricks|data warehouse|dwh"),
    ("Analisi e BI", r"data analyst|\bbi\b|business intelligence|analytics|reporting|power bi|tableau"),
    ("Architettura", r"architect"),
    ("Qualità e test", r"\bqa\b|quality assurance|test|sdet"),
    ("Cloud e DevOps", r"devops|cloud|platform engineer|\bsre\b|site reliability|kubernetes|infrastructure|"
                       r"systems engineer|system engineer|network|linux|sysadmin|system administrator"),
    ("Prodotto e progetti", r"product owner|product manager|project manager|scrum|agile coach|delivery manager|"
                            r"program manager|programme manager|business analyst|business application|"
                            r"functional analyst|systems analyst|technical analyst"),
    ("Supporto IT", r"support|help ?desk|service desk|technician|it specialist|it administrator|administrator"),
    ("Vendite e consulenza", r"sales|business develop|account|pre-?sales|consultant|customer success"),
    ("Guida tecnica", r"lead|manager|director|head of|cto|chief|principal|team leader"),
    ("Sviluppo software", r"software|developer|engineer|backend|back-end|frontend|front-end|full ?stack|"
                          r"programmer|java|python|\.net|\bnet\b|mobile|ios|android|web|embedded|firmware|"
                          r"golang|php|c\+\+|c#"),
]
OTHER = "Altro"


def family(role: str) -> str:
    r = (role or "").lower()
    for name, pat in FAMILIES:
        if re.search(pat, r):
            return name
    return OTHER


def main(dest: str) -> None:
    a = pd.read_parquet(OUT / "must_have_atoms.parquet",
                        columns=["posting_id", "req_topic", "req_head_group", "req_core", "req_level", "req_years_min"])
    a = a[a.req_topic.notna() & (a.req_topic != "")]
    a["obj"] = a.req_topic.str.replace(r"^[a-z ]+: ", "", regex=True).str.strip()
    a = a[~a.obj.isin(GENERIC) & (a.obj != "")]

    t = pd.read_parquet(OUT / "titles.parquet", columns=["posting_id", "title_name"]).drop_duplicates("posting_id")
    ex = pd.DataFrame([{"posting_id": r["_id"], "company": r.get("company_id"), "country": r.get("geo_country") or ""}
                       for r in json.loads(EXPORT.read_text(encoding="utf-8"))])
    ads = (pd.DataFrame({"posting_id": a.posting_id.unique()})
           .merge(t, on="posting_id", how="left").merge(ex, on="posting_id", how="left"))
    ads["title_name"] = ads.title_name.fillna("")
    ads["family"] = ads.title_name.map(family)
    total = len(ads)

    fam_n = ads.family.value_counts()
    role_n = ads.title_name.value_counts()
    country_n = ads.country.value_counts()
    print(f"{total} adverts; families:")
    for f, n in fam_n.items():
        print(f"  {f:22} {n:6} {n / total:6.1%}")

    per = a.merge(ads, on="posting_id")
    by_obj = per.groupby("obj")
    stats = pd.DataFrame({"ads": by_obj.posting_id.nunique(), "companies": by_obj.company.nunique()})
    keep = stats[(stats.ads >= MIN_ADS) & (stats.companies >= MIN_COMPANIES)].sort_values("ads", ascending=False)
    print(f"{len(keep)} requirements kept of {len(stats)} (>= {MIN_ADS} adverts, >= {MIN_COMPANIES} companies)")

    pa = per[per.obj.isin(keep.index)]
    ad_sets = pa.groupby("obj").posting_id.agg(set).to_dict()
    names = (pa.groupby(["obj", "req_core"]).size().reset_index(name="n").sort_values("n", ascending=False)
             .drop_duplicates("obj").set_index("obj").req_core.to_dict())
    slug = {o: re.sub(r"[^a-z0-9]+", "-", o.lower()).strip("-") or "r" for o in keep.index}
    meta = ads.set_index("posting_id")

    reqs = []
    for o in keep.index:
        s = ad_sets[o]
        m = meta.loc[list(s)]
        rows = pa[pa.obj == o]
        fam = m.family.value_counts()
        roles = m.title_name.value_counts()
        roles = roles[(roles.index != "") & roles.index.map(lambda r: role_n.get(r, 0) >= MIN_ROLE_ADS)]
        ctry = m.country.value_counts()
        ctry = ctry[(ctry.index != "") & ctry.index.map(lambda c: country_n.get(c, 0) >= MIN_COUNTRY_ADS)]
        yrs = rows.req_years_min.dropna()
        bins = [("0-1", 0, 1), ("2", 2, 2), ("3", 3, 3), ("4", 4, 4), ("5", 5, 5), ("6-7", 6, 7), ("8+", 8, 99)]
        withs = []
        for o2 in keep.index:
            if o2 == o:
                continue
            j = len(s & ad_sets[o2])
            if j >= MIN_JOINT:
                withs.append((o2, j, j * total / (len(s) * len(ad_sets[o2]))))
        withs = sorted(withs, key=lambda x: (-x[2], -x[1]))[:TOP_WITH]
        reqs.append({
            "id": slug[o], "name": names.get(o, o), "ads": int(len(s)), "companies": int(keep.companies[o]),
            "share": round(len(s) / total, 5),
            "families": sorted([{"family": f, "ads": int(n), "share": round(n / fam_n[f], 5)} for f, n in fam.items()],
                               key=lambda x: -x["share"]),
            "roles": sorted([{"role": r, "family": family(r), "ads": int(n), "share": round(n / role_n[r], 5)}
                             for r, n in roles.items()], key=lambda x: -x["share"])[:TOP_ROLES],
            "asked_as": {k or "(senza testa)": int(v) for k, v in rows.req_head_group.value_counts().items()},
            "levels": {k: int(v) for k, v in rows.req_level.replace("", pd.NA).dropna().value_counts().head(6).items()},
            "years": {"atoms_with_years": int(len(yrs)),
                      "bins": [{"bin": b, "n": int(((yrs >= lo) & (yrs <= hi)).sum())} for b, lo, hi in bins]},
            "countries": sorted([{"country": c, "ads": int(n), "share": round(n / country_n[c], 5)}
                                 for c, n in ctry.items()], key=lambda x: -x["share"])[:TOP_COUNTRIES],
            "with": [{"id": slug[o2], "name": names.get(o2, o2), "ads": int(j), "lift": round(l, 2)}
                     for o2, j, l in withs],
        })

    out = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "source": {"adverts": total, "what": "annunci software e data, export europeo di agosto 2026",
                   "rules": {"min_ads": MIN_ADS, "min_companies": MIN_COMPANIES, "min_role_ads": MIN_ROLE_ADS,
                             "min_country_ads": MIN_COUNTRY_ADS},
                   "families_note": "famiglie di ruoli provvisorie, lette dal nome del ruolo con parole chiave"},
        "families": [{"family": f, "ads": int(n)} for f, n in fam_n.items()],
        "requirements": reqs,
    }
    # An index the page loads at once (names, sizes, share per family in a fixed
    # order) and one small file per requirement, fetched when it is clicked.
    order = [f for f, _ in FAMILIES] + [OTHER]
    base = Path(dest)
    (base / "req").mkdir(parents=True, exist_ok=True)
    for old in (base / "req").glob("*.json"):
        old.unlink()
    index = {**{k: out[k] for k in ("generated", "source")},
             "families": [{"family": f, "ads": int(fam_n.get(f, 0))} for f in order],
             "requirements": [{"id": r["id"], "name": r["name"], "ads": r["ads"], "share": r["share"],
                               "by_family": [next((round(x["share"], 4) for x in r["families"] if x["family"] == f), 0)
                                             for f in order]} for r in reqs]}
    (base / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for r in reqs:
        (base / "req" / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")),
                                                     encoding="utf-8")
    size = sum(f.stat().st_size for f in (base / "req").glob("*.json"))
    print(f"{len(reqs)} requirements -> {base}/index.json ({(base / 'index.json').stat().st_size / 1024:.0f} KB), "
          f"req/*.json ({size / 1024:.0f} KB in all, {size / len(reqs) / 1024:.1f} KB each)")


if __name__ == "__main__":
    main(sys.argv[1])
