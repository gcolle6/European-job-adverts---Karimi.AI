"""The site's explorer, kept up to date by the runs: counts of adverts per requirement.

    python -m karimi_normalise.explore --base <out.jsonl>     # the export's adverts, from the batch (local)
    python -m karimi_normalise.explore --rebuild              # rebuild from the store (KARIMI_STORE)
    python -m karimi_normalise.explore --contribute <job>     # one checked run, then rebuild

Decided 2026-11-15 with Karimi's agreement: every run that passes its check
adds its adverts to the explorer, so a requirement already listed gains
counts and a new one appears once enough adverts and companies ask for it.
Before, the explorer was built once from the August export and committed to
the site by hand.

Two gates, both written down so a reader can see why a count is or is not there:

* **the run** (`gate`): the check's judge passed its planted pairs and the
  check's error estimate is not red (under 6% of requirements estimated
  wrong). Until 2026-11-16 a splitting signal out of range blocked too; it
  kept batch 2 out at 2.0264 requirements per item against a normal 2.0253,
  an unusual shape and no measured error, and since the colour follows
  errors (the user's call) a shape is at most a yellow that does not block.
  The dictionary-coverage signals (`share_known`, `share_nuovo`, ...) never
  blocked: they measure how new the adverts are, and new adverts are what
  should come in;
* **each requirement** (`keep`): counted (not optional), not from an item
  whose split came out broken, placed in the dictionary's space with a topic,
  not a degree the inspector flags (`errors.degree_flag`), not a generic word.
  An item kept whole because it looked compound IS counted: dropping them
  was tried on 2026-11-15 and took `Written and verbal communication skills`
  (359 adverts), `Linux system administration` and 61 more off the list, one
  requirement each by the count convention. A compound that is not one
  rarely reaches the floors, and too many of them in a run block the run
  (`share_items_llm`).

The same `keep` runs on the export's adverts (`base_rows`), so the August
adverts and the runs' adverts are counted by one rule. An advert counts once:
its key is a hash of the id it was sent with, so the same advert sent twice,
or an advert of the export sent again, is one advert. What is stored is
counts' raw material only: the advert's key and its company as hashes, its
country, seniority and role, and per requirement the normalised fields. No
text of an advert. The floors (`MIN_ADS` adverts from `MIN_COMPANIES`
companies) still decide what is shown.

In the store, outside `jobs/` so the 30-day deletion leaves it:

* `explore/base.jsonl`           the export's adverts, uploaded with the dictionary;
* `explore/runs/<job>.jsonl`     one checked run's adverts, if it passed;
* `explore/decisions/<job>.json` every run's decision, passed or not, and why;
* `explore/index.json`, `explore/requirements.json`, `explore/built.json`,
  `explore/categories.json`      what the API serves, and the category cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import pandas as pd

from . import categories, errors
from .store import jf, now, open_store, read_json, write_json

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
         "language": "As a language", "education": "As a degree", "": "Named alone"}
# The degree an education requirement asks for (`normalise_req.DEGREES`), lowest first.
# `school` (the school-leaving diploma) since rules 0.4.7
DEGREES = ["school", "student", "bachelor", "master", "phd", "mba", "degree"]
DEGREE_NAME = {"school": "High school diploma", "student": "Student", "bachelor": "Bachelor", "master": "Master", "phd": "PhD", "mba": "MBA",
               "degree": "Any degree"}
# The export writes countries in their own language, the runs sometimes as ISO codes.
COUNTRY_EN = {
    "Deutschland": "Germany", "Nederland": "Netherlands", "España": "Spain", "België": "Belgium",
    "Italia": "Italy", "Sverige": "Sweden", "Polska": "Poland", "Schweiz": "Switzerland", "România": "Romania",
    "Österreich": "Austria", "Česko": "Czechia", "Danmark": "Denmark", "Ελλάδα": "Greece",
    "Magyarország": "Hungary", "България": "Bulgaria", "Slovensko": "Slovakia", "Suomi": "Finland",
    "Éire": "Ireland", "Norge": "Norway", "Brasil": "Brazil",
    "DE": "Germany", "NL": "Netherlands", "ES": "Spain", "BE": "Belgium", "IT": "Italy", "SE": "Sweden",
    "PL": "Poland", "CH": "Switzerland", "RO": "Romania", "AT": "Austria", "CZ": "Czechia", "DK": "Denmark",
    "GR": "Greece", "HU": "Hungary", "BG": "Bulgaria", "SK": "Slovakia", "FI": "Finland", "IE": "Ireland",
    "NO": "Norway", "FR": "France", "GB": "United Kingdom", "UK": "United Kingdom", "PT": "Portugal",
    "LU": "Luxembourg", "LT": "Lithuania", "US": "United States", "USA": "United States", "IN": "India",
    "CA": "Canada", "BR": "Brazil", "JP": "Japan", "KE": "Kenya", "NG": "Nigeria", "MX": "Mexico",
    "CN": "China", "SG": "Singapore", "AU": "Australia",
}

# Objects that name no requirement on their own: fragments of the frame.
GENERIC = {
    # `comparable qualification` and `methodologies` once the list around them is gone (2026-11-10)
    "qualification", "methodologies",
    # one word left from a broken split, read on the list 2026-11-11
    "ample", "have", "higher", "highly", "large", "problem", "position", "well", "field", "function",
    "demonstrate", "role", "user", "setting up", "synthesis", "listening",
    "technical", "equivalent", "work", "it", "development", "business", "experience", "data", "engineering",
    "tools", "team", "industry", "standards", "management", "services", "processes", "organization",
    "structured", "commercial", "production", "frameworks", "relational", "similar application",
    "similar role", "thinking level", "data-management role", "design", "integration", "programming",
    "architecture", "infrastructure", "platform", "systems", "solutions", "technology", "technologies",
    "skills", "knowledge", "environment", "environments", "methods", "concepts", "principles",
}

# Signals of the run report that say the SPLIT went wrong: these block a run.
# The others measure how much of the run the dictionary already knew.
SPLIT_SIGNALS = ("requirements_per_item", "share_items_llm", "share_items_damaged", "share_one_word")
DROPPED = ("not_counted", "damaged", "no_topic", "degree_suspect", "generic")

BASE, RUNS, DECISIONS = "explore/base.jsonl", "explore/runs/", "explore/decisions/"
INDEX, REQUIREMENTS, BUILT, CATEGORIES = ("explore/index.json", "explore/requirements.json",
                                         "explore/built.json", "explore/categories.json")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def advert_key(posting_id, title: str = "", items: list[str] | None = None) -> str:
    """One advert, one key: its id when it has one, else its title and text."""
    if posting_id not in (None, ""):
        return _hash(f"id:{posting_id}")
    return _hash("text:" + (title or "") + "\n" + "\n".join(items or []))


def obj_of(topic: str) -> str:
    """The explorer's unit, from `req_topic`: one requirement whatever the
    apostrophe or the spacing (`master's` and `master’s` were two before 2026-11-06)."""
    t = (topic or "").removeprefix("language: ").replace("’", "'")
    return " ".join(t.split()).strip().lower()


def keep(r: dict) -> str | None:
    """None if the requirement counts; else why not, one of DROPPED.

    ``r`` carries the requirement's fields under the API's names (`route`,
    `counted`, `space`, `core`, `atom`, `req_topic`)."""
    if r.get("counted") is False or str(r.get("counted")).lower() == "false":
        return "not_counted"
    if r.get("route") == "damaged":
        return "damaged"
    if not r.get("req_topic") or r.get("match") == "empty":
        return "no_topic"
    if errors.degree_flag(r):
        return "degree_suspect"
    if obj_of(r["req_topic"]) in GENERIC or not obj_of(r["req_topic"]):
        return "generic"
    return None


def _req(r: dict) -> list:
    return [obj_of(r["req_topic"]), r.get("req_group") or "", r.get("space") or "", r.get("head_group") or "",
            r.get("core") or "", r.get("level") or "", r.get("degree") or ""]


def gate(check_out: dict | None) -> tuple[bool, str]:
    """Whether a checked run may add to the explorer, and why in one line."""
    if not check_out:
        return False, "not checked yet"
    if not (check_out.get("canaries") or {}).get("trusted"):
        return False, "no trusted judge on this run: nothing verified its decisions"
    for f in check_out.get("findings") or []:
        if f.get("level") == "health" or (f.get("level") == "errors" and f.get("light") == "red"):
            return False, f"{f.get('code')}: {f.get('what')}"
    est = check_out.get("error_estimate")
    if est is None:
        # a run checked before 2026-11-16 has no estimate: the rule it was checked under
        for f in check_out.get("findings") or []:
            code = (f.get("code") or "").split(":", 1)[-1]
            if f.get("level") == "judge" or (f.get("level") == "signals" and code in SPLIT_SIGNALS):
                return False, f"{f.get('code')}: {f.get('what')}"
        return True, "judge trusted and within its reference; splitting signals normal (checked before 2026-11-16)"
    return True, f"judge trusted; about {est['share']:.1%} of requirements estimated wrong, under the red line"


def run_rows(inputs: list[dict], results: list[dict], job: str) -> tuple[list[dict], Counter]:
    """A run's adverts as the explorer stores them, and what each rule dropped."""
    rows, dropped = [], Counter()
    for p, res in zip(inputs, results):
        reqs = []
        for r in res.get("requirements") or []:
            why = keep(r)
            if why:
                dropped[why] += 1
            else:
                reqs.append(_req(r))
        if not reqs:
            continue
        t = res.get("title") or {}
        company = p.get("company") or p.get("company_id") or p.get("company_name") or ""
        country = str(p.get("country") or p.get("geo_country") or "").strip()
        rows.append({"k": advert_key(p.get("id"), p.get("title") or "", p.get("must_have")),
                     "c": _hash(f"company:{company}") if company else "",
                     "country": COUNTRY_EN.get(country, country), "sen": str(p.get("seniority") or ""),
                     "role": t.get("title_name") or t.get("title_role") or "", "src": job,
                     "rv": t.get("rules_version", ""), "r": reqs})
    return rows, dropped


