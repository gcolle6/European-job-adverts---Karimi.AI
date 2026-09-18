"""Cluster 615, opened fully — and is the defect confined to it?

A single-word requirement is not automatically damage. French and German adverts
genuinely list bare attributes as bullets (`Rigueur`, `Zuverlässigkeit`), and
those are the employer's own wording. What IS damage is a bare **relational
noun** — a word that cannot denote a requirement without a complement.
`Fähigkeit` means "ability"; ability to do what? `Bereitschaft` means
"willingness"; willingness to do what? The complement carried the requirement
and the split threw it away.

So the test is not length. It is whether the token is a relational noun, which
is a closed, auditable list per language rather than a curated set of strings.
Measured corpus-wide, not just inside 615, because a defect found in one cluster
is only interesting once you know whether it is everywhere.
"""
import re
import sys

sys.path.insert(0, r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

OUT = r"c:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
pd.set_option("display.width", 250)

# Relational nouns: they take an obligatory complement, so alone they denote
# nothing. Listed per language, on the NORMALISED form (accents stripped).
RELATIONAL = {
    # German
    "fahigkeit", "fahigkeiten", "bereitschaft", "kenntnis", "kenntnisse",
    "erfahrung", "erfahrungen", "verstandnis", "interesse", "umgang",
    "beherrschung", "affinitat", "freude", "begeisterung", "gespur",
    # English
    "ability", "abilities", "willingness", "knowledge", "experience",
    "understanding", "interest", "familiarity", "proficiency", "command",
    "awareness", "aptitude", "affinity", "passion", "enthusiasm",
    # French
    "capacite", "capacites", "connaissance", "connaissances", "maitrise",
    "experience", "comprehension", "interet", "gout", "aisance", "sens",
    "appetence", "attrait",
    # Italian / Spanish / Portuguese
    "capacita", "conoscenza", "conoscenze", "esperienza", "comprensione",
    "padronanza", "attitudine", "interesse", "predisposizione",
    "capacidad", "conocimiento", "conocimientos", "experiencia", "dominio",
    "comprension", "manejo", "interes",
    "capacidade", "conhecimento", "conhecimentos", "experiencia", "dominio",
    # Dutch
    "kennis", "ervaring", "vermogen", "begrip", "affiniteit", "interesse",
    "bereidheid", "beheersing",
}

# Filler that is not a requirement at all under any reading.
FILLER = {"und", "and", "et", "of", "in", "a", "the", "de", "des", "du", "e",
          "o", "y", "ou", "or", "with", "mit", "avec", "con", "com", "sowie",
          "plus", "etc", "ecc", "usw", "idealerweise", "ideally", "bonus",
          "vorteil", "plus", "gerne", "gern"}

reqs = pd.read_parquet(r"week 1/output/requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
j["cluster"] = j["cluster"].fillna(-1).astype(int)
j["n_words"] = j["phrase"].astype(str).str.split().str.len()
j["norm1"] = j["phrase_norm"].astype(str).str.lower().str.strip()

j["bare_relational"] = (j["n_words"] == 1) & j["norm1"].isin(RELATIONAL)
j["bare_filler"] = (j["n_words"] == 1) & j["norm1"].isin(FILLER)
j["unusable"] = j["bare_relational"] | j["bare_filler"]

print("=" * 88)
print("1. CLUSTER 615, FULLY DECOMPOSED")
print("=" * 88)
sub = j[j["cluster"] == 615]
n = len(sub)
cats = {
    "bare relational noun (damage)": int(sub["bare_relational"].sum()),
    "bare filler (damage)": int(sub["bare_filler"].sum()),
    "other single word (employer's own bullet)":
        int(((sub["n_words"] == 1) & ~sub["unusable"]).sum()),
    "two or more words": int((sub["n_words"] >= 2).sum()),
}
for k, v in cats.items():
    print(f"  {k:<46} {v:>6,}  {v/n:>6.1%}")
print(f"  {'TOTAL':<46} {n:>6,}")
print("")
print("  the damage, itemised:")
for p, c in sub.loc[sub["unusable"], "phrase"].value_counts().head(12).items():
    print(f"    {c:>5}  {p}")
print("")
print("  the legitimate single words, for contrast:")
for p, c in sub.loc[(sub["n_words"] == 1) & ~sub["unusable"], "phrase"].value_counts().head(12).items():
    print(f"    {c:>5}  {p}")
print("")

print("=" * 88)
print("2. IS IT CONFINED TO 615? corpus-wide")
print("=" * 88)
tot = len(j)
print(f"  all requirements                       {tot:>8,}")
print(f"  bare relational nouns                  {int(j['bare_relational'].sum()):>8,}  "
      f"{j['bare_relational'].mean():>6.2%}")
print(f"  bare filler                            {int(j['bare_filler'].sum()):>8,}  "
      f"{j['bare_filler'].mean():>6.2%}")
print(f"  UNUSABLE TOTAL                         {int(j['unusable'].sum()):>8,}  "
      f"{j['unusable'].mean():>6.2%}")
print(f"  of which sit in cluster 615            "
      f"{int(j.loc[j['cluster']==615,'unusable'].sum()):>8,}  "
      f"{j.loc[j['unusable'],'cluster'].eq(615).mean():>6.1%} of the damage")
print("")
print("  which clusters hold the rest:")
d = (j[j["unusable"]].groupby("cluster").size().rename("unusable").reset_index()
     .merge(named[["cluster", "label", "occurrences"]], on="cluster", how="left"))
d["pct_of_cluster"] = (d["unusable"] / d["occurrences"] * 100).round(1)
print(d.nlargest(10, "unusable")[["cluster", "label", "unusable", "occurrences",
                                  "pct_of_cluster"]].to_string(index=False))
print("")

print("=" * 88)
print("3. MEAN WORDS PER CLUSTER — is it a usable damage detector?")
print("=" * 88)
mw = j[j["cluster"] != -1].groupby("cluster").agg(
    occurrences=("phrase", "size"),
    mean_words=("n_words", "mean"),
    pct_single=("n_words", lambda s: float((s == 1).mean()) * 100),
    pct_unusable=("unusable", lambda s: float(s.mean()) * 100),
).reset_index().merge(named[["cluster", "label", "top_type"]], on="cluster", how="left")
mw["mean_words"] = mw["mean_words"].round(2)
mw["pct_single"] = mw["pct_single"].round(1)
mw["pct_unusable"] = mw["pct_unusable"].round(1)
print("  the 12 clusters with the shortest requirements:")
print(mw.nsmallest(12, "mean_words")[
    ["cluster", "label", "occurrences", "mean_words", "pct_single",
     "pct_unusable", "top_type"]].to_string(index=False))
print("")
lo = mw[mw["mean_words"] < 2.5]
hi = mw[mw["mean_words"] >= 2.5]
print(f"  clusters with mean_words < 2.5 : {len(lo):>3}   mean unusable share "
      f"{lo['pct_unusable'].mean():.2f}%")
print(f"  clusters with mean_words >= 2.5: {len(hi):>3}   mean unusable share "
      f"{hi['pct_unusable'].mean():.2f}%")
print("")
mw.to_csv(OUT + r"\cluster_word_length.csv", index=False, encoding="utf-8")
print(f"  written: cluster_word_length.csv")

print("")
print("=" * 88)
print("4. WHAT WOULD DROPPING THEM CHANGE?")
print("=" * 88)
kept = j[~j["unusable"]]
print(f"  requirements: {tot:,} -> {len(kept):,}  (-{j['unusable'].sum():,}, "
      f"-{j['unusable'].mean():.2%})")
for fn in sorted(j["macro_function"].dropna().unique()):
    a = j[j["macro_function"] == fn]
    print(f"  {fn:<16} unusable {a['unusable'].mean():>6.2%}")
print("")
print("  postings that would lose ALL their requirements:")
before = j.groupby("vacancy_id").size()
after = kept.groupby("vacancy_id").size()
lost = set(before.index) - set(after.index)
print(f"    {len(lost)} of {len(before):,}")
print("")
print("  affected clusters' share of the boilerplate set:")
bp = set(named.loc[named["boilerplate"] == True, "cluster"])
in_bp = j.loc[j["unusable"], "cluster"].isin(bp).mean()
print(f"    {in_bp:.1%} of the damage sits in clusters already set aside as boilerplate")
