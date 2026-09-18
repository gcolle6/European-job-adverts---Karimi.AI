"""Building the requirement table: atomise, deduplicate, classify.

The requirement table is the unit of every later measurement. One row per
(posting, requirement), carrying the cell coordinates so shares and lift can be
computed over postings rather than over phrases.
"""

from __future__ import annotations

import re

import pandas as pd

from . import atomise as atom
from . import classify as clf
from . import config


# An atom that still carries a conjunction between two content words, or that is
# still long, is probably two requirements the splitter could not separate.
#
# This flag exists for one specific downstream claim. Week 2 defines the
# taxonomy residual as clusters with no ESCO anchor within threshold, and that
# residual *is* Hypothesis 2 — but an atom holding two requirements has no
# single ESCO concept by construction, so it lands in the residual whatever the
# taxonomy contains. Without the flag, H2 would partly measure our own
# under-splitting, and it would do so in the direction the hypothesis predicts.
_STILL_COMPOUND_RE = re.compile(
    r"\w{3,}\s+(?:and|or|und|oder|et|ou|sowie|nonch[eé]|e|y)\s+\w{3,}", re.I)


# A one-word requirement is not automatically damage. French and German adverts
# genuinely list bare attributes as bullet points — `Rigueur`, `Zuverlässigkeit`,
# `Curiosité` are the employer's own wording and 57% of cluster 615 is exactly
# that. So length is the wrong test.
#
# What *is* damage is a bare **relational noun**: a word that cannot denote a
# requirement without its complement. `Fähigkeit` means "ability" — ability to do
# what? `Bereitschaft` means "willingness" — to do what? The complement carried
# the requirement and the split discarded it. Same for a stranded inflected
# adjective (`Eigenständige`, `Sehr gute mündliche`), which in German and French
# is waiting for a noun that is no longer there.
#
# Both are closed, auditable lists rather than curated strings, and both are
# checked against the NORMALISED phrase, where accents are already stripped.
_RELATIONAL_HEADS = frozenset("""
fahigkeit fahigkeiten bereitschaft kenntnis kenntnisse erfahrung erfahrungen
verstandnis interesse umgang beherrschung affinitat freude begeisterung gespur lust
ability abilities willingness knowledge experience understanding interest
familiarity proficiency command awareness aptitude affinity passion enthusiasm
capacite capacites connaissance connaissances maitrise comprehension interet
gout aisance sens appetence attrait
capacita conoscenza conoscenze esperienza comprensione padronanza attitudine
predisposizione
capacidad conocimiento conocimientos experiencia dominio comprension manejo interes
capacidade conhecimento conhecimentos
kennis ervaring vermogen begrip affiniteit bereidheid beheersing
""".split())

# Filler that is not a requirement under any reading.
_BARE_FILLER = frozenset("""
und and et of in a the de des du e o y ou or with mit avec con com sowie plus
etc ecc usw idealerweise ideally bonus vorteil gerne gern motsvarande
""".split())

# A stranded German adjective ends in an inflection and carries no noun. This
# works for German specifically because German adverts **nominalise** their bare
# bullets — `Zuverlässigkeit`, `Belastbarkeit`, `Durchsetzungsvermögen` — so an
# *inflected* form such as `Selbstständige` or `Analytische` is reliable evidence
# that the noun it agreed with (`Arbeitsweise`, `Denkweise`) has been lost.
#
# ⚠️ The same logic does NOT transfer to the Romance languages, and an earlier
# version of this rule was wrong for exactly that reason. French adverts use bare
# adjectives as legitimate bullets — `Rigoureux`, `Organisé(e)`, `Dynamique` are
# the employer's own wording, not damage — so `-eux/-euse` was removed after it
# flagged 21 occurrences of `rigoureux` that are correct as they stand.
# Morphology is only a stranding signal where the language's own bullet
# convention is nominal.
_STRANDED_ADJ_RE = re.compile(
    r"^\w{6,}(?:ige|igen|iges|iger|liche|lichen|liches|licher|"
    r"ische|ischen|isches|ischer)$", re.I)


def flag_bare_head(requirements: pd.DataFrame) -> pd.DataFrame:
    """Mark atoms that lost the complement carrying their meaning.

    A third extraction-damage axis, independent of the two in
    ``flag_extraction_risk``: those mark atoms holding *too much*, this marks
    atoms left holding *too little*. Measured at 0.23% of the corpus, so it
    changes no headline — it matters because 55% of it lands in one cluster and
    inflates that cluster's size and its ``unassigned`` share.

    Carried as a flag rather than dropped, for the same reason the other two are:
    a published count can exclude it, and a reader can see what the exclusion
    cost. See ``week 2/risk_impact.py`` for why flagging beat dropping.
    """
    out = requirements.copy()
    norm = out["phrase_norm"].astype(str).str.lower().str.strip()
    single = out["phrase"].astype(str).str.split().str.len() == 1
    out["bare_head"] = single & (
        norm.isin(_RELATIONAL_HEADS)
        | norm.isin(_BARE_FILLER)
        | norm.str.match(_STRANDED_ADJ_RE).fillna(False)
    )
    return out


