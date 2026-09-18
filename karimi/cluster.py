"""Clustering the requirement space, with centroids that survive a refresh.

The design constraint that shapes this module is not clustering quality, it is
**comparability over time**. A monthly product needs "requirements entering and
leaving the core" to mean something, and re-clustering each month would make
every such statement an artefact of the new fit. So the structure is learned
once on a reference period and everything afterwards is *assigned* to it.

That forces one decision that is easy to get wrong: the centroids are stored in
the **original 384-dimensional embedding space**, not in UMAP coordinates. UMAP
is stochastic and its `transform` depends on the fitted manifold, so centroids
living in UMAP space would make next month's assignment depend on this month's
random seed. Assignment is therefore a cosine comparison in the space the
embedding model actually produced, and a refresh never needs UMAP again.

UMAP is fitted on a sample rather than the full vocabulary. With ~180k
reference phrases the full fit costs far more than it improves the manifold,
and `transform` extends it to the rest — a standard trade, recorded here so the
sample size is visible rather than buried.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config

# Reference period. May-July 2026 are complete months; August is partial (3,894
# postings against July's 9,892) and is deliberately excluded from the fit so
# that it can serve as the first "new data assigned to existing centroids"
# test — which is the operation every future refresh performs.
REFERENCE_MONTHS = ("2026-05", "2026-06", "2026-07")

# Assignment threshold. A phrase further than this from every centroid is left
# unassigned rather than forced into the nearest cluster: HDBSCAN allows noise
# and the assignment step must too, or the noise class silently disappears the
# moment new data arrives.
MIN_ASSIGN_COSINE = 0.55

UMAP_FIT_SAMPLE = 60_000
UMAP_COMPONENTS = 10
UMAP_NEIGHBOURS = 25
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 40
HDBSCAN_MIN_SAMPLES = 8
RANDOM_STATE = 20260906


def reference_phrases(reqs: pd.DataFrame, base: pd.DataFrame) -> set[str]:
    """The unique phrases appearing in reference-period postings."""
    months = base["created_at"].dt.to_period("M").astype(str)
    ref_ids = set(base.loc[months.isin(REFERENCE_MONTHS), "vacancy_id"])
    return set(reqs.loc[reqs["vacancy_id"].isin(ref_ids), "phrase_norm"].dropna())


def fit_reference(phrases: list[str], vectors: np.ndarray, ref: set[str]) -> dict:
    """Learn the cluster structure on the reference period only.

    Returns the centroids in embedding space plus the labels of the reference
    phrases, so the fit can be inspected before anything is assigned to it.
    """
    import umap
    from sklearn.cluster import HDBSCAN

    idx = [i for i, p in enumerate(phrases) if p in ref]
    ref_vecs = vectors[idx]
    ref_names = [phrases[i] for i in idx]

    unit = ref_vecs / np.clip(np.linalg.norm(ref_vecs, axis=1, keepdims=True), 1e-12, None)

    rng = np.random.default_rng(RANDOM_STATE)
    sample = rng.choice(len(unit), size=min(UMAP_FIT_SAMPLE, len(unit)), replace=False)
    reducer = umap.UMAP(
        n_components=UMAP_COMPONENTS, n_neighbors=UMAP_NEIGHBOURS,
        min_dist=UMAP_MIN_DIST, metric="cosine", random_state=RANDOM_STATE,
    ).fit(unit[sample])
    reduced = reducer.transform(unit)

    labels = HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=HDBSCAN_MIN_SAMPLES,
    ).fit_predict(reduced)

    # Centroids in the ORIGINAL space — see the module docstring for why.
    centroids, ids = [], []
    for cid in sorted(set(labels) - {-1}):
        c = unit[labels == cid].mean(axis=0)
        n = np.linalg.norm(c)
        if n < 1e-9:
            continue
        centroids.append(c / n)
        ids.append(int(cid))

    return {
        "cluster_ids": ids,
        "centroids": np.vstack(centroids) if centroids else np.zeros((0, unit.shape[1])),
        "reference_labels": pd.Series(labels, index=ref_names, name="cluster"),
        "n_reference_phrases": len(ref_names),
        "n_clusters": len(ids),
        "noise_share": float((labels == -1).mean()),
        "umap_fit_sample": int(len(sample)),
    }


def assign(phrases: list[str], vectors: np.ndarray, fit: dict) -> pd.DataFrame:
    """Assign every phrase to its nearest reference centroid, or to noise.

    One cosine comparison per phrase against a few hundred centroids — cheap,
    deterministic, and independent of UMAP, which is what makes a monthly
    refresh comparable to this one.
    """
    if fit["centroids"].shape[0] == 0:
        raise ValueError("no centroids to assign to")

    unit = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    sims = unit @ fit["centroids"].T
    best = sims.argmax(axis=1)
    score = sims[np.arange(len(sims)), best]

    ids = np.array(fit["cluster_ids"])
    cluster = np.where(score >= MIN_ASSIGN_COSINE, ids[best], -1)
    return pd.DataFrame({"phrase_norm": phrases, "cluster": cluster,
                         "similarity": score.round(4)})


def cluster_dictionary(assigned: pd.DataFrame, reqs: pd.DataFrame,
                       top_terms: int = 6) -> pd.DataFrame:
    """One row per cluster: size, occurrences, exposure and candidate terms.

    Candidate terms come from c-TF-IDF over cluster members — term frequency
    within the cluster against its frequency across all clusters — which is
    what the procedure specifies for labelling. The two Week 1 risk flags are
    carried through so a cluster built mostly from untrustworthy atoms is
    visible rather than having to be discovered later.

    ``candidate_terms`` holds single *words*, which is a standing source of
    confusion: it is the naming step's input and a diagnostic, never the
    cluster's contents. The contents are phrases averaging 5.1 words.
    ``mean_words`` is printed beside it so the two are not mistaken for each
    other, and because a cluster of one-word atoms behaves differently from a
    cluster of phrases — one-word atoms carry little context, so they group by
    shape rather than by meaning. Cluster 615 is the worked example.

    ⚠️ ``mean_words`` is a weak detector on its own and should not be used as
    a filter. Measured: of the 7 clusters below 2.5 words, only one carries any
    bare-head damage at all (615, at 6.5%); the other six — `Autonomy`,
    `Flexibility`, `Structured working style` — are 0.0% damage and perfectly
    coherent, because bare attributes are how those requirements are genuinely
    written. Read it with ``bare_head_pct``, which measures the damage directly.
    """
    joined = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    joined["cluster"] = joined["cluster"].fillna(-1).astype(int)
    joined["_n_words"] = joined["phrase"].astype(str).str.split().str.len()
    if "bare_head" not in joined.columns:
        from .requirements import flag_bare_head
        joined = flag_bare_head(joined)

    counts = {}
    for cid, sub in joined.groupby("cluster"):
        words = sub["phrase_norm"].str.split().explode()
        counts[cid] = words.value_counts()
    overall = pd.concat(counts.values()).groupby(level=0).sum()

    rows = []
    for cid, sub in joined.groupby("cluster"):
        tf = counts[cid]
        ctfidf = (tf / tf.sum()) * np.log(1 + overall.sum() / overall.reindex(tf.index).fillna(1))
        terms = ", ".join(ctfidf.sort_values(ascending=False).head(top_terms).index)
        rows.append({
            "cluster": cid,
            "unique_phrases": sub["phrase_norm"].nunique(),
            "occurrences": len(sub),
            "postings": sub["vacancy_id"].nunique(),
            "from_long_pct": round(float(sub["from_long_segment"].mean()) * 100, 1),
            "compound_pct": round(float(sub["looks_compound"].mean()) * 100, 1),
            "mean_words": round(float(sub["_n_words"].mean()), 2),
            "pct_single_word": round(float((sub["_n_words"] == 1).mean()) * 100, 1),
            "bare_head_pct": round(float(sub["bare_head"].mean()) * 100, 1),
            "top_type": sub["req_type"].mode().iat[0] if len(sub) else "",
            "candidate_terms": terms,
        })
    out = pd.DataFrame(rows).sort_values("occurrences", ascending=False)
    return out.reset_index(drop=True)


def language_shape(assigned: pd.DataFrame, reqs: pd.DataFrame) -> pd.DataFrame:
    """Per cluster, the share held by its most common language.

    Week 1 measured that 52.6% of a phrase's nearest neighbours share its
    language, three to seven times chance for the smaller ones. A cluster that
    is overwhelmingly one language is a candidate artefact of that effect
    rather than a requirement grouping, and must be checked before it is named.
    """
    joined = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    joined["cluster"] = joined["cluster"].fillna(-1).astype(int)
    col = "text_language" if "text_language" in joined.columns else "language"
    joined[col] = joined[col].replace("", "(unknown)").fillna("(unknown)")

    rows = []
    for cid, sub in joined.groupby("cluster"):
        if cid == -1:
            continue
        share = sub[col].value_counts(normalize=True)
        rows.append({"cluster": cid, "occurrences": len(sub),
                     "top_language": share.index[0],
                     "top_language_pct": round(float(share.iloc[0]) * 100, 1)})
    out = pd.DataFrame(rows)
    return out.sort_values("top_language_pct", ascending=False).reset_index(drop=True)


# --- boilerplate -------------------------------------------------------------
#
# `Team player`, `excellent communication skills`, `problem solving` appear
# everywhere and would otherwise form enormous uninformative clusters that
# dominate the structure. The procedure says to separate them; the question is
# by what rule.
#
# Defining boilerplate by SIZE would be wrong — `cloud / aws / azure` is large
# and highly informative. Boilerplate is instead the measurable **opposite of
# shell**: shell is a cluster whose share is elevated in one context, so
# boilerplate is a cluster whose share is high and *flat* across every context.
# Both are read off the same per-cell share table, which keeps the two
# definitions consistent by construction rather than by intention.
BOILERPLATE_MIN_MEAN_SHARE = 0.10   # requested by 10%+ of postings on average
BOILERPLATE_MAX_CV = 0.60           # and varying little between cells


def cell_shares(assigned: pd.DataFrame, reqs: pd.DataFrame,
                paired_only: bool = False) -> pd.DataFrame:
    """Share of postings in each cell that request each cluster.

    Postings, not atoms: a posting asking for `Python` three ways should count
    once, or a verbose employer outvotes a terse one.
    """
    joined = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    joined["cluster"] = joined["cluster"].fillna(-1).astype(int)
    if paired_only:
        joined = joined[joined["company_industry"].isin(config.PAIRED_INDUSTRIES)]

    postings = (joined.groupby(["macro_function", "company_industry"])["vacancy_id"]
                .nunique().rename("cell_postings"))
    hits = (joined.groupby(["macro_function", "company_industry", "cluster"])["vacancy_id"]
            .nunique().rename("postings_with"))
    out = hits.reset_index().merge(postings.reset_index(),
                                   on=["macro_function", "company_industry"])
    out["share"] = out["postings_with"] / out["cell_postings"]
    return out


def classify_boilerplate(shares: pd.DataFrame) -> pd.DataFrame:
    """Split clusters into boilerplate and informative, by flatness not size.

    ``cv`` is the coefficient of variation of a cluster's share across cells.
    High mean share with low cv means "asked for everywhere, equally" — which
    carries no information about context and would swamp the core/shell tables.
    """
    g = shares[shares["cluster"] != -1].groupby("cluster")["share"]
    out = g.agg(mean_share="mean", min_share="min", max_share="max", std="std").reset_index()
    out["cv"] = (out["std"] / out["mean_share"]).fillna(0)
    out["boilerplate"] = ((out["mean_share"] >= BOILERPLATE_MIN_MEAN_SHARE)
                          & (out["cv"] <= BOILERPLATE_MAX_CV))
    return out.sort_values("mean_share", ascending=False).reset_index(drop=True)


# --- core and shell ----------------------------------------------------------
#
# Core = requested at a high rate and at the SAME rate everywhere: it travels
# with the role. Shell = requested far more in one context than the function's
# own baseline: it belongs to that context. Both fall out of one quantity, the
# lift of a cluster's share in a cell against its share across the function.
#
# Lift, not raw share, is what separates them — and lift is a ratio of two
# estimates, so it is unstable when either is small. `MIN_CELL_POSTINGS_FOR_LIFT`
# keeps a cluster requested by four postings in a small cell from reporting a
# lift of 8 and being read as the strongest shell finding in the study.
CORE_MIN_SHARE = 0.05
CORE_MAX_LIFT_DEVIATION = 0.35
SHELL_MIN_LIFT = 1.75
SHELL_MIN_SHARE = 0.03
MIN_CELL_POSTINGS_FOR_LIFT = 20


def core_shell(assigned: pd.DataFrame, reqs: pd.DataFrame,
               boilerplate: set[int] | None = None,
               paired_only: bool = True) -> pd.DataFrame:
    """Lift per cluster per cell, and the core/shell verdict.

    Restricted to `config.PAIRED_INDUSTRIES` by default: a between-function
    comparison needs both cells present in the same industry, and Think Tank
    contributes a software cell with no sales counterpart.

    Boilerplate clusters are excluded from the verdict but kept in the table
    with `boilerplate=True`, because they are the extreme end of the core and
    dropping them silently would overstate how much informative core there is.
    """
    boilerplate = boilerplate or set()
    shares = cell_shares(assigned, reqs, paired_only=paired_only)
    shares = shares[shares["cluster"] != -1]

    joined = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    joined["cluster"] = joined["cluster"].fillna(-1).astype(int)
    if paired_only:
        joined = joined[joined["company_industry"].isin(config.PAIRED_INDUSTRIES)]

    fn_postings = joined.groupby("macro_function")["vacancy_id"].nunique()
    fn_hits = joined.groupby(["macro_function", "cluster"])["vacancy_id"].nunique()
    baseline = (fn_hits / fn_postings).rename("function_share").reset_index()

    out = shares.merge(baseline, on=["macro_function", "cluster"], how="left")
    out["lift"] = out["share"] / out["function_share"].replace(0, np.nan)
    out["boilerplate"] = out["cluster"].isin(boilerplate)
    out["reliable"] = out["postings_with"] >= MIN_CELL_POSTINGS_FOR_LIFT

    out["verdict"] = "neither"
    core = (out["share"] >= CORE_MIN_SHARE) & (out["lift"].sub(1).abs() <= CORE_MAX_LIFT_DEVIATION)
    shell = (out["lift"] >= SHELL_MIN_LIFT) & (out["share"] >= SHELL_MIN_SHARE) & out["reliable"]
    out.loc[core & ~out["boilerplate"], "verdict"] = "core"
    out.loc[shell & ~out["boilerplate"], "verdict"] = "shell"
    return out


def core_shell_summary(cs: pd.DataFrame) -> pd.DataFrame:
    """Per cell: how many clusters are core, how many shell, and the top shell.

    The count is the headline for Hypothesis 1 — a thick shell means many
    clusters elevated in that context — and the named example is what makes it
    readable rather than abstract.
    """
    rows = []
    for (fn, ind), sub in cs.groupby(["macro_function", "company_industry"]):
        shell = sub[sub["verdict"] == "shell"].nlargest(1, "lift")
        rows.append({
            "macro_function": fn, "company_industry": ind,
            "clusters_present": int((sub["postings_with"] > 0).sum()),
            "n_core": int((sub["verdict"] == "core").sum()),
            "n_shell": int((sub["verdict"] == "shell").sum()),
            "top_shell_cluster": int(shell["cluster"].iat[0]) if len(shell) else None,
            "top_shell_lift": round(float(shell["lift"].iat[0]), 2) if len(shell) else None,
        })
    return pd.DataFrame(rows).sort_values(["macro_function", "n_shell"], ascending=[True, False])


# --- merging fragmented groups ----------------------------------------------
#
# HDBSCAN splits one technology across several groups whenever employers write it
# several ways: `SQL knowledge`, `SQL skills` and `SQL and databases` are three
# groups describing one demand, and `Python` is five. Measured on the 2026-09
# corpus, **43.8% of groups have a near-duplicate at cosine 0.80, carrying 61.0%
# of requirement mass** — so this is the normal condition of the structure, not
# an edge case.
#
# It matters unevenly, which is worse than mattering uniformly. Python's demand is
# understated 57% by any single group while Java's is understated 0%, because Java
# happens to have one group. **Any comparison between two technologies built on
# single groups is therefore invalid rather than merely low.**
#
# ⚠️ Merging on centroid distance alone does NOT work, and the failure is the same
# one that defeated three other attempts in this project: cosine cannot separate
# "same thing, different wording" from "different things, same topic". At 0.85 it
# merges `Microsoft Office` with `Microsoft Azure` and `Languages` with
# `Programming languages proficiency`; at 0.70 a single component swallows 457 of
# 617 groups. A lexical constraint on top of the geometry is what makes it safe.

# Tokens that describe rather than name. A shared token from this set is not
# evidence that two groups are the same thing — `microsoft` is here because it is
# what merged Office with Azure.
GENERIC_LABEL_TOKENS = frozenset("""
experience experiences knowledge skills skill proficiency expertise
understanding familiarity background degree diploma qualification certification
management managing developer development engineering engineer technical
technology technologies tools tool systems system platform platforms software
and or the of in with a an for to strong good excellent solid advanced basic
relevant professional practical hands-on hands on work working ability abilities
communication team teams leadership interpersonal collaboration mindset
attitude thinking orientation focus oriented driven learning
microsoft google amazon apache oracle ibm sap adobe
data business commercial general senior junior level years
""".split())

MERGE_MIN_COSINE = 0.80
MERGE_MAX_COMPONENT = 12          # a larger component means the rule is chaining


def _label_names(label: str) -> set[str]:
    """The specific tokens in a label — the ones that name rather than describe."""
    toks = re.findall(r"[a-z0-9#+./]+", str(label).lower())
    return {t for t in toks if t not in GENERIC_LABEL_TOKENS
            and (len(t) > 2 or t in {"go", "r", "c#", "ai"})}


# Words every requirement is written out of, whatever it is about. Stripped
# before comparing two groups' member vocabulary, or the comparison measures
# phrasing rather than content.
MEMBER_STOP = frozenset("""
a an the of in with and or to for on at as is are be by from your you we our
experience experiences knowledge skills skill proficiency expertise strong good
excellent solid advanced basic relevant professional practical hands working work
ability abilities understanding familiarity years year plus minimum
erfahrung kenntnisse gute sehr sowie mit der die das und oder im von zu
expérience connaissance connaissances bonne maîtrise des du de la le les en
esperienza conoscenza buona ottima con del della di il lo
""".split())

MEMBER_TOP_WORDS = 25       # the words that characterise a group, not its tail
MEMBER_MIN_OVERLAP = 0.10   # validated in the merge_aliases docstring


def member_vocabulary(assigned, reqs, top: int = MEMBER_TOP_WORDS):
    """The content words characterising each group — the third sameness signal.

    Independent of both the embedding and the LLM naming step, because it reads
    the members' own text. That independence is the point: two signals that fail
    together are one signal, which is the mistake made earlier in this project
    when a label was typed with the same classifier it was being checked against.
    """
    j = reqs.merge(assigned[["phrase_norm", "cluster"]], on="phrase_norm", how="left")
    j["cluster"] = j["cluster"].fillna(-1).astype(int)
    out = {}
    for cid, sub in j[j["cluster"] != -1].groupby("cluster"):
        counts = {}
        for phrase in sub["phrase_norm"].astype(str):
            for w in re.findall(r"[a-z0-9#+.]{3,}", phrase.lower()):
                if w not in MEMBER_STOP:
                    counts[w] = counts.get(w, 0) + 1
        out[int(cid)] = set(sorted(counts, key=counts.get, reverse=True)[:top])
    return out


def merge_aliases(named: pd.DataFrame, cluster_ids, centroids: np.ndarray,
                  min_cosine: float = MERGE_MIN_COSINE,
                  vocab=None, min_overlap: float = MEMBER_MIN_OVERLAP) -> dict:
    """Group-level alias map, rebuilt from labels so it survives a refit.

    **This must be recomputed after every clustering run.** An alias table stored
    as cluster ids is worthless the moment the clusters are refitted, because the
    ids are assigned afresh; the *rule* is what carries over, not its output.
    Call this after the naming step and apply the result before any per-technology
    figure is published.

    **The method, and its validated boundary.** Centroid distance is a gate, never
    a verdict — on its own it merges `Microsoft Office` with `Microsoft Azure`.
    Past the gate a merge needs one of three pieces of positive evidence:

    1. the labels are **identical** — two groups the naming step named the same;
    2. the labels **share a specific name**, a token that identifies rather than
       describes;
    3. ``vocab`` is supplied and the two groups' **member vocabularies overlap**
       at ``min_overlap``.

    Signal 3 reads the members' own words, so it is independent of the embedding
    *and* of the LLM that wrote the labels. Validated against pairs whose answer
    is known: it catches **89.5%** of name-rule merges while firing on **3.3%**
    of random pairs — separation 0.862 — and it correctly refuses
    `Microsoft Azure` + `Microsoft Office` (0.087) and `Prompt engineering` +
    `Engineering degree` (0.064).

    ⚠️ **Known blind spot: credentials, and it was measured rather than assumed.**
    All three signals fail on degree groups. Every degree is written out of the
    same frame, so member overlap fires across the whole family and would merge
    `Computer Science degree` with `Electronics degree`. Stripping the frame
    words does not rescue it — **31 of 33 credential pairs still merge**. Leave
    ``vocab=None`` (the default) to keep credentials out, or resolve that family
    with LLM adjudication: that is what rescued ESCO anchoring when cosine failed
    there, and it is the only tool left for this case.

    Everything unresolved is returned in ``rejected`` for a person rather than
    silently dropped — 179 pairs on the 2026-09 corpus, carrying 34.6% of
    requirement mass, and they are genuinely fragmented too.
    """
    lab = dict(zip(named["cluster"], named["label"]))
    occ = dict(zip(named["cluster"], named.get("occurrences", pd.Series(dtype=int))))
    ids = np.asarray(cluster_ids)
    unit = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12, None)
    sims = unit @ unit.T
    np.fill_diagonal(sims, -1.0)

    parent = list(range(len(ids)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    accepted, rejected = [], []
    ii, jj = np.where(np.triu(sims >= min_cosine, k=1))
    for a, b in zip(ii, jj):
        ca, cb = int(ids[a]), int(ids[b])
        la, lb = str(lab.get(ca, "")), str(lab.get(cb, ""))
        shared = _label_names(la) & _label_names(lb)
        same_label = la.strip().lower() == lb.strip().lower() and la.strip() != ""
        ov = 0.0
        if vocab is not None:
            va, vb = vocab.get(ca, set()), vocab.get(cb, set())
            ov = len(va & vb) / len(va | vb) if va and vb else 0.0
        if shared or same_label or ov >= min_overlap:
            why = ("identical label" if same_label
                   else ", ".join(sorted(shared)) if shared
                   else "member overlap %.2f" % ov)
            accepted.append({"a": ca, "b": cb, "cosine": round(float(sims[a, b]), 3),
                             "overlap": round(ov, 3), "why": why})
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        else:
            rejected.append({"a": ca, "b": cb, "cosine": round(float(sims[a, b]), 3),
                             "overlap": round(ov, 3), "label_a": la, "label_b": lb})

    comp: dict[int, list[int]] = {}
    for i in range(len(ids)):
        comp.setdefault(find(i), []).append(int(ids[i]))
    families = [c for c in comp.values() if len(c) > 1]

    largest = max((len(c) for c in families), default=0)
    if largest > MERGE_MAX_COMPONENT:
        raise ValueError(
            f"single linkage produced a component of {largest} groups, above "
            f"MERGE_MAX_COMPONENT={MERGE_MAX_COMPONENT}. The rule is chaining "
            f"unrelated groups; inspect before lowering the guard.")

    alias = {}
    for c in families:
        keep = max(c, key=lambda x: occ.get(x, 0))
        for x in c:
            alias[x] = keep
    return {
        "alias": alias,
        "families": families,
        "accepted": pd.DataFrame(accepted),
        "rejected": pd.DataFrame(rejected),
        "n_groups_before": len(ids),
        "n_groups_after": len(ids) - sum(len(c) for c in families) + len(families),
        "largest_family": largest,
    }


def apply_aliases(assigned: pd.DataFrame, alias: dict) -> pd.DataFrame:
    """Rewrite cluster ids through the alias map. Unmapped ids pass through."""
    out = assigned.copy()
    out["cluster"] = out["cluster"].map(lambda c: alias.get(c, c))
    return out