def base_rows(batch: str | Path, export: str | Path) -> tuple[list[dict], Counter]:
    """The export's adverts, from the batch the dictionary was frozen from, by the same `keep`."""
    from .versions import RULES_VERSION

    batch = Path(batch)
    a = pd.read_parquet(batch / "must_have_atoms.parquet",
                        columns=["posting_id", "atom", "route", "counted", "req_topic", "req_group", "req_space",
                                 "req_head_group", "req_core", "req_level", "req_degree"])
    a = a.rename(columns={"req_space": "space", "req_head_group": "head_group", "req_core": "core",
                          "req_level": "level", "req_degree": "degree"}).fillna("")
    t = pd.read_parquet(batch / "titles.parquet", columns=["posting_id", "title_name"]).drop_duplicates("posting_id")
    roles = dict(zip(t.posting_id, t.title_name.fillna("")))
    meta = {r["_id"]: r for r in json.loads(Path(export).read_text(encoding="utf-8"))}
    by, dropped = {}, Counter()
    for r in a.to_dict("records"):
        why = keep(r)
        if why:
            dropped[why] += 1
            continue
        by.setdefault(r["posting_id"], []).append(_req(r))
    rows = []
    for pid, reqs in by.items():
        m = meta.get(pid, {})
        country = m.get("geo_country") or ""
        rows.append({"k": advert_key(pid), "c": _hash(f"company:{m['company_id']}") if m.get("company_id") else "",
                     "country": COUNTRY_EN.get(country, country), "sen": m.get("seniority") or "",
                     "role": roles.get(pid, ""), "src": "export", "rv": RULES_VERSION, "r": reqs})
    return rows, dropped


