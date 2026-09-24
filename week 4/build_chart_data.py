"""The four chart datasets, from the corrected and merged structure.

Everything here reads the *final* assignment — intruders moved to noise, the 20
merge families applied — because anything built on the raw 617 groups understates
per-technology demand by 55-62% and does so unevenly, which makes comparisons
between groups invalid rather than merely low.

Written as small JSON so a page can load them directly. Each file carries the
numbers a chart draws **and** the qualifier it must draw beside them: a lift with
its employer count, an index with its interval, a share with its denominator. A
dataset that ships the point estimate alone invites a panel that publishes the
point estimate alone.
"""
import json
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl, config, data

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
W4 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 4"
pd.set_option("display.width", 250)
t0 = time.time()

import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
pathlib.Path(W4, "data").mkdir(parents=True, exist_ok=True)


import pagecopy                              # pagecopy.md — every word the page shows

C = pagecopy.load()
CHART = {"chart1_drivers": "chart1", "chart2_core_shell": "chart2",
         "chart3_residual": "chart3", "chart4_employers": "chart4"}


# Figures typed into pagecopy.md by hand go stale when the data moves. The ones that
# can be re-derived are re-derived, and a mismatch is reported rather than
# published: a drifted number usually means the sentence beside it has drifted
# too, so the warning names the bullet instead of quietly correcting it.
def _c1(d):
    r = {x["factor"]: x for x in d["rows"]}["Which country"]
    return f"{r['raw']:.3f} → {r['controlled']:.3f}"


def _c2(kind):
    return lambda d: (f"{sum(1 for g in d['groups'] if g['kind'] == kind)} "
                      f"of {len(d['groups'])}")


CHECKS = {
    "chart1": {0: _c1},
    "chart2": {0: _c2("core"), 1: _c2("shell")},
    "chart3": {0: lambda d: " and ".join(f"{f['residual_share']*100:.1f}%"
                                         for f in d["families"])},
    "chart4": {0: lambda d: f"{len(d['employers'])} employers"},
}


def write(name, obj):
    """Attach this chart's pagecopy from pagecopy.md, check its figures, and write it."""
    key = CHART.get(name.replace(".json", ""))
    pts = []
    if key:
        for slot in ("title", "note", "x_label", "y_label", "dot_a", "dot_b"):
            if C.get(f"{key}.{slot}"):
                obj = dict(obj, **{slot: C[f"{key}.{slot}"]})
        pts = pagecopy.points(C.get(f"{key}.points", ""))
        for i, fn in CHECKS.get(key, {}).items():
            want = fn(obj)
            if i < len(pts) and pts[i]["stat"] != want:
                print(f"  !! {key} bullet {i}: pagecopy.md says {pts[i]['stat']!r}, "
                      f"the data says {want!r} — reread the sentence beside it")
                pts[i]["stat"] = want
        if pts:
            obj = dict(obj, points=pts)
    p = pathlib.Path(W4, "data", name)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {name:<28} {p.stat().st_size/1024:>6.1f} KB"
          + (f"  +{len(pts)} bullets" if pts else ""))


reqs = pd.read_parquet(W1 + r"\requirements.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
asg = pd.read_parquet(W3 + r"\phrase_clusters_corrected.parquet")
alias = pd.read_csv(W3 + r"\alias_table_final.csv")
amap = dict(zip(alias["cluster"], alias["merged_into"]))
asg["cluster"] = asg["cluster"].map(lambda c: amap.get(c, c))

lab = dict(zip(named["cluster"], named["label"]))
drop = {amap.get(c, c) for c in
        set(named.loc[named["boilerplate"] == True, "cluster"]) |
        set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])}
base = data.build_analysis_base().df
post = base.drop_duplicates("vacancy_id")

print("building chart datasets from the corrected structure")
print(f"  groups after merge: {asg.loc[asg['cluster'] != -1, 'cluster'].nunique()}")
print("")

