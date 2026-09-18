"""The language control, for every factor — not just the two that motivated it.

Country was recomputed on English-only adverts because language and country are
obviously confounded, and industry was recomputed as its control. That leaves
three factors with no stated reason for their position, which is not good enough
for a chart whose whole point is the gap between raw and controlled.

So the same restriction is applied to all five. The expectation is that only
country moves — but an expectation is not a measurement, and this project has
been wrong about the direction of a control twice already.

The comparison holds everything else fixed: same levels, same cell-size
equalisation, same number of levels per factor. Only the corpus narrows.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import data, language as lang, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

FACTORS = ["geo_country", "seniority", "company_industry", "company_type", "company_size"]
MIN_LEVEL = 120
DRAWS = 120

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

# the language OF THE REQUIREMENT TEXT — the advert's recorded language differs
# for 10.9% of postings, and it is the text that was embedded
det = lang.detect_series(base["must_have"])
base["text_lang"] = det["detected"].where(det["hits"] >= 1, base["language"])
post = base.drop_duplicates("vacancy_id")
eng_ids = set(post.loc[post["text_lang"] == "English", "vacancy_id"])

join = [c for c in FACTORS if c not in reqs.columns]
reqs = reqs.merge(post[["vacancy_id"] + join], on="vacancy_id", how="left")
reqs_en = reqs[reqs["vacancy_id"].isin(eng_ids)]

print(f"corpus {post['vacancy_id'].nunique():,} adverts, "
      f"English text {len(eng_ids):,} ({len(eng_ids)/len(post):.1%})")
print("")


def index_for(frame, factor, levels, n):
    boot = var.bootstrap(asg, frame, exclude=drop, unit="vacancy_id", draws=DRAWS,
                         equalise=n, factor=factor, levels=levels)
    s = var.summarise(boot)
    return float(s["js_mean"].mean())


rows = []
for f in FACTORS:
    # levels must clear the floor in BOTH functions and in the English subset,
    # or the two runs would not be comparing the same cells
    ct_all = pd.crosstab(post[f], post["macro_function"])
    eng = post[post["vacancy_id"].isin(eng_ids)]
    ct_en = pd.crosstab(eng[f], eng["macro_function"])
    ok = [lv for lv in ct_all.index
          if lv in ct_en.index
          and (ct_all.loc[lv] >= MIN_LEVEL).all()
          and (ct_en.loc[lv] >= MIN_LEVEL).all()]
    if len(ok) < 3:
        print(f"  {f:<18} UNPOWERED — only {len(ok)} levels clear {MIN_LEVEL} "
              f"in both functions and in English")
        rows.append({"factor": f, "levels": len(ok), "pooled": None,
                     "english_only": None})
        continue
    top = ct_en.loc[ok].min(axis=1).nlargest(3).index.tolist()
    n = int(min(ct_en.loc[top].min().min(), ct_all.loc[top].min().min()))
    a = index_for(reqs, f, top, n)
    b = index_for(reqs_en, f, top, n)
    rows.append({"factor": f, "levels": 3, "pooled": a, "english_only": b})
    print(f"  {f:<18} n={n:<5} {', '.join(str(x)[:18] for x in top)}")

d = pd.DataFrame(rows).dropna(subset=["pooled"])
d["shift_pct"] = ((d["english_only"] - d["pooled"]) / d["pooled"] * 100).round(1)
d["pooled"] = d["pooled"].round(4)
d["english_only"] = d["english_only"].round(4)
d = d.sort_values("shift_pct")

print("")
print("=" * 88)
print("THE LANGUAGE CONTROL, ALL FACTORS")
print("=" * 88)
print(d.to_string(index=False))
print("")
worst = d.iloc[0]
rest = d.iloc[1:]["shift_pct"].abs().max()
print(f"  {worst['factor']} loses {abs(worst['shift_pct']):.1f}%")
print(f"  every other factor moves at most {rest:.1f}%")
print("")
print("  If only country moves, the confound is specific and the chart is honest.")
print("  If several move, the restriction is changing the corpus, not isolating")
print("  a confound — and the dumbbell would be showing a sampling artefact.")

d.to_csv(W3 + r"\language_control_all.csv", index=False, encoding="utf-8")
print(f"\nwritten: language_control_all.csv   total {time.time()-t0:.0f}s")