def _shares(col: pd.Series, base: pd.Series, keep_groups: list[str] | None = None) -> list[dict]:
    """Share of each group's adverts that ask for it; groups with too few adverts left out."""
    n = col.value_counts()
    groups = keep_groups if keep_groups is not None else [g for g in base.index if base[g] >= MIN_GROUP_ADS]
    return [{"group": g, "ads": int(n.get(g, 0)), "of": int(base[g]), "share": round(n.get(g, 0) / base[g], 5)}
            for g in groups if g in base.index and base[g] >= MIN_GROUP_ADS]


def slugs(objs) -> dict[str, str]:
    """A file name per requirement, unique. Symbols that name languages survive
    (`c++`, `c#`): reduced to letters they all became `c`, one file for three."""
    import re

    out, seen = {}, {}
    for o in objs:
        s = o.lower().replace("c++", "c-plus-plus").replace("c#", "c-sharp").replace(".net", "dotnet")
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "r"
        n = seen.get(s, 0)
        seen[s] = n + 1
        out[o] = s if n == 0 else f"{s}-{n + 1}"
    return out


def unique(rows: list[dict]) -> list[dict]:
    """Each advert once: the first time its key was seen (the export, then runs in order)."""
    seen, out = set(), []
    for r in rows:
        if r["k"] not in seen:
            seen.add(r["k"])
            out.append(r)
    return out


