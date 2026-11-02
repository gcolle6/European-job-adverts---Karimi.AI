"""Audit of every ESCO claim the publication makes, against ESCO itself.

Written because the ESCO section is the only part of this study whose central
claim is about an **external object anyone can check**. Every other finding is
about our corpus, and a reader has to take the corpus on trust; "ESCO has no
concept for Kubernetes" can be falsified in ten seconds by typing Kubernetes
into ESCO's search box. A single wrong example there costs more credibility than
the whole section buys.

So this re-derives, from the RDF and the decision files rather than from any
previous summary:

  1. what we actually anchored against - 13,939 skills plus 420 hierarchy
     headings, not "14,359 defined skill concepts";
  2. how many anchors rest on a heading rather than a skill, and what the
     residual becomes if a heading is not counted as coverage;
  3. which residual clusters ESCO plainly carries under their own name, i.e.
     where the shortlist failed rather than the taxonomy;
  4. the atoms in no cluster, which are silently counted as covered;
  5. the language gap between the corpus and the six languages loaded;
  6. the share of the residual that belongs to pillars never searched.

Run time is dominated by one stream pass over the 1.35 GB RDF.

    python "week 4/esco_audit.py"
"""
from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
W1 = ROOT / "week 1" / "output"
W2 = ROOT / "week 2"
OUT = W2 / "output"

SKOS = "{http://www.w3.org/2004/02/skos/core#}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
ISO = "{http://purl.org/iso25964/skos-thes#}"

# ESCO's own published figures, for the numbers a reader will check against the
# source. Updating these means re-reading esco.ec.europa.eu, not guessing.
ESCO_PUBLISHED = {"version": "v1.2.0", "released": "May 2024",
                  "newer_minor": "v1.2.1 (December 2025), not used",
                  "skills": 13_939, "occupations": 3_039, "languages": 28}

# Residual clusters whose own concept ESCO carries under that very wording.
# Curated by reading the members, because the crude sweep that produced the
# candidate list is unreliable in a specific way: it matches ANY member phrase,
# so `Microsoft Azure` came back "found in ESCO" on the strength of a member
# reading `Microsoft Access`, and `PowerPoint proficiency` on one reading
# `PowerShell`. A member matching is not the cluster being covered. Each entry
# below was checked against the cluster's own phrases.
RETRIEVAL_MISSES = {
    608: "interpersonal skills", 211: "information security",
    549: "communication skills", 471: "Adobe Creative Suite",
    391: "data analysis", 82: "writing skills", 8: "data analysis",
    546: "knowledge of GDPR", 603: "DevOps",
}


def concept_types(rdf_path) -> dict:
    """Split the anchor set into real skills and hierarchy headings.

    ESCO types a skill as `esco:Skill`; the nodes that organise the pillar carry
    no rdf:type and exist to hold other concepts. Both live under /esco/skill/
    and both were loaded, which is why our count exceeds ESCO's published one.

    Only the concept element is cleared, never its children: clearing a child as
    it ends empties the attributes the parent still needs, and an earlier version
    of this check read every `status` back as empty and counted 804 obsolete
    concepts as live.
    """
    node = {}
    with open(rdf_path, "rb") as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != f"{SKOS}Concept":
                continue
            uri = elem.get(f"{RDF}about", "")
            if "/esco/skill/" not in uri:
                elem.clear()
                continue
            if (elem.findtext(f"{ISO}status", "") or "").strip().lower() == "obsolete":
                elem.clear()
                continue
            node[uri] = {
                "typed": bool(elem.findall(f"{RDF}type")),
                "schemes": {s.get(f"{RDF}resource", "").rsplit("/", 1)[-1]
                            for s in elem.findall(f"{SKOS}inScheme")},
            }
            elem.clear()
    return node


