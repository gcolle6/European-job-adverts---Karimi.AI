"""The data behind the site's explorer: how each requirement is asked for, and where.

    python "New project/site_requirements.py" "../karimi-normalise-site/public/data/explore"

Aggregates only, from the batch (`must_have_atoms.parquet`, `titles.parquet`)
and the export (country, seniority, company id): counts of adverts, never
text, never a company. One role family for now, Software and data (the
export's `macro_function`); sub-families were tried and dropped, decided
2026-11-06.

Per requirement, the five charts of the explorer:

1. roles      — the roles that ask for it most, as a share of that role's adverts;
2. seniority  — the share at each seniority level, against all its adverts;
3. asked      — how it is asked (experience, competence, ...) and at what level;
4. countries  — the share in each country, against all its adverts;
5. with       — the requirements that come with it: how much more often than
                anywhere (lift) and how many of its adverts ask for them too.

A requirement is a `req_topic` without its head (`competence: python` and
`experience: python` are both Python), the unit a reader means by "Python".
Listed only if at least MIN_ADS adverts from at least MIN_COMPANIES companies
ask for it: one employer's template posted 131 times (`fof`, `ddx`, ...) is
not a trend. Generic objects that name nothing (`technical`, `equivalent`)
are left out by an explicit list. Writes an index the page loads at once and
one small file per requirement, fetched when it is chosen.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXPORT = HERE.parent / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"

FAMILY = "Software and data"
MIN_ADS = 30
MIN_COMPANIES = 8
MIN_ROLE_ADS = 40
MIN_GROUP_ADS = 100          # a seniority level or a country, to be shown at all
MIN_JOINT = 20
TOP_ROLES, TOP_WITH = 12, 30
SENIORITY = ["Internship", "Junior", "Mid-level", "Senior"]   # C-Level: 53 adverts, too few
LEVELS = ["basic", "good", "strong", "advanced", "expert"]    # the five level words, by intensity
ASKED = {"experience": "As experience", "competence": "As a skill", "ability": "As an ability",
         "language": "As a language", "": "Named alone"}
COUNTRY_EN = {
    "Deutschland": "Germany", "Nederland": "Netherlands", "España": "Spain", "België": "Belgium",
    "Italia": "Italy", "Sverige": "Sweden", "Polska": "Poland", "Schweiz": "Switzerland", "România": "Romania",
    "Österreich": "Austria", "Česko": "Czechia", "Danmark": "Denmark", "Ελλάδα": "Greece",
    "Magyarország": "Hungary", "България": "Bulgaria", "Slovensko": "Slovakia", "Suomi": "Finland",
    "Éire": "Ireland",
}

# Objects that name no requirement on their own: fragments of the frame.
GENERIC = {
    "technical", "equivalent", "work", "it", "development", "business", "experience", "data", "engineering",
    "tools", "team", "industry", "standards", "management", "services", "processes", "organization",
    "structured", "commercial", "production", "frameworks", "relational", "similar application",
    "similar role", "thinking level", "data-management role", "design", "integration", "programming",
    "architecture", "infrastructure", "platform", "systems", "solutions", "technology", "technologies",
    "skills", "knowledge", "environment", "environments", "methods", "concepts", "principles",
}


def _slugs(objs) -> dict[str, str]:
    """A file name per requirement, unique. Symbols that name languages survive
    (`c++`, `c#`): reduced to letters they all became `c`, one file for three."""
    out, seen = {}, {}
    for o in objs:
        s = o.lower().replace("c++", "c-plus-plus").replace("c#", "c-sharp").replace(".net", "dotnet")
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "r"
        n = seen.get(s, 0)
        seen[s] = n + 1
        out[o] = s if n == 0 else f"{s}-{n + 1}"
    return out


def _shares(col: pd.Series, base: pd.Series, keep: list[str] | None = None) -> list[dict]:
    """Share of each group's adverts that ask for it; groups with too few adverts left out."""
    n = col.value_counts()
    groups = keep if keep is not None else [g for g in base.index if base[g] >= MIN_GROUP_ADS]
    return [{"group": g, "ads": int(n.get(g, 0)), "of": int(base[g]), "share": round(n.get(g, 0) / base[g], 5)}
            for g in groups if g in base.index and base[g] >= MIN_GROUP_ADS]