def aggregate(rows: list[dict], categorise, source: dict) -> tuple[dict, list[dict]]:
    """The explorer's index and one record per requirement shown, from advert rows.

    ``categorise(names, spaces) -> categories``; ``source`` goes into the index
    as given, beside the floors. The five charts per requirement:

    1. roles      — the roles that ask for it most, as a share of that role's adverts;
    2. seniority  — the share at each seniority level, against all its adverts;
    3. asked      — how it is asked (experience, competence, ...) and at what level;
    4. countries  — the share in each country, against all its adverts;
    5. with       — the requirements that come with it: how much more often than
                    anywhere (lift) and how many of its adverts ask for them too.
    """
    from karimi import normalise_req

    rows = unique(rows)
    ads = pd.DataFrame([{"posting_id": r["k"], "company": r["c"] or None, "country": r["country"],
                         "seniority": r["sen"], "title_name": r["role"]} for r in rows])
    a = pd.DataFrame([{"posting_id": r["k"], "obj": q[0], "req_group": q[1], "req_space": q[2],
                       "req_head_group": q[3], "req_core": q[4], "req_level": q[5], "req_degree": q[6]}
                      for r in rows for q in r["r"]])
    total = len(ads)
    role_n = ads.title_name.value_counts()
    country_n = ads.country[ads.country != ""].value_counts()
    sen_n = ads.seniority.value_counts()

    per = a.merge(ads, on="posting_id")
    by_obj = per.groupby("obj")
    stats = pd.DataFrame({"ads": by_obj.posting_id.nunique(), "companies": by_obj.company.nunique()})
    kept = stats[(stats.ads >= MIN_ADS) & (stats.companies >= MIN_COMPANIES)].sort_values("ads", ascending=False)

    pa = per[per.obj.isin(kept.index)]
    ad_sets = pa.groupby("obj").posting_id.agg(set).to_dict()
    # The name is the topic's largest GROUP, worded as that group is most often
    # written. Counting wordings across the whole topic named `data analysis`
    # `Data` (2026-11-10): its spellings split the count, one bare word did not.
    big = (pa.groupby(["obj", "req_group"]).size().reset_index(name="n").sort_values("n", ascending=False)
           .drop_duplicates("obj"))
    pg = pa.merge(big[["obj", "req_group"]], on=["obj", "req_group"])
    top = (pg.groupby(["obj", "req_space", "req_core"]).size().reset_index(name="n")
           .sort_values(["n", "req_core"], ascending=[False, True]).drop_duplicates("obj"))
    names = {o: normalise_req.display(sp, c) for o, sp, c in zip(top.obj, top.req_space, top.req_core)}
    space = dict(zip(top.obj, top.req_space))
    category = dict(zip(kept.index, categorise([names.get(o, o) for o in kept.index],
                                               [space.get(o, "") for o in kept.index])))
    slug = slugs(kept.index)
    meta = ads.set_index("posting_id")
    by_rows = {o: g for o, g in pa.groupby("obj")}
    # Each degree is its own requirement since rules 0.4.0 (`Master in Physics`),
    # so chart 3 shows, for a degree, how often its FIELD is asked at each
    # degree level, across all of them: the user's view of 2026-11-10, kept.
    edu = per[per.req_space == "education"]
    field = edu.req_core.str.split(" in ", n=1).str[1].fillna("").map(normalise_req.canon)
    by_field = edu.assign(field=field).groupby("field").req_degree.value_counts()

    reqs = []
    for o in kept.index:
        s = ad_sets[o]
        m = meta.loc[list(s)]
        rows_o = by_rows[o]
        roles = m.title_name.value_counts()
        roles = roles[(roles.index != "") & roles.index.map(lambda r: role_n.get(r, 0) >= MIN_ROLE_ADS)]
        asked = rows_o.req_head_group.value_counts()
        lv = rows_o.req_level.value_counts()
        core0 = rows_o.req_core.iloc[0]
        f = (normalise_req.canon(core0.split(" in ", 1)[1])
             if rows_o.req_space.iloc[0] == "education" and " in " in core0 else None)
        dg = by_field.loc[f] if f and f in by_field.index.get_level_values(0) else rows_o.req_degree.value_counts()
        withs = []
        for o2 in kept.index:
            if o2 == o:
                continue
            j = len(s & ad_sets[o2])
            if j >= MIN_JOINT:
                withs.append((o2, j, j * total / (len(s) * len(ad_sets[o2]))))
        withs = sorted(withs, key=lambda x: (-x[2], -x[1]))[:TOP_WITH]
        reqs.append({
            "id": slug[o], "name": names.get(o, o), "category": category[o],
            "ads": int(len(s)), "companies": int(kept.companies[o]),
            "share": round(len(s) / total, 5), "family": FAMILY,
            "roles": sorted([{"role": r, "ads": int(n), "of": int(role_n[r]), "share": round(n / role_n[r], 5)}
                             for r, n in roles.items()], key=lambda x: -x["share"])[:TOP_ROLES],
            "seniority": _shares(m.seniority, sen_n, SENIORITY),
            "asked": [{"how": ASKED.get(k, k), "atoms": int(asked.get(k, 0))} for k in ASKED if asked.get(k, 0)],
            "levels": [{"level": k, "atoms": int(lv.get(k, 0))} for k in LEVELS],
            "degrees": [{"degree": DEGREE_NAME[k], "atoms": int(dg.get(k, 0))} for k in DEGREES if dg.get(k, 0)],
            "atoms": int(len(rows_o)),
            "countries": sorted(_shares(m.country, country_n), key=lambda x: -x["share"]),
            "with": [{"id": slug[o2], "name": names.get(o2, o2), "ads": int(j), "share": round(j / len(s), 5),
                      "lift": round(lift, 2)} for o2, j, lift in withs],
        })

    index = {
        "generated": now(),
        "source": {"adverts": total, **source,
                   "rules": {"min_ads": MIN_ADS, "min_companies": MIN_COMPANIES, "min_role_ads": MIN_ROLE_ADS,
                             "min_group_ads": MIN_GROUP_ADS, "min_joint": MIN_JOINT}},
        "families": [{"family": FAMILY, "ads": total}],
        # the explorer's browsing window groups by these, in this order (`categories.py`)
        "categories": [c for c in categories.ORDER if any(r["category"] == c for r in reqs)],
        "requirements": [{"id": r["id"], "name": r["name"], "category": r["category"], "ads": r["ads"],
                          "share": r["share"]} for r in reqs],
    }
    return index, reqs


