"""ESCO anchoring: which requirement clusters the taxonomy has no concept for.

The residual — clusters with no ESCO anchor within threshold — **is Hypothesis
2**. That makes the threshold the most consequential number in Week 2, because
it decides the size of the very thing being claimed. So it is not set by taste.

**How the threshold is set.** The same way Week 1 licensed the cross-lingual
comparison: with a positive *and* a negative control. Clusters that obviously
are ESCO concepts — a named language, a common degree, a named tool — give the
distribution of a genuine anchor. Randomly paired cluster/concept cosines give
the distribution of no relationship. The threshold goes where those separate,
and the separation is reported: if the two overlap, anchoring cannot support a
residual claim at all, and that is the finding rather than a reason to pick a
number anyway.

A single arbitrary cosine would let the residual be whatever we wanted it to be,
which for a hypothesis *about* the residual is not acceptable.

**Two decisions belong to the data, not the code**, and both must be recorded:

* *Which ESCO version.* Concepts are added between releases, so the residual is
  version-sensitive. Pin it and print it, exactly as the embedding checkpoint is.
* *Which language's labels.* Clusters here are multilingual — `communication`
  sits with `kommunikationsfahigkeiten`. Anchoring a French-heavy cluster
  against English labels measures translation distance on top of concept
  distance. ESCO publishes 28 languages; using them costs a larger anchor set
  and removes that confound.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Header names the ESCO CSV distribution has used for the skills pillar. Matched
# tolerantly by lowercase substring, because the exact set has changed between
# releases and a hard-coded name would break silently on the next one.
URI_HINTS = ("conceptUri", "uri")
LABEL_HINTS = ("preferredLabel", "preferred_label", "title")
ALT_HINTS = ("altLabels", "alternativeLabel", "alt_labels")
TYPE_HINTS = ("skillType", "hasSkillType", "conceptType")


def _pick(columns, hints):
    lower = {c.lower(): c for c in columns}
    for hint in hints:
        if hint.lower() in lower:
            return lower[hint.lower()]
    for hint in hints:
        for c in columns:
            if hint.lower() in c.lower():
                return c
    return None


def load_skills(path, languages: list[str] | None = None) -> pd.DataFrame:
    """Load the ESCO skills pillar from the CSV distribution.

    Returns one row per **label**, not per concept. Alternative labels are real
    anchor surface — `k8s` should reach Kubernetes — and keeping only preferred
    labels would inflate the residual by discarding the wording employers
    actually use.
    """
    path = Path(path)
    files = sorted(path.glob("skills*.csv")) if path.is_dir() else [path]
    if not files:
        raise FileNotFoundError(
            f"No skills CSV under {path}. Download the ESCO 'classification' in "
            "CSV from https://esco.ec.europa.eu/en/use-esco/download (registration "
            "and accepting the statement are required) and point this at the folder."
        )

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str).fillna("")
        uri = _pick(df.columns, URI_HINTS)
        lab = _pick(df.columns, LABEL_HINTS)
        alt = _pick(df.columns, ALT_HINTS)
        typ = _pick(df.columns, TYPE_HINTS)
        if not uri or not lab:
            raise ValueError(
                f"{f.name}: no URI/label column found among {list(df.columns)}"
            )

        lang = f.stem.split("_")[-1] if "_" in f.stem else "unknown"
        if languages and lang not in languages:
            continue

        rows = []
        for _, r in df.iterrows():
            if r[lab].strip():
                rows.append({"concept_uri": r[uri], "label": r[lab].strip(),
                             "kind": "preferred", "language": lang,
                             "skill_type": r[typ] if typ else ""})
            if alt:
                for a in str(r[alt]).replace("|", "\n").split("\n"):
                    if a.strip():
                        rows.append({"concept_uri": r[uri], "label": a.strip(),
                                     "kind": "alternative", "language": lang,
                                     "skill_type": r[typ] if typ else ""})
        frames.append(pd.DataFrame(rows))

    if not frames:
        raise ValueError(f"no files matched languages={languages}")
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(["concept_uri", "label"]).reset_index(drop=True)


# --- RDF distribution -------------------------------------------------------
#
# Karimi downloaded RDF rather than CSV, and the file is 1.35 GB uncompressed.
# Loading it with `rdflib` would build a full in-memory triple store — many
# gigabytes and a long wait — to extract two fields per concept. So it is
# **stream-parsed** instead: `iterparse` over `skos:Concept` elements, clearing
# each one after reading it, so memory stays flat and no dependency is added.
# The archive is read directly, so the 1.35 GB is never written to disk either.
SKOS = "{http://www.w3.org/2004/02/skos/core#}"
RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
ISOTHES = "{http://purl.org/iso25964/skos-thes#}"

# Skills live under /esco/skill/; occupations under /esco/occupation/. Filtering
# on the URI is more robust than reading `skos:inScheme`, which appears several
# times per concept with different scheme URIs.
SKILL_URI_MARKER = "/esco/skill/"


def load_skills_rdf(archive, member: str | None = None,
                    languages: tuple[str, ...] = ("en", "de", "fr", "it", "es", "nl"),
                    include_obsolete: bool = False) -> pd.DataFrame:
    """Stream the skills pillar out of the ESCO RDF/XML distribution.

    Returns one row per label — preferred and alternative, per language —
    because alternative labels are real anchor surface and dropping them would
    inflate the residual by discarding the wording employers use.

    **Obsolete concepts are excluded by default.** ESCO marks superseded
    concepts with `iso-thes:status = obsolete` and keeps them in the
    distribution. Letting them anchor would mean a cluster counted as "covered
    by the taxonomy" on the strength of a concept the taxonomy has retired,
    which is precisely backwards for a claim about what ESCO lacks.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    archive = Path(archive)
    rows: list[dict] = []
    n_concepts = n_obsolete = 0

    if archive.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(archive)
        member = member or next(n for n in zf.namelist() if n.lower().endswith((".rdf", ".xml")))
        stream = zf.open(member)
    else:
        stream = open(archive, "rb")

    try:
        for event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != f"{SKOS}Concept":
                continue
            uri = elem.get(f"{RDF_NS}about", "")
            if SKILL_URI_MARKER not in uri:
                elem.clear()
                continue
            n_concepts += 1

            status = elem.findtext(f"{ISOTHES}status", default="")
            if status.strip().lower() == "obsolete":
                n_obsolete += 1
                if not include_obsolete:
                    elem.clear()
                    continue

            for kind, tag in (("preferred", f"{SKOS}prefLabel"),
                              ("alternative", f"{SKOS}altLabel")):
                for child in elem.findall(tag):
                    lang = child.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                    text = (child.text or "").strip()
                    if text and lang in languages:
                        rows.append({"concept_uri": uri, "label": text,
                                     "kind": kind, "language": lang,
                                     "skill_type": ""})
            elem.clear()
    finally:
        stream.close()

    out = pd.DataFrame(rows).drop_duplicates(["concept_uri", "label", "language"])
    out.attrs["n_skill_concepts"] = n_concepts
    out.attrs["n_obsolete_skipped"] = 0 if include_obsolete else n_obsolete
    return out.reset_index(drop=True)