# ---------------------------------------------------------------- corpus ---
# The two families described by five factors, for the introductory chart. Counts
# are the analysis base — the same 25,800 the masthead states and every chart
# below uses — so a reader adding up the bubbles arrives at the headline figure.
CORPUS_FACTORS = [
    ("company_industry", "Industry"),
    ("company_size", "Company size"),
    ("company_type", "Kind of company"),
    ("seniority", "Seniority"),
    ("work_type", "Where the work happens"),
]
UNSTATED = "not stated"

corpus = {"total": int(post["vacancy_id"].nunique()), "groups": []}
for col, title in CORPUS_FACTORS:
    lv = post[col].fillna("").astype(str).str.strip().replace("", UNSTATED)
    ct = pd.crosstab(lv, post["macro_function"])
    co = post.assign(_l=lv).groupby(["_l", "macro_function"])["company"].nunique().unstack()
    for fn in ("SOFTWARE_DATA", "SALES_BD"):
        if fn not in ct.columns:
            ct[fn] = 0
        if fn not in co.columns:
            co[fn] = 0
    ct = ct.assign(tot=ct["SOFTWARE_DATA"] + ct["SALES_BD"]).sort_values("tot", ascending=False)
    # an unstated level is information about the data, so it is kept and named —
    # but it belongs at the bottom, not interleaved with real levels
    order = [i for i in ct.index if i != UNSTATED] + \
            ([UNSTATED] if UNSTATED in ct.index else [])
    corpus["groups"].append({
        "factor": title,
        "levels": [{
            "level": str(i),
            "software": int(ct.loc[i, "SOFTWARE_DATA"]),
            "sales": int(ct.loc[i, "SALES_BD"]),
            "sw_companies": int(co.loc[i, "SOFTWARE_DATA"]) if i in co.index else 0,
            "sa_companies": int(co.loc[i, "SALES_BD"]) if i in co.index else 0,
            "unstated": bool(i == UNSTATED),
        } for i in order],
    })
# Two further metrics for the industry block, as counts of adverts rather than
# shares — so they share the adverts radius scale and read as subsets of it.
# Chosen because each separates the families sharply and varies between
# industries; Enterprise share does neither (67% against 66%).
EXTRA = [("senior", post["seniority"].eq("Senior")),
         ("flex", post["work_type"].isin(["hybrid", "remote"]))]
ind = [g for g in corpus["groups"] if g["factor"] == "Industry"][0]
for key, mask in EXTRA:
    ct = pd.crosstab(post.loc[mask, "company_industry"],
                     post.loc[mask, "macro_function"])
    for lv in ind["levels"]:
        row = ct.loc[lv["level"]] if lv["level"] in ct.index else None
        lv[f"{key}_sw"] = int(row.get("SOFTWARE_DATA", 0)) if row is not None else 0
        lv[f"{key}_sa"] = int(row.get("SALES_BD", 0)) if row is not None else 0

write("corpus.json", corpus)

# ---------------------------------------------------------------- chart 1 ---
dd = pd.read_csv(W3 + r"\driver_dumbbell.csv", index_col=0)
NICE = {"seniority": "How senior the role is", "company_industry": "Which industry",
        "geo_country": "Which country", "company_type": "What kind of company",
        "company_size": "How big the company is"}
write("chart1_drivers.json", {
    "rows": [{
        "factor": NICE.get(i, i),
        "raw": round(float(r["raw"]), 4),
        "controlled": round(float(r["controlled"]), 4),
        "shift_pct": round(float(r["shift_pct"]), 1),
        "confounded": bool(abs(r["shift_pct"]) > 5),
    } for i, r in dd.sort_values("controlled", ascending=False).iterrows()],
})

# ---------------------------------------------------------------- chart 2 ---
cs = cl.core_shell(asg, reqs, boilerplate=drop)
j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
# reqs already carries a company column; merging the base in would shadow it
employers = (j[j["cluster"] != -1]
             .groupby(["cluster", "macro_function", "company_industry"])["company"]
             .nunique().rename("employers").reset_index())
cs = cs.merge(employers, on=["cluster", "macro_function", "company_industry"], how="left")

peak = (cs[cs["reliable"]].sort_values("lift", ascending=False)
        .drop_duplicates("cluster"))