def what(n_export: int, n_runs: int, jobs: int) -> str:
    """The index's one-line description of where the adverts come from."""
    w = "Software and data job adverts, European export of August 2026"
    return w + (f", and {n_runs:,} adverts from {jobs} API run{'s' if jobs != 1 else ''} that passed "
                f"their check" if n_runs else "")

# ---------------------------------------------------------------- the store


def _jsonl(store, name: str) -> list[dict]:
    text = store.read_text(name) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def contribute(store, job: str, check_out: dict | None = None) -> dict:
    """Decide whether a checked run adds to the explorer; store its adverts if so.

    Always writes the decision (`explore/decisions/<job>.json`), passed or not,
    so the site can say why a run is or is not in the counts."""
    check_out = check_out if check_out is not None else read_json(store, jf(job, "check.json"))
    ok, why = gate(check_out)
    out = {"job": job, "decided": now(), "contributed": ok, "why": why}
    if ok:
        inputs, results = _jsonl(store, jf(job, "input.jsonl")), _jsonl(store, jf(job, "results.jsonl"))
        rows, dropped = run_rows(inputs, results, job)
        store.write_text(f"{RUNS}{job}.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        kept = sum(len(r["r"]) for r in rows)
        out.update(postings=len(rows), of_postings=len(results), requirements=kept,
                   dropped={k: dropped.get(k, 0) for k in DROPPED},
                   rules_version=(rows[0]["rv"] if rows else ""))
    write_json(store, f"{DECISIONS}{job}.json", out)
    return out


def rebuild(store, judge_url: str | None = None) -> dict:
    """The explorer from the export's adverts and every run that passed; written to the store."""
    base = _jsonl(store, BASE)
    if not base:
        raise FileNotFoundError(f"{BASE} is missing: upload it with the dictionary (`--base`)")
    decisions = [read_json(store, n) for n in store.list(DECISIONS)]
    decisions = sorted([d for d in decisions if d], key=lambda d: d.get("decided", ""))
    run_rows_all, used = [], []
    for d in decisions:
        if d.get("contributed"):
            rows = _jsonl(store, f"{RUNS}{d['job']}.jsonl")
            run_rows_all += rows
            used.append(d["job"])
    rows = unique(base + run_rows_all)
    n_runs = sum(1 for r in rows if r["src"] in used)
    n_export = len(rows) - n_runs
    asked = read_json(store, CATEGORIES) or {}
    n_asked = len(asked)
    index, reqs = aggregate(rows, lambda names, spaces: categories.categorise(names, spaces, asked,
                                                                              judge_url=judge_url,
                                                                              prototypes=False),
                            {"what": what(n_export, n_runs, len(used)),
                             "from": {"export": n_export, "runs": n_runs, "run_jobs": len(used)}})
    if len(asked) > n_asked:
        write_json(store, CATEGORIES, asked)
    store.write_text(REQUIREMENTS, json.dumps({r["id"]: r for r in reqs}, ensure_ascii=False,
                                              separators=(",", ":")))
    store.write_text(INDEX, json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    previous = {r["id"] for r in (read_json(store, BUILT) or {}).get("shown", [])}
    built = {"built": index["generated"], "adverts": index["source"]["adverts"], "from": index["source"]["from"],
             "requirements": len(reqs), "new_requirements": sorted(r["name"] for r in reqs if previous and
                                                                   r["id"] not in previous),
             "shown": [{"id": r["id"], "ads": r["ads"]} for r in reqs],
             "decisions": [{k: d.get(k) for k in ("job", "decided", "contributed", "why", "postings", "of_postings",
                                                  "requirements", "dropped", "rules_version")} for d in decisions]}
    write_json(store, BUILT, built)
    return {k: built[k] for k in ("built", "adverts", "from", "requirements", "new_requirements")}


def pending(store) -> list[str]:
    """Checked jobs with no decision yet: runs checked before the explorer existed, or whose step failed."""
    done = {n.removeprefix(DECISIONS).removesuffix(".json") for n in store.list(DECISIONS)}
    return [j for j in store.jobs() if j not in done and store.exists(jf(j, "check.json"))]


def summary(store) -> dict | None:
    """What the site's metrics page shows of this step: the last build and the last decisions."""
    b = read_json(store, BUILT)
    if not b:
        return None
    return {"agent": "publisher", "built": b["built"], "adverts": b["adverts"], "from": b["from"],
            "requirements": b["requirements"], "new_requirements": b.get("new_requirements", [])[:30],
            "decisions": list(reversed(b["decisions"]))[:20]}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", help="write the export's adverts to this file (needs the batch)")
    ap.add_argument("--batch", default=str(Path(__file__).resolve().parent.parent / "New project" / "output"))
    ap.add_argument("--export", default=str(Path(__file__).resolve().parent.parent / "wetransfer_karimi-jobs_2026-08-25_1346"
                                            / "software_data_europe.json"))
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--contribute", metavar="JOB")
    a = ap.parse_args(argv)
    if a.base:
        rows, dropped = base_rows(a.batch, a.export)
        Path(a.base).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(json.dumps({"adverts": len(rows), "requirements": sum(len(r["r"]) for r in rows),
                          "dropped": dict(dropped)}))
        return
    store = open_store()
    if a.contribute:
        print(json.dumps(contribute(store, a.contribute), ensure_ascii=False))
    if a.rebuild or a.contribute:
        print(json.dumps(rebuild(store, os.environ.get("KARIMI_JUDGE_URL")), ensure_ascii=False))


if __name__ == "__main__":
    main()