def flag_extraction_risk(requirements: pd.DataFrame) -> pd.DataFrame:
    """Mark the atoms whose extraction is least trustworthy.

    Two independent axes, because they threaten different Week 2 claims:

    ``from_long_segment`` — the atom came from a segment over
    ``LONG_SEGMENT_CHARS``, where recall is 58% against 83% for short ones. Long
    segments are 4.4% of software segments against 2.4% of sales, and range
    1.45%-8.45% across cells, so this error is **not** uniform. Core/shell works
    on lift between cells and only survives noise that hits cells equally, so
    every core/shell table needs recomputing on ``~from_long_segment`` as a
    sensitivity.

    ``looks_compound`` — the atom still reads as two requirements. Bears on the
    ESCO residual and therefore on Hypothesis 2; see the note above.
    """
    out = requirements.copy()
    out["looks_compound"] = (
        out["phrase"].str.contains(_STILL_COMPOUND_RE, na=False)
        | (out["phrase"].str.len() > config.LONG_SEGMENT_CHARS)
    )
    return out


def extraction_exposure(requirements: pd.DataFrame) -> pd.DataFrame:
    """Per cell: how much of its requirement mass is at risk, and from what.

    Reported beside every core/shell table so a reader can see which cells had
    more mass exposed to extraction error, rather than having to assume the
    error was spread evenly.
    """
    g = requirements.groupby(["macro_function", "company_industry"])
    out = g.agg(
        atoms=("phrase", "size"),
        from_long_pct=("from_long_segment", lambda x: round(x.mean() * 100, 2)),
        compound_pct=("looks_compound", lambda x: round(x.mean() * 100, 2)),
    ).reset_index()
    return out.sort_values("from_long_pct", ascending=False)


def build_requirement_table(df: pd.DataFrame) -> pd.DataFrame:
    """Explode postings into one row per requirement atom.

    Each atom records the segment it came from and whether that segment was
    long, because extraction quality differs sharply between the two and the
    difference is not spread evenly across cells.
    """
    records = []
    for row in df.itertuples(index=False):
        for seg in atom.segments(row.must_have):
            long_seg = len(seg) > config.LONG_SEGMENT_CHARS
            for phrase in atom.atomise(seg):
                records.append(
                    {
                        "vacancy_id": row.vacancy_id,
                        "macro_function": row.macro_function,
                        "company": row.company,
                        "company_industry": row.company_industry,
                        "geo_country": row.geo_country,
                        "language": row.language,
                        "phrase": phrase,
                        "from_long_segment": long_seg,
                    }
                )
    out = pd.DataFrame(records)
    out["phrase_norm"] = out["phrase"].map(atom.normalise)
    return flag_extraction_risk(out)


def atomisation_stats(df: pd.DataFrame, requirements: pd.DataFrame) -> dict:
    """How much splitting happened, and what it cost."""
    segments, split_segments = 0, 0
    for must_have in df["must_have"]:
        for seg in atom.segments(must_have):
            segments += 1
            if len(atom.atomise(seg)) > 1:
                split_segments += 1

    pre_unique = {
        atom.normalise(s) for must_have in df["must_have"] for s in atom.segments(must_have)
    }
    lengths = requirements["phrase"].str.len()
    return {
        "segments_in": segments,
        "segments_split": split_segments,
        "segments_split_pct": round(split_segments / segments * 100, 1),
        "atoms_out": len(requirements),
        "expansion_pct": round((len(requirements) - segments) / segments * 100, 1),
        "atoms_per_posting": round(len(requirements) / len(df), 1),
        "median_atom_chars": int(lengths.median()),
        "unique_before_split": len(pre_unique),
        "unique_after_split": requirements["phrase_norm"].nunique(),
    }


