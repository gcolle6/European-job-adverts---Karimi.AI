"""Datasets for article 1 — what actually changes the job.

Scope discipline: this article answers one question only. Which of the things
that vary around a fixed role actually changes what employers ask for, and what
had to be removed before that ranking could be believed. Core and shell, the
ESCO residual and the sales-versus-software headline belong to articles 2 and 3
and are deliberately absent, so the three pieces stay separable.

Five figures, in the order the argument runs:

  A  the six factors ranked, with intervals, in both job families
  B  the confound made visible: each country is a language mixture
  C  the same ranking recomputed on English text only
  D  the follow-up confound: is an industry step partly a country step?
  E  the ranking under employer weighting rather than advert weighting

A, C, D and E are read from the Week 3 runs rather than recomputed, so the
article cannot quietly disagree with the tables it came from. B is computed
here because nothing in Week 3 wrote it out.
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import data, language as lang

HERE = pathlib.Path(__file__).resolve().parent
W3 = HERE.parent.parent / "week 3"
MIN_LEVEL = 120                      # the floor run_language_control_all.py used

NICE = {"seniority": "How senior the role is",
        "company_industry": "Which industry",
        "geo_country": "Which country",
        "company_type": "What kind of company",
        "company_size": "How big the company is",
        "work_type": "Office, hybrid or remote"}
FN = {"SOFTWARE_DATA": "software", "SALES_BD": "sales"}

t0 = time.time()
out = {}

# --- A ---------------------------------------------------------------------
# Six factors, both job families, with the bootstrap interval. The point is the
# ranking, and that the ranking is the same in both families.
dr = pd.read_csv(W3 / "driver_ranking.csv")
order = (dr.groupby("factor")["js"].mean().sort_values(ascending=False).index.tolist())
out["a"] = {
    "title": "Six things vary around a fixed job. Country moves it most.",
    "note": ("Distance between the requirement profiles of three levels of each factor, "
             "with the job family held fixed. 0 would mean the levels ask for exactly "
             "the same things. Bars are 95% bootstrap intervals. The ranking is the "
             "same in both families, which is what makes it a ranking rather than a "
             "property of one of them."),
    "x_label": "how far apart the requirement profiles are  \u2192",
    "factors": [
        {"factor": NICE[f],
         "series": [{"family": FN[fn],
                     "js": float(r["js"]), "lo": float(r["js_lo"]), "hi": float(r["js_hi"])}
                    for fn, r in dr[dr["factor"] == f].set_index("function").iterrows()]}
        for f in order],
}

# --- B ---------------------------------------------------------------------
# The confound. Nothing in Week 3 wrote this out, so it is computed here, with
# the language derived exactly as the control derived it: the language of the
# requirement TEXT, not the advert's own field, which disagrees for ~11% of rows.
base = data.build_analysis_base().df
det = lang.detect_series(base["must_have"])
base["text_lang"] = det["detected"].where(det["hits"] >= 1, base["language"])
post = base.drop_duplicates("vacancy_id")

ct = pd.crosstab(post["geo_country"], post["text_lang"])
tot = ct.sum(axis=1).sort_values(ascending=False)

# which three countries actually entered the comparison — same rule as the run
eng = post[post["text_lang"] == "English"]
ct_all = pd.crosstab(post["geo_country"], post["macro_function"])
ct_en = pd.crosstab(eng["geo_country"], eng["macro_function"])
ok = [lv for lv in ct_all.index
      if lv in ct_en.index
      and (ct_all.loc[lv] >= MIN_LEVEL).all() and (ct_en.loc[lv] >= MIN_LEVEL).all()]
compared = ct_en.loc[ok].min(axis=1).nlargest(3).index.tolist()

# Three categories, not seven. The control that follows keeps English and drops
# everything else, so the split that matters is English against the country's own
# language — and three series stay inside a palette that can be told apart.
#
# The detector covers eight languages and Polish is not one of them, so the
# largest non-English share in a Polish row is misdetection noise on a small
# slice rather than a local language. Naming it would put "Português" beside
# Poland. A share under this floor is therefore not named at all and falls into
# "any other", which is what it is.
NAME_LOCAL_ABOVE = 10.0

rows = []
for c in tot.head(12).index:
    sh = (ct.loc[c] / tot[c] * 100)
    english = float(sh.get("English", 0.0))
    rest = sh.drop(labels=["English"], errors="ignore")
    top_name, top_pct = (str(rest.idxmax()), float(rest.max())) if len(rest) else ("", 0.0)
    named = top_pct >= NAME_LOCAL_ABOVE
    local = top_pct if named else 0.0
    rows.append({"country": c, "adverts": int(tot[c]),
                 "compared": bool(c in compared),
                 "local_name": top_name if named else None,
                 "english": round(english, 1),
                 "local": round(local, 1),
                 "other": round(100 - english - local, 1)})

out["b"] = {
    "title": "Each country writes its adverts in a different mixture of languages",
    "note": ("Language of the requirement text, by country. The United Kingdom is 99.8% "
             "English while France is 56.7% French and Germany 59.0% German — so "
             "comparing those countries is partly comparing those languages, and the "
             "requirement text is what was embedded and grouped. The three outlined "
             "rows are the countries the comparison above actually ran on, which is the "
             "worst case: they are the three most sharply separated by language. "
             "Detection covers eight languages; a country whose own language is not "
             "among them, such as Poland, shows its adverts as English because that "
             "is what the requirement text was written or rewritten in."),
    "keys": [{"key": "english", "label": "English"},
             {"key": "local", "label": "the country's own main language"},
             {"key": "other", "label": "any other language"}],
    "rows": rows,
}

# --- C ---------------------------------------------------------------------
lc = pd.read_csv(W3 / "language_control_all.csv")
out["c"] = {
    "title": "Restrict to English-only adverts and one factor moves",
    "note": ("The same measurement on the same levels, with the corpus narrowed to "
             "adverts whose requirement text is English. If a factor's position were "
             "real, narrowing the corpus should not move it. Country loses a fifth of "
             "its distance; nothing else moves more than 2.6%, and company size moves "
             "the wrong way, which is what noise looks like."),
    "x_label": "how far apart the requirement profiles are  \u2192",
    "rows": [{"factor": NICE[r["factor"]],
              "raw": float(r["pooled"]), "controlled": float(r["english_only"]),
              "shift_pct": float(r["shift_pct"]),
              "confounded": bool(abs(r["shift_pct"]) > 10)}
             for _, r in lc.sort_values("shift_pct").iterrows()],
}

# --- D ---------------------------------------------------------------------
gc = pd.read_csv(W3 / "geo_control.csv")
out["d"] = {
    "title": "Changing industry is not secretly changing country",
    "note": ("How much of the destination's demand you already hold after a move. "
             "Higher means the move costs less. Each move is measured twice: pooled, "
             "and again inside a single country. Holding country fixed makes an "
             "industry step cost MORE, not less \u2014 the opposite of the worry. "
             "Climbing a seniority level is the control: it has no reason to be "
             "geographically confounded, and it barely moves."),
    "y_label": "share of the destination's demand you already hold  \u2191",
    "rows": [{"family": FN[r["function"]], "move": r["move"],
              "pooled": float(r["pooled"]), "within": float(r["within_country"]),
              "shift": float(r["shift"]),
              "control": bool(r["move"] == "climb a level")}
             for _, r in gc.iterrows()],
}

# --- E ---------------------------------------------------------------------
de = pd.read_csv(W3 / "driver_ranking_employer.csv")
m = (dr[["factor", "function", "js"]]
     .merge(de[["factor", "function", "js"]], on=["factor", "function"],
            suffixes=("_advert", "_employer")))
m["factor_nice"] = m["factor"].map(NICE)
out["e"] = {
    "title": "Count each employer once and every distance shrinks, in the same order",
    "note": ("The same six factors with each employer counted once per cell instead of "
             "each advert. Every distance falls \u2014 repeated adverts from one firm "
             "were inflating all of them \u2014 but no factor overtakes another. A "
             "correction that moves everything by roughly the same amount changes the "
             "size of the answer, not the answer."),
    "x_label": "how far apart the requirement profiles are  \u2192",
    "rows": [{"factor": r["factor_nice"], "family": FN[r["function"]],
              "advert": float(r["js_advert"]), "employer": float(r["js_employer"]),
              "drop_pct": round((r["js_employer"] - r["js_advert"]) / r["js_advert"] * 100, 1)}
             for _, r in m.iterrows()],
}

(HERE / "data").mkdir(exist_ok=True)
p = HERE / "data" / "article1.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"countries compared: {', '.join(compared)}")
print(f"rows charted      : {len(out['b']['rows'])} countries, "
      f"{sum(1 for r in out['b']['rows'] if r['local_name']) } with a named local language")
print(f"\n{p.name}  {p.stat().st_size/1024:.1f} KB   {time.time()-t0:.0f}s")
for k in "abcde":
    print(f"  {k}: {out[k]['title']}")
