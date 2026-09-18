"""Step 17, follow-up: is the country effect really a language effect?

Country came top of the ranking, and there is an obvious reason to distrust that
before publishing it. **Adverts in France are written in French and adverts in
Germany in German**, and the cluster structure is partly language-shaped:
`Computer Science degree` exists three times over (English, German, French), and
`English proficiency` four times. Two countries can therefore land far apart
while asking for exactly the same things in different words.

If that is what is happening, "country moves requirements most" is a fact about
our clustering, not about European labour markets.

**The test.** Recompute the country index over adverts written in ENGLISH only.
Language is then held constant and whatever distance remains between countries
is real. A collapse means the ranking was measuring vocabulary.

A control runs alongside: the same restriction applied to `company_industry`. If
restricting to English shrinks every factor equally, the shrinkage is a sample-size
artefact rather than evidence about country.
"""
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import data, language as lang, variance as var

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
t0 = time.time()

DRAWS = 150

base = data.build_analysis_base().df
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
drop = set(named.loc[named["boilerplate"] == True, "cluster"]) | \
       set(named.loc[named["label"].astype(str).str.upper() == "MIXED", "cluster"])

# the language OF THE REQUIREMENT TEXT, not of the advert record: 10.9% differ
det = lang.detect_series(base["must_have"])
base["text_lang"] = det["detected"].where(det["hits"] >= 1, base["language"])
join = ["text_lang"] + [c for c in ("geo_country", "company_industry")
                        if c not in reqs.columns]
reqs = reqs.merge(base[["vacancy_id"] + join], on="vacancy_id", how="left")

print("=" * 88)
print("ENGLISH-LANGUAGE ADVERTS PER COUNTRY")
print("=" * 88)
post = base.drop_duplicates("vacancy_id")
eng = post[post["text_lang"] == "English"]
ct = pd.crosstab(eng["geo_country"], eng["macro_function"])
ct["min"] = ct.min(axis=1)
print(ct.nlargest(8, "min").to_string())
print("")

countries = ct[ct["min"] >= 120].nlargest(3, "min").index.tolist()
print(f"countries with >=120 English adverts in both functions: {countries}")
n_eng = int(ct.loc[countries, "min"].min())
print(f"common cell size for the English-only run: n = {n_eng}")
print("")

reqs_en = reqs[reqs["text_lang"] == "English"]

print("=" * 88)
print("COUNTRY: ALL LANGUAGES vs ENGLISH ONLY")
print("=" * 88)
for label, frame, lv in [("all languages", reqs, countries),
                         ("ENGLISH ONLY ", reqs_en, countries)]:
    boot = var.bootstrap(asg, frame, exclude=drop, unit="vacancy_id", draws=DRAWS,
                         equalise=n_eng, factor="geo_country", levels=lv)
    s = var.summarise(boot)
    for r in s.itertuples():
        print(f"  {label}  {r.function:<14} JS {r.js_mean:.4f} "
              f"[{r.js_lo:.4f}, {r.js_hi:.4f}]   cosine {r.cosine_mean:.4f}")
    print("")

print("=" * 88)
print("CONTROL — the same restriction applied to INDUSTRY")
print("=" * 88)
ct_i = pd.crosstab(eng["company_industry"], eng["macro_function"])
inds = ct_i[ct_i.min(axis=1) >= 120].nlargest(3, ct_i.columns[0]).index.tolist()
print(f"  industries with >=120 English adverts in both: {inds}")
for label, frame in [("all languages", reqs), ("ENGLISH ONLY ", reqs_en)]:
    boot = var.bootstrap(asg, frame, exclude=drop, unit="vacancy_id", draws=DRAWS,
                         equalise=n_eng, factor="company_industry", levels=inds)
    s = var.summarise(boot)
    for r in s.itertuples():
        print(f"  {label}  {r.function:<14} JS {r.js_mean:.4f} "
              f"[{r.js_lo:.4f}, {r.js_hi:.4f}]")
    print("")
print(f"total {time.time()-t0:.0f}s")
