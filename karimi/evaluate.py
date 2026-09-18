"""Validation: drawing the sample, and scoring it once it is labelled.

The design constraint that shapes this module: **the person who wrote the rules
cannot be the person who labels the sample.** Their labels inherit the same
assumptions the rules encode, so agreement would measure consistency rather than
correctness, and every systematic error would validate itself.

So this module does not label anything. It draws a stratified sample, writes a
sheet containing the raw text and nothing else — no predicted split, no predicted
type — and scores that sheet once a human has filled it in. The pipeline's own
output is never written to the sheet and is only joined back at scoring time.

Two samples, because the two claims are different:

* **atomisation** is a claim about *segments* — was this split correctly;
* **classification** is a claim about *atoms* — is this the right type.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import atomise as atom
from . import config

# --- development / held-out split --------------------------------------------

# Splitting the labelled set is not optional once the extractor is being fixed
# against it. Tuning a rule until it satisfies a row and then reporting accuracy
# on that same row measures memorisation, not extraction, and the gate would
# certify nothing. So the labelled rows are partitioned once, deterministically:
# rules may be developed against DEV and the gate is read off HOLDOUT.
#
# The split is stratified on the two axes that failure tracks — language, and
# whether the segment is long — so a rule that only works on short English text
# cannot hide in a lucky partition.
DEV_HOLDOUT_SEED = 20260903
DEV_FRACTION = 0.5


def dev_holdout_split(labelled: pd.DataFrame, text_col: str = "segment") -> pd.DataFrame:
    """Add a ``split`` column with values ``dev`` and ``holdout``.

    Deterministic in the seed, so the partition is identical across runs and a
    holdout score cannot drift by re-drawing. Stratified on language x length.
    """
    d = labelled.copy()
    lang = d["language"].fillna("(unknown)") if "language" in d.columns else "(unknown)"
    if text_col in d.columns:
        is_long = d[text_col].astype(str).str.len() > config.LONG_SEGMENT_CHARS
    else:
        is_long = False
    d["_stratum"] = pd.Series(lang, index=d.index).astype(str) + "|" + pd.Series(is_long, index=d.index).astype(str)

    rng = np.random.default_rng(DEV_HOLDOUT_SEED)
    d["split"] = "holdout"
    for _, idx in d.groupby("_stratum").groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        n_dev = int(round(len(idx) * DEV_FRACTION))
        d.loc[idx[:n_dev], "split"] = "dev"
    return d.drop(columns="_stratum")


SHEET_INSTRUCTIONS_ATOMISATION = (
    "Write the requirements you can see in the segment, ONE PER LINE, separated by ' | '. "
    "Split only where genuinely separate things are being asked for. "
    "'Both written and verbal communication' is ONE requirement. "
    "'Experience with Python and SQL' is TWO. Do not look at the pipeline output first."
)

SHEET_INSTRUCTIONS_CLASSIFICATION = (
    "Assign exactly one type: technical / soft / domain / credential / language / availability. "
    "technical = a nameable tool, technology or technical activity. "
    "soft = a disposition or interpersonal quality. "
    "domain = knowledge of an industry, market or regulation. "
    "credential = a degree, certification or licence. "
    "language = a natural-language requirement. "
    "availability = travel, shifts, location or contract conditions."
)


def _strata(df: pd.DataFrame) -> pd.Series:
    """Language x function. Missing language is its own stratum, not a deletion.

    `language` is empty for about 16% of postings. Dropping those rows would
    make the sample unrepresentative of exactly the part of the corpus whose
    provenance is least certain, so they are sampled as `(unknown)`.

    Prefers ``text_language`` where it is present. `language` describes the
    original advertisement, and 10.9% of postings carry requirement text in a
    different language — so stratifying on it stratifies on the language of a
    document the labeller never sees. See ``karimi/language.py``.
    """
    col = "text_language" if "text_language" in df.columns else "language"
    lang = df[col].replace("", "(unknown)").fillna("(unknown)")
    return lang + " / " + df["macro_function"]


def draw_classification_sample_by_type(
    reqs: pd.DataFrame,
    n: int = 180,
    seed: int = 20260903,
    per_type_floor: int = 20,
) -> pd.DataFrame:
    """Sample atoms with a floor per predicted type, then spread by language.

    Replaces proportional sampling for the classification sheet, because
    proportional sampling cannot validate a rare type. `availability` is 0.9% of
    occurrences, so a 150-row proportional draw expects 1.4 of them and the
    first round got **zero** — one of the six types was never tested at all.

    The floor is applied to the *predicted* type, which is a sampling decision
    and not a label: the labeller still sees only raw text, and if the predictor
    is wrong about a row that is precisely what the sheet is meant to catch.

    The cost is that the sample is no longer corpus-representative, so
    ``sampling_weight`` is carried on every row. Per-type accuracy is read
    directly; any corpus-level figure must be reweighted by it, or it will
    overstate the rare types. Scoring reports both.
    """
    pool = reqs.copy()
    if "req_type" not in pool.columns:
        raise ValueError("classify the requirement table before sampling by type")
    pool["pred_type"] = pool["req_type"].fillna("unassigned")
    pool["stratum"] = _strata(pool)

    rng = np.random.default_rng(seed)
    groups = list(config.REQUIREMENT_TYPES) + ["unassigned"]

    # Floor first, so a rare type cannot be squeezed out by rounding.
    picks = []
    for t in groups:
        block = pool[pool["pred_type"] == t]
        if block.empty:
            continue
        take = min(per_type_floor, len(block))
        # Spread the floor across language strata rather than taking whichever
        # rows happen to sort first, so a type is not validated in one language.
        by_stratum = []
        for _, sub in block.groupby("stratum"):
            by_stratum.append(sub.sample(frac=1, random_state=seed))
        shuffled = pd.concat(by_stratum).sample(frac=1, random_state=seed)
        picks.append(shuffled.head(take))

    sample = pd.concat(picks, ignore_index=True) if picks else pool.head(0)
    sample = _top_up(sample, pool, n, seed)

    # What a row's selection probability was, relative to its type's share.
    type_share = pool["pred_type"].value_counts(normalize=True)
    drawn_share = sample["pred_type"].value_counts(normalize=True)
    sample["sampling_weight"] = sample["pred_type"].map(
        lambda t: float(type_share.get(t, 0.0) / drawn_share.get(t, 1.0))
    )
    return sample.sample(frac=1, random_state=seed).reset_index(drop=True)


def score_classification_split(labelled: pd.DataFrame, pred_col: str) -> dict:
    """Accuracy decomposed by whether the label's definition still stands.

    Reporting one pooled figure would conflate two different things: how well the
    classifier types requirements, and how far one class's definition has moved
    since its labels were written. The 31 `domain` labels describe a superseded
    specification, so scoring against them measures the revision.

    Coverage is returned beside every accuracy, because `on_assigned` can be
    raised by abstaining more and is not interpretable without it.
    """
    d = labelled.copy()
    d["true_type"] = d["true_type"].astype(str).str.strip().str.lower()
    d = d[d["true_type"].isin(config.REQUIREMENT_TYPES)]

    def block(sub: pd.DataFrame) -> dict:
        assigned = sub[sub[pred_col].notna()]
        ok = int((assigned[pred_col] == assigned["true_type"]).sum())
        return {
            "n": len(sub),
            "n_assigned": len(assigned),
            "coverage": round(len(assigned) / len(sub), 3) if len(sub) else 0.0,
            "on_assigned": round(ok / len(assigned), 3) if len(assigned) else 0.0,
            "overall": round(ok / len(sub), 3) if len(sub) else 0.0,
        }

    stable = d[d["true_type"].isin(config.DEFINITION_STABLE_TYPES)]
    changed = d[~d["true_type"].isin(config.DEFINITION_STABLE_TYPES)]

    out = {
        "all": block(d),
        "stable": block(stable),
        "changed": block(changed),
        "stable_types": list(config.DEFINITION_STABLE_TYPES),
    }
    if "split" in d.columns:
        out["stable_holdout"] = block(stable[stable["split"] == "holdout"])
        out["stable_dev"] = block(stable[stable["split"] == "dev"])

    per_type = []
    for t in config.REQUIREMENT_TYPES:
        sub = d[d["true_type"] == t]
        if sub.empty:
            per_type.append({"type": t, "n_true": 0, "correct": 0,
                             "recall": None, "definition_stable": t in config.DEFINITION_STABLE_TYPES})
            continue
        per_type.append({
            "type": t,
            "n_true": len(sub),
            "correct": int((sub[pred_col] == t).sum()),
            "recall": round(float((sub[pred_col] == t).mean()), 3),
            "definition_stable": t in config.DEFINITION_STABLE_TYPES,
        })
    out["per_type"] = pd.DataFrame(per_type)
    return out


def score_llm_routing(labelled: pd.DataFrame) -> dict:
    """How well does `atomise.needs_llm` find the segments the rules cannot do?

    The router's job is not to split but to decide where the expensive stage is
    spent, so it is scored as a detector against the labelled sample:

    * a **true positive** is a segment the human split into several requirements
      that the rules left whole — genuine work for the LLM;
    * a **false positive** is a single requirement sent to the LLM anyway, which
      wastes a call and risks an unnecessary rewrite;
    * a **false negative** is a compound segment left unsplit and *not* routed,
      which is requirement mass lost silently — the costliest error of the three.

    Recall matters more than precision here: a wasted call is cheap, and a
    missed requirement never appears in any table.
    """
    rows = []
    for r in labelled.itertuples(index=False):
        raw = r.true_requirements
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        truth = [t.strip() for t in str(raw).split("|") if t.strip()]
        if not truth:
            continue
        pieces, route = atom.route(r.segment)
        rows.append({
            "n_true": len(truth),
            "n_pred": len(pieces),
            "route": route,
            "truly_compound": len(truth) > 1,
            "rules_split": route == "rules",
            "routed": route == "llm",
            "is_long": len(r.segment) > config.LONG_SEGMENT_CHARS,
            "missed_mass": max(0, len(truth) - len(pieces)),
        })
    d = pd.DataFrame(rows)

    unsplit = d[~d["rules_split"]]
    tp = int((unsplit["truly_compound"] & unsplit["routed"]).sum())
    fp = int((~unsplit["truly_compound"] & unsplit["routed"]).sum())
    fn = int((unsplit["truly_compound"] & ~unsplit["routed"]).sum())
    tn = int((~unsplit["truly_compound"] & ~unsplit["routed"]).sum())

    return {
        "n_segments": len(d),
        "by_route": d["route"].value_counts().to_dict(),
        "routed_share": round(float(d["routed"].mean()), 3),
        "detector_precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
        "detector_recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
        "true_pos": tp, "false_pos": fp, "false_neg": fn, "true_neg": tn,
        # What the LLM would be asked to recover, and what is lost if it is not run.
        "mass_total": int(d["n_true"].sum()),
        "mass_found_by_rules": int(d["hits"].sum()) if "hits" in d else None,
        "mass_missed_in_routed": int(d.loc[d["routed"], "missed_mass"].sum()),
        "mass_missed_unrouted": int(d.loc[~d["routed"] & ~d["rules_split"], "missed_mass"].sum()),
        "detail": d,
    }


def gate1(atom_scores: dict, class_scores: dict) -> pd.DataFrame:
    """The Gate 1 table, read off held-out figures against `config` thresholds.

    Classification is judged on the definition-stable labels and carries a
    coverage floor, so the criterion cannot be satisfied by abstaining.
    """
    cls = class_scores.get("stable_holdout") or class_scores["stable"]
    rows = [
        {"criterion": "Atomisation precision (holdout)",
         "threshold": config.GATE_ATOM_PRECISION, "result": atom_scores["precision"]},
        {"criterion": "Atomisation recall (holdout)",
         "threshold": config.GATE_ATOM_RECALL, "result": atom_scores["recall"]},
        {"criterion": "Classification accuracy, stable labels",
         "threshold": config.GATE_CLASS_ACCURACY, "result": cls["on_assigned"]},
        {"criterion": "Classification coverage",
         "threshold": config.GATE_CLASS_MIN_COVERAGE, "result": cls["coverage"]},
    ]
    out = pd.DataFrame(rows)
    out["passes"] = out["result"] >= out["threshold"]
    return out


def write_atomisation_recheck(labelled: pd.DataFrame, out_dir,
                              name: str = "atomisation_long_relabel") -> "Path":
    """Re-ask the long segments under the settled splitting convention.

    Long segments are 35% of the labelled rows but **61% of the requirement
    mass**, and they carry the entire remaining gate failure — short segments
    already reach 0.897 / 0.835. So this is where a clearer target changes the
    measurement, and where a vaguer one has been hiding as model error.

    The point is not to relabel for its own sake. Round 1's long-segment labels
    applied the cross-product rule inconsistently: three roles against two
    contexts were expanded to six in one row and four roles against three
    industries were left as seven in another. Until one rule governs both, an
    extractor cannot be scored on either, because being right on one row means
    being wrong on the other.

    Previous labels are deliberately absent from the sheet, and the order is
    shuffled, so the answer is given again rather than copied.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    long_rows = labelled[labelled["segment"].astype(str).str.len() > config.LONG_SEGMENT_CHARS]
    sheet = long_rows[["segment"]].copy()
    if "language" in long_rows.columns:
        sheet.insert(0, "language", long_rows["language"])
    sheet = sheet.sample(frac=1, random_state=DEV_HOLDOUT_SEED).reset_index(drop=True)
    sheet.insert(0, "id", range(1, len(sheet) + 1))
    sheet["true_requirements"] = ""
    sheet["unsure"] = ""

    path = out_dir / f"validation_{name}_BLANK.csv"
    sheet.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_recheck_sheet(phrases: pd.DataFrame, out_dir, name: str = "recheck_domain") -> "Path":
    """Write a small blind sheet re-asking about phrases already labelled once.

    Its purpose is narrow: measure whether a *definition* change moved the
    labels, holding the phrases fixed. A fresh sample cannot do that, because a
    change in the labels would be confounded with a change in the rows.

    The previous label is deliberately absent from the sheet — as is every other
    piece of pipeline output — but the phrases are not new to the labeller, so
    some recall of their earlier answer is possible and the result should be read
    as indicative rather than independent. Order is shuffled to weaken it.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = phrases[["phrase"]].copy()
    if "language" in phrases.columns:
        sheet.insert(0, "language", phrases["language"])
    sheet = sheet.sample(frac=1, random_state=DEV_HOLDOUT_SEED).reset_index(drop=True)
    sheet.insert(0, "id", range(1, len(sheet) + 1))
    sheet["true_type"] = ""
    sheet["unsure"] = ""

    path = out_dir / f"validation_{name}_BLANK.csv"
    sheet.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _top_up(sample: pd.DataFrame, pool: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Proportional allocation rounds down; draw the shortfall at random."""
    if len(sample) >= n:
        return sample.head(n)
    remaining = pool[~pool.index.isin(sample.index)]
    extra = remaining.sample(min(n - len(sample), len(remaining)), random_state=seed)
    return pd.concat([sample, extra], ignore_index=True)


