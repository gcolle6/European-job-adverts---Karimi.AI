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
pathlib.Path(W4, "data").mkdir(parents=True, exist_ok=True)


def write(name, obj):
    p = pathlib.Path(W4, "data", name)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {name:<28} {p.stat().st_size/1024:>6.1f} KB")


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

# ---------------------------------------------------------------- chart 1 ---
dd = pd.read_csv(W3 + r"\driver_dumbbell.csv", index_col=0)
NICE = {"seniority": "How senior the role is", "company_industry": "Which industry",
        "geo_country": "Which country", "company_type": "What kind of company",
        "company_size": "How big the company is"}
write("chart1_drivers.json", {
    "title": "Country looked like the strongest — until the advert's language was taken out",
    "note": ("Every factor is tested the same way: hold the job fixed, change only that "
             "one thing, and measure how much the list of requirements moves. Further "
             "right means it moves more. The pale dot is the first measurement. The "
             "solid dot is the same measurement after removing the effect of the "
             "language the advert happens to be written in — adverts from one country "
             "tend to share a language, so an untreated country comparison is partly "
             "just a comparison of languages. Only country moves when that is taken "
             "out, which is how you can tell it was the confounded one."),
    "x_label": "how much the list of requirements changes when this factor changes  →",
    "dot_a": "what we first measured",
    "dot_b": "after removing the language effect",
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
    "title": "Most of what you know travels. A few things belong to one industry.",
    "note": ("Every dot is one requirement, placed where employers ask for it most. "
             "1× means it is asked just as often there as anywhere else in the same "
             "job — so it travels with you. 20× means it is asked twenty times more "
             "often there than anywhere else. Hover any dot to see what it is."),
    "x_label": "asked for how much more often here than in the same job elsewhere  →",
    "reference": {"value": 1.0, "label": "asked just as often everywhere"},
    "keys": {"core": "asked everywhere, equally",
             "shell": "belongs to one industry",
             "neither": "somewhere in between"},
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
    "title": "About a quarter is not — and the two jobs fall off the list for different reasons",
    "note": ("ESCO is the European Union's official classification of skills and "
             "occupations: the reference list used to compare jobs across countries. "
             "Each bar is one job family's requirements that match no concept in it, "
             "split by why they do not. Software falls off through novelty — it names "
             "things the list has not caught up with. Sales falls off through vagueness "
             "— it names nothing specific enough to match. 'No reason assigned' is the "
             "largest piece of both, and part of it is our own grouping rather than a "
             "gap in the catalogue."),
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
    "title": "Posting a lot is not the same as posting the same thing",
    "note": ("Each dot is one employer that posted 20 adverts or more. Higher up "
             "means that employer keeps re-posting the same advert: 1.0 would mean "
             "every one of its adverts asks for exactly the same things. The dashed "
             "line is how alike two adverts from DIFFERENT employers usually are — "
             "so anything near it is writing genuinely different adverts."),
    "x_label": "how many adverts this employer posted  →",
    "y_label": "how alike its own adverts are to each other  ↑",
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

write("weighting.json", {
    "label": "One retailer posted the same advert 474 times. Should it count 474 times?",
    "note": ("Pick a rule and the headline number is recomputed under it. The point is "
             "not which rule is correct — it is that the answer stays above 1 whichever "
             "you pick, so the finding does not depend on this choice."),
    # The result is a ratio, and a ratio is unreadable without its pair. Both halves
    # are stated on the page next to the number rather than left to the note.
    "measures": "sales vs software",
    "meaning": ("a sales role's list of requirements shifts this much more than a "
                "software role's when the industry changes"),
    "options": [
        {"key": "advert", "label": "count every advert",
         "explain": ("All 25,800 adverts count once each. That retailer's 474 "
                     "near-identical adverts count 474 times, so one company's template "
                     "can look like an industry-wide pattern."),
         "ratio": 1.240, "adverts": 25800},
        {"key": "dedup", "label": "count repeated adverts once",
         "explain": ("When an employer posts the same advert twice, count it once. Those "
                     "474 adverts become 26 genuinely different ones, and 17% of the "
                     "whole corpus turns out to be a repost."),
         "ratio": 1.168, "adverts": 21356, "default": True, "published": True},
        {"key": "employer", "label": "count every employer once",
         "explain": ("Each company gets one vote however much it posts. Safe against "
                     "templates, but it throws away 975 genuinely different adverts from "
                     "the largest poster in order to neutralise 86 copies from a smaller "
                     "one."),
         "ratio": 1.196, "adverts": 2420},
    ],
})

print("")
print(f"total {time.time()-t0:.0f}s")