def embed_skills(skills: pd.DataFrame, out_path, model=None) -> dict:
    """Embed ESCO labels with the SAME model the corpus used.

    Anchoring compares cluster centroids against concept vectors, so a
    different checkpoint makes every cosine meaningless. This reaches for
    `embed.load_model` by default rather than accepting any model, because that
    is the failure most likely to go unnoticed.
    """
    from . import embed as emb

    model = model or emb.load_model()
    labels = skills["label"].tolist()
    vectors = emb.encode(model, labels)
    vectors = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    np.savez_compressed(
        out_path,
        labels=np.array(labels, dtype=object),
        uris=np.array(skills["concept_uri"].tolist(), dtype=object),
        vectors=vectors,
    )
    return {"labels": len(labels), "concepts": skills["concept_uri"].nunique(),
            "path": str(out_path)}


def load_skill_vectors(path) -> tuple[list[str], list[str], np.ndarray]:
    z = np.load(path, allow_pickle=True)
    return list(z["labels"]), list(z["uris"]), z["vectors"]


def anchor(centroids: np.ndarray, cluster_ids: list[int], skill_vectors: np.ndarray,
           skill_uris: list[str], skill_labels: list[str]) -> pd.DataFrame:
    """Nearest ESCO concept for each cluster centroid, with its cosine."""
    unit = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12, None)
    sims = unit @ skill_vectors.T
    best = sims.argmax(axis=1)
    return pd.DataFrame({
        "cluster": cluster_ids,
        "esco_uri": [skill_uris[i] for i in best],
        "esco_label": [skill_labels[i] for i in best],
        "cosine": sims[np.arange(len(sims)), best].round(4),
    })