def draw_atomisation_sample(
    df: pd.DataFrame, n: int = 150, seed: int = 20260830, long_boost: float = 0.35
) -> pd.DataFrame:
    """Sample `must_have` segments, stratified, oversampling long ones.

    Long segments are where splitting actually fails, and a proportional sample
    would barely contain any: they are 3.6% of segments. `long_boost` is the
    share of the sample reserved for them. The over-representation is recorded
    so scoring can report both the raw and the reweighted figure.
    """
    rows = []
    for r in df.itertuples(index=False):
        for seg in atom.segments(r.must_have):
            rows.append(
                {
                    "vacancy_id": r.vacancy_id,
                    "macro_function": r.macro_function,
                    "language": r.language,
                    "segment": seg,
                    "is_long": len(seg) > config.LONG_SEGMENT_CHARS,
                }
            )
    pool = pd.DataFrame(rows)
    pool["stratum"] = _strata(pool)

    rng = np.random.default_rng(seed)
    n_long = int(round(n * long_boost))
    long_part = pool[pool["is_long"]].sample(min(n_long, int(pool["is_long"].sum())), random_state=seed)
    rest = pool[~pool["is_long"]]

    # proportional allocation across strata for the remainder
    take = n - len(long_part)
    weights = rest["stratum"].value_counts(normalize=True)
    picks = []
    for stratum, share in weights.items():
        k = int(round(share * take))
        block = rest[rest["stratum"] == stratum]
        if k and len(block):
            picks.append(block.sample(min(k, len(block)), random_state=seed))
    sample = pd.concat([long_part] + picks, ignore_index=True)
    sample = _top_up(sample, pool, n, seed)
    return sample.sample(frac=1, random_state=seed).reset_index(drop=True)