core_ids = set(cs.loc[cs["verdict"] == "core", "cluster"])
rows = []
for r in peak.itertuples():
    if r.cluster in drop:
        continue
    rows.append({
        "group": str(lab.get(int(r.cluster), "?")),
        "lift": round(float(r.lift), 2),
        "share": round(float(r.share), 4),
        "cell": f"{'software' if r.macro_function == 'SOFTWARE_DATA' else 'sales'} in {r.company_industry}",
        "employers": int(r.employers) if pd.notna(r.employers) else None,
        "kind": "core" if int(r.cluster) in core_ids else (
            "shell" if r.verdict == "shell" else "neither"),
    })
rows.sort(key=lambda x: -x["lift"])
write("chart2_core_shell.json", {
    "reference": {"value": 1.0, "label": "same rate in every industry"},
    # the verdict's own thresholds, so the chart draws the rules it is showing
    # rather than a retyped copy of them
    "thresholds": {"shell_lift": cl.SHELL_MIN_LIFT, "shell_share": cl.SHELL_MIN_SHARE,
                   "core_share": cl.CORE_MIN_SHARE, "core_dev": cl.CORE_MAX_LIFT_DEVIATION},
    "keys": {"core": "similar rate everywhere",
             "shell": "mostly one industry",
             "neither": "neither"},
    "groups": rows,
})

# ---------------------------------------------------------------- chart 3 ---
res = pd.read_csv(W3 + r"\residual_by_reason.csv")
hyb = pd.read_parquet(OUT + r"\req_type_hybrid.parquet")
dec = pd.read_csv(OUT + r"\esco_decisions.csv")
dec["anchored"] = dec["anchored"].astype(str).str.strip().str.lower().eq("true")
jj = j.merge(dec[["cluster", "anchored"]], on="cluster", how="left")
jj["anchored"] = jj["anchored"].fillna(False).astype(bool)
rmap = dict(zip(res["cluster"], res["reason"]))
rr = jj[(jj["cluster"] != -1) & (~jj["anchored"])].copy()
rr["reason"] = rr["cluster"].map(rmap).fillna("other")
tot = jj[jj["cluster"] != -1].groupby("macro_function").size()
tab = rr.groupby(["macro_function", "reason"]).size().unstack(fill_value=0)
LABEL = {"novelty": "names something not yet catalogued",
         "vagueness": "names nothing in particular",
         "structural": "ESCO does not model it at all",
         "other": "no reason assigned"}
write("chart3_residual.json", {
    "families": [{
        "family": "software" if fn == "SOFTWARE_DATA" else "sales",
        "residual_share": round(float(rr[rr["macro_function"] == fn].shape[0] / tot[fn]), 4),
        "segments": [{"reason": LABEL[k],
                      "key": k,
                      "share_of_family": round(float(tab.loc[fn, k] / tot[fn]), 4)}
                     for k in ("novelty", "vagueness", "structural", "other")
                     if k in tab.columns],
    } for fn in ("SOFTWARE_DATA", "SALES_BD")],
})

# ---------------------------------------------------------------- chart 4 ---
tpl = pd.read_csv(W3 + r"\employer_templates.csv")
write("chart4_employers.json", {
    "control_line": round(float(tpl["control"].median()), 3),
    "employers": [{
        "name": str(r.company),
        "adverts": int(r.adverts),
        "self_similarity": round(float(r.own_similarity), 3),
        "highlight": str(r.company) in {"Inetum", "Worten"},
    } for r in tpl.itertuples()],
})

# ---------------------------------------------------------------- tiles -----
write("tiles.json", {"tiles": [
    {"value": "1.17", "range": "1.13 – 1.43",
     "label": "how much more sales requirement profiles move between industries than software's"},
    {"value": "7", "range": "five of them not technical",
     "label": "requirement groups asked for everywhere, at the same rate"},
    {"value": "26.9%", "range": "a third of it uncharacterised",
     "label": "of demand has no concept in the European skills catalogue"},
]})

print("")
print(f"total {time.time()-t0:.0f}s")