def null_distribution(centroids: np.ndarray, skill_vectors: np.ndarray,
                      seed: int = 20260907) -> np.ndarray:
    """Best-of-set cosine against RANDOM concepts — the negative control.

    The null has to perform the same operation as the thing it controls for.
    `anchor` takes the **maximum** cosine over every ESCO label, and the maximum
    of tens of thousands of draws is far above any single draw — so a null built
    from random *pairs* would show separation on pure noise. It did: a dry run on
    random vectors reported separation 0.184 and passed as usable, which is the
    bug this docstring exists to prevent recurring.

    So the null is max-over-a-set-of-the-same-size, using random unit vectors in
    place of the concept vectors. It answers the right question: how good a match
    would the best of this many concepts be, if none of them meant anything?
    """
    rng = np.random.default_rng(seed)
    unit = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12, None)

    # The query is meaningless but the CORPUS IS REAL. Permuting each centroid's
    # dimensions preserves its norm and marginal distribution while destroying
    # its semantic direction, so the null asks the right question: how high does
    # the best of 214,482 *real* concept vectors go for a query that means
    # nothing?
    #
    # A previous version drew random Gaussian unit vectors as the concept set.
    # Those are near-orthogonal to everything in 384 dimensions and scored ~0.23,
    # while real sentence embeddings of short skill phrases sit in a narrow cone
    # and score ~0.87 against each other regardless of meaning. That null put the
    # threshold at 0.25, every cluster cleared it, and the residual came out at
    # exactly 0.0% — which is how a broken control announces itself.
    permuted = np.empty_like(unit)
    for i in range(len(unit)):
        permuted[i] = rng.permutation(unit[i])
    permuted /= np.clip(np.linalg.norm(permuted, axis=1, keepdims=True), 1e-12, None)
    return (permuted @ skill_vectors.T).max(axis=1)


def calibrate(anchored: pd.DataFrame, named: pd.DataFrame, null: np.ndarray,
              positive_types=("language", "credential", "technical"),
              null_quantile: float = 0.95) -> dict:
    """Set the anchoring threshold from both controls, and report the separation.

    Positive control: clusters whose dominant requirement type is one ESCO
    certainly covers. Negative control: the shuffled-pair distribution.

    The threshold sits at the null distribution's `null_quantile`, so at most
    5% of no-relationship pairs would be called anchored. `separation` is the
    gap between the positive mean and the null mean; if it is small the two
    distributions overlap and no threshold makes the residual meaningful.
    """
    joined = anchored.merge(named[["cluster", "top_type"]], on="cluster", how="left")
    pos = joined.loc[joined["top_type"].isin(positive_types), "cosine"].dropna()

    threshold = float(np.quantile(null, null_quantile))
    out = {
        "threshold": round(threshold, 4),
        "null_quantile": null_quantile,
        "null_mean": round(float(null.mean()), 4),
        "null_p95": round(float(np.quantile(null, 0.95)), 4),
        "n_positive_clusters": int(len(pos)),
        "positive_mean": round(float(pos.mean()), 4) if len(pos) else None,
        "positive_p05": round(float(pos.quantile(0.05)), 4) if len(pos) else None,
        "separation": round(float(pos.mean() - null.mean()), 4) if len(pos) else None,
        "positive_above_threshold": (
            round(float((pos >= threshold).mean()), 4) if len(pos) else None),
        "positive_types": list(positive_types),
    }
    out["usable"] = bool(out["positive_above_threshold"] and
                         out["positive_above_threshold"] >= 0.80)
    return out


def residual_both_ways(assigned: pd.DataFrame, reqs: pd.DataFrame,
                       anchored: pd.DataFrame, threshold: float) -> dict:
    """The H2 residual, on all atoms and excluding compound atoms.

    Three outcomes, each meaning something different, so they are never
    collapsed into one number:

    * **unchanged** — H2 survives the extraction shortfall;
    * **higher** without compounds — compounds were anchoring *spuriously* and
      the residual was understated;
    * **lower** without compounds — compounds were inflating it and part of the
      residual is our own under-splitting.
    """
    unanchored = set(anchored.loc[anchored["cosine"] < threshold, "cluster"])

    def share(sub: pd.DataFrame) -> dict:
        j = sub.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
        j["cluster"] = j["cluster"].fillna(-1).astype(int)
        by_fn = j.groupby("macro_function")["cluster"].apply(
            lambda c: float(c.isin(unanchored).mean()))
        return {"overall": round(float(j["cluster"].isin(unanchored).mean()), 4),
                **{k: round(float(v), 4) for k, v in by_fn.items()}}

    all_atoms = share(reqs)
    no_compounds = share(reqs[~reqs["looks_compound"]])
    return {
        "threshold": threshold,
        "n_unanchored_clusters": len(unanchored),
        "residual_all_atoms": all_atoms,
        "residual_excluding_compounds": no_compounds,
        "difference": {k: round(no_compounds[k] - all_atoms[k], 4) for k in all_atoms},
    }