def draw_classification_sample(reqs: pd.DataFrame, n: int = 150, seed: int = 20260830) -> pd.DataFrame:
    """Sample requirement atoms, stratified by language and function."""
    pool = reqs.copy()
    pool["stratum"] = _strata(pool)
    rng_weights = pool["stratum"].value_counts(normalize=True)
    picks = []
    for stratum, share in rng_weights.items():
        k = int(round(share * n))
        block = pool[pool["stratum"] == stratum]
        if k and len(block):
            picks.append(block.sample(min(k, len(block)), random_state=seed))
    sample = _top_up(pd.concat(picks, ignore_index=True), pool, n, seed)
    return sample.sample(frac=1, random_state=seed).reset_index(drop=True)


def write_blind_sheets(
    atom_sample: pd.DataFrame,
    class_sample: pd.DataFrame,
    out_dir,
    overwrite_labelled: bool = False,
) -> dict:
    """Write the labelling sheets. No pipeline output is included, by design.

    Refuses to redraw a sheet whose ``*_LABELLED.csv`` already exists. The sample
    depends on the analysis base, so any change upstream silently draws different
    rows — and the labels are hand-made by someone who is not allowed to have
    seen the rules, so a desynchronised sheet cannot be regenerated, only
    re-labelled. Pass ``overwrite_labelled=True`` to redraw deliberately, after
    moving the existing labels aside.
    """
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite_labelled:
        existing = sorted(p.name for p in out_dir.glob("*_LABELLED.csv"))
        if existing:
            raise FileExistsError(
                f"human labels present in {out_dir} ({', '.join(existing)}); "
                "redrawing the blind sheets would orphan them. Move them aside and "
                "pass overwrite_labelled=True if that is intended."
            )

    # `unsure` lets the labeller flag a genuine judgement call without corrupting
    # the label. Ambiguous items are exactly what the confusion matrix should be
    # allowed to separate from confident errors.
    a = atom_sample[["vacancy_id", "language", "macro_function", "segment"]].copy()
    a.insert(0, "id", range(1, len(a) + 1))
    a["true_requirements"] = ""
    a["unsure"] = ""
    a_path = out_dir / "validation_atomisation_BLANK.csv"
    a.to_csv(a_path, index=False, encoding="utf-8-sig")

    c = class_sample[["vacancy_id", "language", "macro_function", "phrase"]].copy()
    c.insert(0, "id", range(1, len(c) + 1))
    c["true_type"] = ""
    c["unsure"] = ""
    c_path = out_dir / "validation_classification_BLANK.csv"
    c.to_csv(c_path, index=False, encoding="utf-8-sig")

    # Full labelling rules, tie-breaks and worked examples live in GUIDE.md,
    # which is written by hand and not regenerated here — the worked examples
    # cite specific row ids, so it must be checked if the seed ever changes.
    if not (out_dir / "GUIDE.md").exists():
        (out_dir / "validation_INSTRUCTIONS.txt").write_text(
            "ATOMISATION SHEET\n" + SHEET_INSTRUCTIONS_ATOMISATION +
            "\n\nCLASSIFICATION SHEET\n" + SHEET_INSTRUCTIONS_CLASSIFICATION +
            "\n\nLabel both sheets before looking at any pipeline output.\n",
            encoding="utf-8",
        )
    return {"atomisation": a_path, "classification": c_path}