def classify_requirements(requirements: pd.DataFrame, hybrid: bool = False,
                          embeddings_path=None) -> pd.DataFrame:
    """Attach a requirement type, classifying each unique phrase once.

    ``hybrid=False`` runs the lexicon alone: ~8 ordered regular expressions,
    deterministic, free, and **0.927 accurate on what it assigns** — but it
    assigns only 53% of the corpus, because it recognises vocabulary and half of
    these requirements describe rather than name.

    ``hybrid=True`` adds the prototype layer (``classify_embed``), which needs
    the corpus embeddings. Coverage goes to **92.6%** and `unassigned` falls from
    46.9% to 7.4%, at 0.754 accuracy on what it assigns.

    ⚠️ **Neither is the right default for every question, so both are reported.**
    The choice is a genuine trade: the lexicon is more accurate on a minority,
    the hybrid characterises nearly everything at a stated error rate. For any
    statement *about* a type — "how much domain knowledge does sales carry" —
    the lexicon's 47% hole is disqualifying and the hybrid is the honest choice.
    For a claim that rests on a type being *right*, the lexicon's precision
    matters more. Week 2's published tables used the lexicon, which is why
    `untyped` came out as half of each family's ESCO residual; recomputed on the
    hybrid that falls to 10%. See ``week 2/hybrid_corpus.py``.

    ⚠️ **`domain` carries the weakest evidence either way** — 0.400 precision on
    the labelled sample — and the hybrid nearly triples its measured mass
    (3.98% to 11.48%). Hypothesis 2 turns on that type, so the increase must be
    published with the precision figure beside it, not on its own.
    """
    out = requirements.copy()
    lookup = {p: clf.classify(p) for p in out["phrase_norm"].unique()}
    out["req_type"] = out["phrase_norm"].map(lookup).fillna("unassigned")
    if not hybrid:
        return out

    import numpy as np

    from . import classify_embed as ce
    from . import embed as emb

    path = embeddings_path or (config.REPO_ROOT / "week 1" / "output" / "embeddings.npz")
    phrases, vecs = emb.load_corpus(path)
    store = {p: i for i, p in enumerate(phrases)}
    uniq = out["phrase_norm"].astype(str).unique()
    known = np.array([p in store for p in uniq])

    model = emb.load_model()
    types, centroids = ce.fit_prototypes(model)
    predicted, _, _ = ce.classify_vectors(
        vecs[np.array([store[p] for p in uniq[known]])], types, centroids)

    merged = dict(zip(uniq[~known], (lookup.get(p) for p in uniq[~known])))
    for phrase, guess in zip(uniq[known], predicted):
        hit = lookup.get(phrase)
        merged[phrase] = hit if hit in ce.LEXICON_PRECEDENCE else (
            guess if guess is not None else hit)
    out["req_type_hybrid"] = out["phrase_norm"].astype(str).map(merged).fillna("unassigned")
    return out


def type_distribution(requirements: pd.DataFrame) -> pd.DataFrame:
    """Unique phrases and total occurrences per requirement type."""
    occ = requirements["req_type"].value_counts()
    uniq = requirements.groupby("req_type")["phrase_norm"].nunique()
    out = pd.DataFrame({"unique_phrases": uniq, "occurrences": occ})
    out["unique_pct"] = (out["unique_phrases"] / out["unique_phrases"].sum() * 100).round(1)
    out["occurrence_pct"] = (out["occurrences"] / out["occurrences"].sum() * 100).round(1)
    return out.sort_values("occurrences", ascending=False)


def type_mix_by_function(requirements: pd.DataFrame) -> pd.DataFrame:
    """Requirement type mix, per function, as shares of occurrences."""
    mix = pd.crosstab(requirements["req_type"], requirements["macro_function"], normalize="columns")
    return (mix * 100).round(1)


def with_sensitivity(requirements: pd.DataFrame, estimate, axis: str = "from_long_segment"):
    """Run an estimate on all atoms and on the trustworthy subset, and diff them.

    ``estimate`` is any function taking the requirement table and returning a
    DataFrame — a core/shell table, a type mix, a variance index. It is called
    twice and the two results are returned with their difference, so a claim can
    be reported with its sensitivity rather than needing a separate pass.

    Which axis to hold out depends on the claim:

    * ``from_long_segment`` for anything comparing cells — core/shell, lift, the
      variance index — because long-segment exposure runs 1.45% to 8.45% across
      cells and 4.4% vs 2.4% between functions, so this error does not cancel.
    * ``looks_compound`` for the ESCO residual and Hypothesis 2, where a
      still-merged atom has no anchor by construction and inflates the residual
      whatever the taxonomy contains.

    If the two results agree, the shortfall did not drive the finding and that
    is worth stating. If they disagree, the difference IS the finding and
    publishing only the first number would be wrong.
    """
    if axis not in requirements.columns:
        raise ValueError(f"{axis!r} not on the table; call flag_extraction_risk first")

    full = estimate(requirements)
    clean = estimate(requirements[~requirements[axis]])
    try:
        delta = (full - clean).round(2)
    except Exception:
        delta = None
    return {"all_atoms": full, "excluding_" + axis: clean, "difference": delta,
            "n_all": len(requirements), "n_clean": int((~requirements[axis]).sum()),
            "share_held_out": round(float(requirements[axis].mean()), 4)}


def top_phrases(requirements: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    counts = requirements["phrase_norm"].value_counts().head(n)
    types = requirements.drop_duplicates("phrase_norm").set_index("phrase_norm")["req_type"]
    return pd.DataFrame({"phrase": counts.index, "occurrences": counts.values,
                         "type": [types.get(p, "unassigned") for p in counts.index]})