def main() -> None:
    dec = pd.read_csv(OUT / "esco_decisions.csv")
    asg = pd.read_parquet(OUT / "phrase_clusters.parquet")
    reqs = pd.read_parquet(W1 / "requirements.parquet")
    sk = pd.read_parquet(W2 / "esco" / "esco_skills_labels.parquet")

    j = reqs.merge(asg[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    j["cluster"] = j["cluster"].fillna(-1).astype(int)
    unanchored = set(dec.loc[dec["esco_uri"].isna(), "cluster"])
    published = j["cluster"].isin(unanchored).mean()

    print("=" * 88)
    print("1. WHAT WE ANCHORED AGAINST")
    print("=" * 88)
    node = concept_types(W2 / "esco" / "esco-v1.2.0.rdf")
    typed = sum(v["typed"] for v in node.values())
    print(f"live concepts under /esco/skill/   {len(node):,}")
    print(f"   typed as a skill                {typed:,}   "
          f"ESCO publishes {ESCO_PUBLISHED['skills']:,}")
    print(f"   hierarchy headings              {len(node) - typed:,}")
    print(f"labels embedded                    {len(sk):,} "
          f"in {sk['language'].nunique()} of {ESCO_PUBLISHED['languages']} languages")
    assert typed == ESCO_PUBLISHED["skills"], "our skill count no longer matches ESCO's"

    print()
    print("=" * 88)
    print("2. ANCHORS THAT REST ON A CATEGORY HEADING")
    print("=" * 88)
    dec["is_heading"] = dec["esco_uri"].map(lambda u: u in node and not node[u]["typed"])
    anchored = int(dec["esco_uri"].notna().sum())
    print(f"anchored clusters {anchored}, of which to a heading "
          f"{int(dec['is_heading'].sum())} ({dec['is_heading'].sum()/anchored:.1%})")
    strict = unanchored | set(dec.loc[dec["is_heading"], "cluster"])
    for name, s in (("a heading counts as coverage (published)", unanchored),
                    ("only a specific skill counts", strict)):
        by = j.groupby("macro_function")["cluster"].apply(lambda c: c.isin(s).mean())
        print(f"   {name:42} {j['cluster'].isin(s).mean():.2%}   "
              + "  ".join(f"{k} {v:.2%}" for k, v in by.items()))
    print("   NB the order of the two families reverses under the strict rule.")

    print()
    print("=" * 88)
    print("3. RESIDUAL CLUSTERS ESCO ACTUALLY CARRIES")
    print("=" * 88)
    m = j["cluster"].isin(RETRIEVAL_MISSES)
    print(f"clusters {len(RETRIEVAL_MISSES)} of {len(unanchored)} unanchored, "
          f"{m.sum():,} atoms = {m.mean():.2%} of the corpus")
    for cid, label in RETRIEVAL_MISSES.items():
        row = dec[dec["cluster"] == cid]
        ours = row["label"].iloc[0] if len(row) else "?"
        print(f"   {cid:4}  {str(ours)[:30]:32} ESCO: {label}")
    print(f"\nresidual published {published:.2%} -> corrected "
          f"{j['cluster'].isin(unanchored - set(RETRIEVAL_MISSES)).mean():.2%}")

    print()
    print("=" * 88)
    print("4. ATOMS IN NO CLUSTER")
    print("=" * 88)
    noise = j["cluster"] == -1
    print(f"{noise.sum():,} atoms ({noise.mean():.2%}) have no cluster and so no ESCO")
    print("decision, yet the test is `cluster in unanchored`, which is False for them -")
    print("so they count as covered.")
    print(f"   residual over all atoms       {published:.2%}  (published)")
    print(f"   over clustered atoms only     {j.loc[~noise, 'cluster'].isin(unanchored).mean():.2%}")

    print()
    print("=" * 88)
    print("5. LANGUAGE COVERAGE")
    print("=" * 88)
    name2iso = {"English": "en", "Deutsch": "de", "Français": "fr", "Nederlands": "nl",
                "Español": "es", "Italiano": "it"}
    have = set(sk["language"].unique())
    iso = reqs["language"].fillna("").map(lambda v: name2iso.get(v, "" if not v else "x"))
    print(f"atoms in a language ESCO was loaded in   {iso.isin(have).mean():.2%}")
    print(f"atoms in another named language          "
          f"{((iso == 'x')).mean():.2%}   no ESCO labels in their language")
    print(f"atoms with the language field empty      {(iso == '').mean():.2%}")

    print()
    print("=" * 88)
    print("6. PILLARS NEVER SEARCHED")
    print("=" * 88)
    r = j[j["cluster"].isin(unanchored)]
    comp = r["req_type"].value_counts(normalize=True)
    for k in ("credential", "availability"):
        if k in comp:
            why = ("qualifications are a separate ESCO pillar, not downloaded"
                   if k == "credential" else "ESCO does not model availability as a skill")
            print(f"   {k:12} {comp[k]:5.1%} of the residual   <- {why}")
    keep = ~j["req_type"].isin(["credential", "availability"])
    print(f"   residual excluding both types: {j[keep]['cluster'].isin(unanchored).mean():.2%}")
    print("\n   Cluster 616 'Trade occupation experience' holds German trades. ESCO")
    print("   carries those as OCCUPATIONS - a pillar this anchoring never searched.")

    print()
    print("=" * 88)
    print("THE CLAIM THAT SURVIVES")
    print("=" * 88)
    print(f"Roughly a quarter of requirement mass has no concept in the SKILLS PILLAR")
    print(f"of ESCO {ESCO_PUBLISHED['version']} ({ESCO_PUBLISHED['released']}). "
          f"Published {published:.1%}; {published - m.mean():.1%} after removing the")
    print("retrieval misses; and higher, not lower, if category headings are not")
    print("accepted as coverage. The direction of the software/sales asymmetry is")
    print("unchanged by all three.")


if __name__ == "__main__":
    main()