# --- scoring -----------------------------------------------------------------

def _match(predicted: list[str], truth: list[str], threshold: float = 0.6) -> int:
    """Greedy one-to-one matching on token overlap (Jaccard)."""
    used, hits = set(), 0
    for p in predicted:
        pt = set(atom.normalise(p).split())
        best, best_j = None, 0.0
        for i, t in enumerate(truth):
            if i in used:
                continue
            tt = set(atom.normalise(t).split())
            if not pt or not tt:
                continue
            j = len(pt & tt) / len(pt | tt)
            if j > best_j:
                best, best_j = i, j
        if best is not None and best_j >= threshold:
            used.add(best)
            hits += 1
    return hits


def score_atomisation(labelled: pd.DataFrame) -> dict:
    """Precision and recall of the produced atoms against the human split."""
    rows = []
    for r in labelled.itertuples(index=False):
        raw = r.true_requirements
        # An unlabelled row is NaN, which str() would turn into the literal
        # "nan" and score as a requirement. Skip it and report the count.
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        truth = [t.strip() for t in str(raw).split("|") if t.strip()]
        if not truth:
            continue
        predicted = atom.atomise(r.segment)
        hits = _match(predicted, truth)
        rows.append(
            {
                "id": r.id, "language": r.language, "is_long": len(r.segment) > config.LONG_SEGMENT_CHARS,
                "n_true": len(truth), "n_pred": len(predicted), "hits": hits,
            }
        )
    d = pd.DataFrame(rows)
    precision = d["hits"].sum() / d["n_pred"].sum()
    recall = d["hits"].sum() / d["n_true"].sum()
    return {
        "n_segments": len(d),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
        "exact_count_match": round((d["n_pred"] == d["n_true"]).mean(), 3),
        "over_split": round((d["n_pred"] > d["n_true"]).mean(), 3),
        "under_split": round((d["n_pred"] < d["n_true"]).mean(), 3),
        "by_length": d.groupby("is_long").apply(
            lambda g: pd.Series({"precision": g["hits"].sum() / g["n_pred"].sum(),
                                 "recall": g["hits"].sum() / g["n_true"].sum()}), include_groups=False
        ).round(3),
        "detail": d,
    }


def score_classification(labelled: pd.DataFrame) -> dict:
    """Accuracy of the lexicon against human labels, overall and per type."""
    from . import classify as clf

    d = labelled.copy()
    d["true_type"] = d["true_type"].str.strip().str.lower()
    d = d[d["true_type"] != ""]
    d["predicted"] = d["phrase"].map(lambda p: clf.classify(atom.normalise(p)) or "unassigned")

    scored = d[d["predicted"] != "unassigned"]
    return {
        "n_labelled": len(d),
        "n_assigned": len(scored),
        "coverage": round(len(scored) / len(d), 3) if len(d) else 0.0,
        "accuracy_on_assigned": round((scored["predicted"] == scored["true_type"]).mean(), 3) if len(scored) else 0.0,
        "confusion": pd.crosstab(d["true_type"], d["predicted"]),
        "by_language": d.assign(ok=d["predicted"] == d["true_type"]).groupby("language")["ok"].agg(["mean", "size"]).round(3),
        "detail": d,
    }