def main(dest: str) -> None:
    a = pd.read_parquet(OUT / "must_have_atoms.parquet",
                        columns=["posting_id", "req_topic", "req_head_group", "req_core", "req_level"])
    a = a[a.req_topic.notna() & (a.req_topic != "")]
    # One requirement whatever the apostrophe or the spacing: `master's` and
    # `master’s` were two before 2026-11-06.
    a["obj"] = (a.req_topic.str.replace(r"^[a-z ]+: ", "", regex=True).str.replace("’", "'", regex=False)
                .str.replace(r"\s+", " ", regex=True).str.strip().str.lower())
    a = a[~a.obj.isin(GENERIC) & (a.obj != "")]

    t = pd.read_parquet(OUT / "titles.parquet", columns=["posting_id", "title_name"]).drop_duplicates("posting_id")
    ex = pd.DataFrame([{"posting_id": r["_id"], "company": r.get("company_id"),
                        "country": COUNTRY_EN.get(r.get("geo_country") or "", r.get("geo_country") or ""),
                        "seniority": r.get("seniority") or ""}
                       for r in json.loads(EXPORT.read_text(encoding="utf-8"))])
    ads = (pd.DataFrame({"posting_id": a.posting_id.unique()})
           .merge(t, on="posting_id", how="left").merge(ex, on="posting_id", how="left"))
    ads["title_name"] = ads.title_name.fillna("")
    total = len(ads)
    role_n = ads.title_name.value_counts()
    country_n = ads.country[ads.country != ""].value_counts()
    sen_n = ads.seniority.value_counts()
    print(f"{total} adverts; seniority {sen_n.to_dict()}")

    per = a.merge(ads, on="posting_id")
    by_obj = per.groupby("obj")
    stats = pd.DataFrame({"ads": by_obj.posting_id.nunique(), "companies": by_obj.company.nunique()})
    keep = stats[(stats.ads >= MIN_ADS) & (stats.companies >= MIN_COMPANIES)].sort_values("ads", ascending=False)
    print(f"{len(keep)} requirements kept of {len(stats)} (>= {MIN_ADS} adverts, >= {MIN_COMPANIES} companies)")

    pa = per[per.obj.isin(keep.index)]
    ad_sets = pa.groupby("obj").posting_id.agg(set).to_dict()
    names = (pa.groupby(["obj", "req_core"]).size().reset_index(name="n").sort_values("n", ascending=False)
             .drop_duplicates("obj").set_index("obj").req_core.to_dict())
    slug = _slugs(keep.index)
    meta = ads.set_index("posting_id")
    by_rows = {o: g for o, g in pa.groupby("obj")}

    reqs = []
    for o in keep.index:
        s = ad_sets[o]
        m = meta.loc[list(s)]
        rows = by_rows[o]
        roles = m.title_name.value_counts()
        roles = roles[(roles.index != "") & roles.index.map(lambda r: role_n.get(r, 0) >= MIN_ROLE_ADS)]
        asked = rows.req_head_group.value_counts()
        lv = rows.req_level.value_counts()
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
            "share": round(len(s) / total, 5), "family": FAMILY,
            "roles": sorted([{"role": r, "ads": int(n), "of": int(role_n[r]), "share": round(n / role_n[r], 5)}
                             for r, n in roles.items()], key=lambda x: -x["share"])[:TOP_ROLES],
            "seniority": _shares(m.seniority, sen_n, SENIORITY),
            "asked": [{"how": ASKED.get(k, k), "atoms": int(asked.get(k, 0))} for k in ASKED if asked.get(k, 0)],
            "levels": [{"level": k, "atoms": int(lv.get(k, 0))} for k in LEVELS],
            "atoms": int(len(rows)),
            "countries": sorted(_shares(m.country, country_n), key=lambda x: -x["share"]),
            "with": [{"id": slug[o2], "name": names.get(o2, o2), "ads": int(j), "share": round(j / len(s), 5),
                      "lift": round(lift, 2)} for o2, j, lift in withs],
        })

    base = Path(dest)
    (base / "req").mkdir(parents=True, exist_ok=True)
    for old in (base / "req").glob("*.json"):
        old.unlink()
    index = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "source": {"adverts": total, "what": "Software and data job adverts, European export of August 2026",
                   "rules": {"min_ads": MIN_ADS, "min_companies": MIN_COMPANIES, "min_role_ads": MIN_ROLE_ADS,
                             "min_group_ads": MIN_GROUP_ADS, "min_joint": MIN_JOINT}},
        "families": [{"family": FAMILY, "ads": total}],
        "requirements": [{"id": r["id"], "name": r["name"], "ads": r["ads"], "share": r["share"]} for r in reqs],
    }
    (base / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for r in reqs:
        (base / "req" / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")),
                                                     encoding="utf-8")
    size = sum(f.stat().st_size for f in (base / "req").glob("*.json"))
    print(f"{len(reqs)} requirements -> {base / 'index.json'} ({(base / 'index.json').stat().st_size / 1024:.0f} KB), "
          f"req/*.json ({size / 1024:.0f} KB in all, {size / len(reqs) / 1024:.1f} KB each)")


if __name__ == "__main__":
    main(sys.argv[1])
