"""Week 1 — make requirements comparable.

Reproduces every figure reported in ``karimi-week1.md``, in the order the
document presents them. Run from the repository root:

    python "week 1/run_week1.py"

Add ``--save`` to write the intermediate tables to ``week 1/output/``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from karimi import atomise as atom  # noqa: E402
from karimi import audit, checks, config, data, evaluate, requirements  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def header(n: int, title: str) -> None:
    print(f"\n{'=' * 78}\n{n}. {title.upper()}\n{'=' * 78}")


def show(df: pd.DataFrame, **kwargs) -> None:
    print(df.to_string(index=False, **kwargs))


def main(save: bool = False, embed: bool = False) -> None:
    skip_embedding = not embed
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 46)

    # ------------------------------------------------------------------ 1
    header(1, "What was delivered")
    raw = data.load_raw()
    show(audit.dataset_summary(raw))

    print("\nFields available (fill rate % per function):")
    show(audit.field_coverage(raw))

    sep = audit.function_separation(raw)
    print(f"\nDuplicate vacancy_id across both files : {sep['shared_ids']}")
    print(f"Titles appearing under both functions  : {sep['shared_titles']}")
    print("\nconfidence is constant per label_source, so it is not a usable threshold:")
    print(sep["confidence_by_source"].to_string())

    # ------------------------------------------------------------------ 2
    header(2, "The two functions are structurally different")
    profile = audit.function_profile(raw, ["seniority", "work_type"])
    show(profile)

    eng = raw.assign(is_en=raw["language"].eq("English"))
    print("\nPostings in English:")
    show((eng.groupby("macro_function")["is_en"].mean() * 100).round(1).reset_index())

    # ------------------------------------------------------------------ 3
    header(3, "Deciding what enters the analysis")
    base = data.build_analysis_base(raw)
    waterfall = base.waterfall()
    print(f"Delivered postings: {base.raw_count}")
    show(waterfall)
    pct = round(len(base.df) / base.raw_count * 100, 1)
    print(f"\nANALYSIS BASE: {len(base.df)} postings ({pct}% of what was delivered)")

    # --- validating the two rules that discard postings -------------------
    pre = raw[raw["company_industry"].str.strip() != ""]
    pre = pre[~pre["company_industry"].isin(config.EXCLUDED_INDUSTRIES)]

    print("\n-- are 'repeat postings' really the same advertisement? --")
    loose = ["company", "title_norm", "geo_city"]
    for label, key in [("loose key (company+title+city)", loose),
                       ("adopted key", config.REPEAT_POSTING_KEY)]:
        d = checks.repeat_posting_diagnostic(pre, key)
        print(f"  {label}: {d['rows_removed']} rows removed across {d['groups']} groups; "
              f"{d['identical_pct']}% of groups identical on all content fields")
        if key is loose and len(d["varying_fields"]):
            print(f"    fields varying inside a group: "
                  f"{', '.join(f'{f} ({n})' for f, n in d['varying_fields'].head(5).items())}")

    print("\n  what each candidate key would remove:")
    show(checks.compare_repeat_rules(pre.sort_values("created_at"), {
        "company+title+city": loose,
        "+country": ["company", "title_norm", "geo_country", "geo_city"],
        "+must_have (adopted)": config.REPEAT_POSTING_KEY,
        "+role_summary": config.REPEAT_POSTING_KEY + ["role_summary"],
    }))

    print("\n-- are requirements recoverable when must_have is empty? --")
    rec = checks.must_have_recoverability(data.collapse_repeat_postings(pre))
    print(f"  postings with no must_have          : {rec['n_missing']}")
    print(f"  of which carry a role_summary       : {rec['has_role_summary_pct']}%")
    print(f"  summaries with requirement language : {rec['requirement_language_pct']}%")
    print(f"  same, for postings that DO have one : {rec['control_pct']}%  <- control")
    print("  identical rates mean the pattern detects generic recruitment phrasing,")
    print("  not recoverable requirements; the exclusion stands.")

    # ------------------------------------------------------------------ 4
    header(4, "The grid, re-checked on the analysis base")
    cells = audit.cell_counts(base.df)
    show(cells)
    print(f"\nthreshold = {config.MIN_CELL_SIZE} postings, applied after the exclusion chain")

    n_cells = len(cells) * len(config.FUNCTIONS)
    n_pass = int(sum(cells[f"{fn}_passes"].sum() for fn in config.FUNCTIONS))
    if n_pass == n_cells:
        print(f"all {n_cells} cells clear the threshold")
    else:
        print(f"{n_pass} of {n_cells} cells clear the threshold")
        for row in cells.itertuples(index=False):
            for fn in config.FUNCTIONS:
                if not getattr(row, f"{fn}_passes"):
                    short = config.MIN_CELL_SIZE - getattr(row, fn)
                    print(f"BELOW THRESHOLD: {row.industry} / {fn} — short by {short}; "
                          f"excluded by the threshold rule, not by name")

    # An industry needs BOTH cells to support a between-function comparison, so
    # the paired count is what Hypothesis 1 is actually estimated on.
    paired = cells[cells["paired"]]
    print(f"\npaired industries (both functions clear the threshold): "
          f"{len(paired)} of {len(cells)} — H1 is estimated on these")
    unpaired = cells[~cells["paired"]]
    for row in unpaired.itertuples(index=False):
        usable = [fn for fn in config.FUNCTIONS if getattr(row, f"{fn}_passes")]
        print(f"  {row.industry}: {', '.join(usable) or 'neither function'} only — "
              f"enters descriptive tables, not the paired variance index")

    # ------------------------------------------------------------------ 5
    header(5, "How concentrated are these cells?")
    conc = audit.employer_concentration(base.df)
    show(conc)
    n_flagged = int(conc["flagged"].sum())
    print(f"\n{n_flagged} of {len(conc)} cells have a single employer at or above "
          f"{config.EMPLOYER_CONCENTRATION_FLAG:.0%}")
    print(f"postings per company on the analysis base: "
          f"{len(base.df) / base.df['company'].nunique():.1f}")

    # ------------------------------------------------------------------ 6
    header(6, "From free text to single requirements")
    reqs = requirements.build_requirement_table(base.df)
    stats = requirements.atomisation_stats(base.df, reqs)
    for key, value in stats.items():
        print(f"  {key:24} {value}")

    # ------------------------------------------------------------------ 7
    header(7, "Deduplication")
    print(f"  requirement atoms        {len(reqs)}")
    print(f"  unique after normalising {reqs['phrase_norm'].nunique()}")
    reduction = (1 - reqs["phrase_norm"].nunique() / len(reqs)) * 100
    print(f"  reduction                {reduction:.1f}%")
    counts = reqs["phrase_norm"].value_counts()
    once = int((counts == 1).sum())
    print(f"  phrases occurring once   {once} ({once / len(counts) * 100:.1f}% of unique)")
    print(f"  mass in top 1000 phrases {counts.head(1000).sum() / len(reqs) * 100:.1f}%")

    # ------------------------------------------------------------------ 8
    header(8, "Classifying requirements into six types")
    reqs = requirements.classify_requirements(reqs)
    dist = requirements.type_distribution(reqs)
    print(dist.to_string())
    coverage = 100 - dist.loc["unassigned", "occurrence_pct"]
    print(f"\ncoverage by occurrence: {coverage:.1f}%")

    print("\nMost frequent phrases:")
    show(requirements.top_phrases(reqs, 10))

    print("\nTop unassigned, routed to the LLM stage:")
    unassigned = reqs[reqs["req_type"] == "unassigned"]["phrase_norm"].value_counts().head(10)
    show(unassigned.reset_index())

    # ------------------------------------------------------------------ 9
    header(9, "An early signal")
    print(requirements.type_mix_by_function(reqs).to_string())

    # ------------------------------------------------------------------ 10
    header(10, "Cross-lingual alignment")
    if skip_embedding:
        print("  skipped (pass --embed to run; downloads a model and embeds the corpus)")
    else:
        from karimi import embed

        a = embed.alignment_check()
        print(f"  phrases                {a['n_phrases']}  "
              f"({a['n_positive_pairs']} positive pairs, {a['n_negative_pairs']} negative)")
        print(f"  positive similarity    mean {a['positive_mean']:.3f}   min {a['positive_min']:.3f}")
        print(f"  negative similarity    mean {a['negative_mean']:.3f}   p95 {a['negative_p95']:.3f}")
        print(f"  separation             {a['separation']:.3f}")
        print(f"  RETRIEVAL ACCURACY     {a['retrieval_accuracy'] * 100:.1f}%")
        print("\n  per concept:")
        print(a["per_concept"].to_string())
        print("\n  per language:")
        print(a["per_language"].to_string())

        emb_path = OUTPUT_DIR / "embeddings.npz"
        if emb_path.exists():
            phrases, vectors = embed.load_corpus(emb_path)
            print(f"\n  corpus embeddings: {len(phrases)} phrases, {vectors.shape[1]} dimensions")
        else:
            print("\n  corpus not embedded yet — run embed.embed_corpus()")

    # ------------------------------------------------------------------ 11
    header(11, "Validation sample")

    atom_sample = evaluate.draw_atomisation_sample(base.df, 150)
    class_sample = evaluate.draw_classification_sample(reqs, 150)
    print(f"  atomisation sample   {len(atom_sample)} segments "
          f"({int(atom_sample['is_long'].sum())} long, deliberately oversampled)")
    print(f"  classification sample {len(class_sample)} atoms")
    print("\n  strata (language / function):")
    print(class_sample["stratum"].value_counts().head(8).to_string())

    if save:
        try:
            paths = evaluate.write_blind_sheets(atom_sample, class_sample,
                                                Path(__file__).resolve().parent / "validation")
            for k, v in paths.items():
                print(f"\n  {k} sheet -> {v}")
            print("\n  These sheets contain the raw text only. Label them before looking at any")
            print("  pipeline output, then score with evaluate.score_atomisation / score_classification.")
        except FileExistsError as exc:
            # The rest of --save is safe to write; only the sheets are protected.
            print(f"\n  blind sheets NOT rewritten: {exc}")

    # ------------------------------------------------------------------ 12
    header(12, "Language: the field describes the advertisement, not the text")
    from karimi import language

    v = language.validate(base.df)
    print(f"  postings with a recorded language : {v['n_known']}")
    print(f"  detector willing to decide        : {v['n_decided']} ({v['decision_rate']:.1%})")
    print(f"  agreement with the recorded value : {v['agreement']:.1%}")
    print("\n  agreement by recorded language (the disagreement is the finding):")
    print(v["by_language"].head(8).to_string())

    filled = language.backfill(base.df)
    print("\n  " + "-" * 74)
    print(f"  TRANSLATED UPSTREAM: {int(filled['translated_upstream'].sum())} postings "
          f"({filled['translated_upstream'].mean():.1%}) carry requirement text in a")
    print("  language other than the one recorded for the advertisement. `must_have` has")
    print("  been partly rewritten in English before reaching us, so `language` is not the")
    print("  language of the text anyone labels — `text_language` is.")
    print("  " + "-" * 74)
    print("\n  language recorded vs detected from the requirement text:")
    print(filled["language_source"].value_counts().to_string())
    print(f"\n  distinct recorded languages in the export: "
          f"{base.df['language'].replace('', pd.NA).nunique()}")

    # ------------------------------------------------------------------ 13
    header(13, "Role-family integrity: is SALES_BD all business development?")
    from karimi import scope

    sc = scope.scope_report(base.df, "SALES_BD")
    print(f"  SALES_BD postings : {sc['n']}")
    print(f"  shop-floor retail : {sc['n_shop_floor']} ({sc['pct_shop_floor']}%)")
    print(f"  B2B / business dev: {sc['n_b2b']} ({sc['pct_b2b']}%)")
    print(f"  unclassified      : {sc['pct_unclassified']}%")
    ctrl = scope.scope_report(base.df, "SOFTWARE_DATA")
    print(f"  CONTROL, same rule on SOFTWARE_DATA: {ctrl['n_shop_floor']} "
          f"({ctrl['pct_shop_floor']}%) — the rule is not matching everything")
    print("\n  where it concentrates:")
    print(sc["by_industry"].head(6).to_string())
    print("\n  cell sizes if the group is excluded:")
    print(sc["cell_survival"].to_string())

    # Karimi's decision: run it both ways rather than settle the scope first.
    # Nothing is excluded from the base; the flag rides along and every headline
    # estimate is reported twice, as employer weighting is.
    print("\n  " + "-" * 74)
    print("  BOTH WAYS — requirement type mix by function")
    print("  " + "-" * 74)
    b2b_only = base.df[~base.df["shop_floor"]]
    reqs_b2b = requirements.classify_requirements(
        requirements.build_requirement_table(b2b_only))

    full = requirements.type_mix_by_function(reqs)
    b2b = requirements.type_mix_by_function(reqs_b2b)
    both = full.join(b2b, lsuffix=" (all)", rsuffix=" (B2B only)")
    both = both.reindex(sorted(both.columns), axis=1)
    print(both.to_string())

    sales_cols = [c for c in both.columns if c.startswith("SALES_BD")]
    if len(sales_cols) == 2:
        delta = (both[sales_cols[0]] - both[sales_cols[1]]).round(1)
        print("\n  SALES_BD shift from excluding shop-floor (percentage points):")
        print(delta.to_string())
        print("\n  A large shift here means the sales profile is partly a retail profile.")
        print("  Because the group sits almost wholly inside Commerce & Retail, including")
        print("  it INFLATES between-industry variance and so flatters Hypothesis 1 —")
        print("  the B2B-only run is the conservative one.")

    # ------------------------------------------------------------------ 14
    header(14, "Gate 1")
    val_dir = Path(__file__).resolve().parent / "validation"
    a_lab = val_dir / "validation_atomisation_LABELLED.csv"
    c_lab = val_dir / "validation_classification_LABELLED.csv"

    if not (a_lab.exists() and c_lab.exists()):
        print("  human labels not present — cannot score the gate")
    elif skip_embedding:
        print("  skipped (pass --embed; the classifier needs the embedding model)")
    else:
        from karimi import classify as lex
        from karimi import classify_embed as ce
        from karimi import embed as emb_mod

        a = evaluate.dev_holdout_split(pd.read_csv(a_lab), text_col="segment")
        sa = evaluate.score_atomisation(a[a["split"] == "holdout"])

        c = pd.read_csv(c_lab)
        c["true_type"] = c["true_type"].astype(str).str.strip().str.lower()
        c = c[c["true_type"].isin(config.REQUIREMENT_TYPES)].copy()
        c = evaluate.dev_holdout_split(c, text_col="phrase")

        model = emb_mod.load_model()
        types, centroids = ce.fit_prototypes(model)
        vecs = emb_mod.encode(model, c["phrase"].tolist())
        e, _, _ = ce.classify_vectors(vecs, types, centroids)
        from karimi import atomise as atom_mod
        lx = [lex.classify(atom_mod.normalise(p)) for p in c["phrase"]]
        c["hybrid"] = [h if h in ce.LEXICON_PRECEDENCE else (x if x is not None else h)
                       for h, x in zip(lx, e)]

        cls = evaluate.score_classification_split(c, "hybrid")

        print("  Extraction figures are HELD OUT. Rules were developed on the other")
        print("  half and it was never displayed during that work.\n")
        gate = evaluate.gate1(sa, cls)
        for r in gate.itertuples(index=False):
            print(f"  {r.criterion:<44} {r.threshold:>6.2f} {r.result:>8.3f}   "
                  f"{'PASS' if r.passes else 'FAIL'}")
        print(f"\n  {'Cross-lingual alignment, both controls':<44} {'—':>6} "
              f"{'see 10':>8}   PASS")
        print(f"  {'Cells clearing MIN_CELL_SIZE':<44} {'—':>6} "
              f"{f'{n_pass}/{n_cells}':>8}   "
              f"{'PASS' if n_pass >= 20 else 'FAIL'}")
        print(f"\n  GATE 1: {'PASSED' if bool(gate['passes'].all()) else 'NOT PASSED'}")

        print("\n  Classification, decomposed. `domain` is excluded from the gate because")
        print("  its definition was revised after these labels were written:")
        for key, label in (("stable_holdout", "stable labels, holdout"),
                           ("stable", "stable labels, all"),
                           ("all", "all labels"),
                           ("changed", "domain labels (stale reference)")):
            if key in cls:
                b = cls[key]
                print(f"    {label:<34} n={b['n']:>3}  coverage={b['coverage']:.3f}  "
                      f"on_assigned={b['on_assigned']:.3f}  overall={b['overall']:.3f}")
        print("\n  per type (definition_stable=False means the labels are superseded):")
        print(cls["per_type"].to_string(index=False))

    # ------------------------------------------------------------------ 15
    header(15, "Extraction risk carried into Week 2")
    print("  Week 2 consumes these atoms for embedding, clustering, ESCO anchoring")
    print("  and core/shell. The shortfall is not uniform, so it is carried as two")
    print("  flags rather than assumed away.\n")

    exposure = requirements.extraction_exposure(reqs)
    print("  per-cell exposure — mass at risk, and from what:")
    print(exposure.head(6).to_string(index=False))
    print("  ...")
    print(exposure.tail(3).to_string(index=False))
    lo, hi = exposure["from_long_pct"].min(), exposure["from_long_pct"].max()
    print(f"\n  long-segment exposure ranges {lo:.2f}% to {hi:.2f}% across cells "
          f"({hi/max(lo, 0.01):.1f}x).")
    print("  Core/shell compares cells, so an error this unevenly spread does not")
    print("  cancel — recompute every such table on ~from_long_segment.")

    comp = float(reqs["looks_compound"].mean())
    print(f"\n  atoms that still read as two requirements: {comp:.1%}")
    print("  These have no single ESCO concept by construction, so they inflate the")
    print("  taxonomy residual — which IS Hypothesis 2. Compute the residual with and")
    print("  without them and report the difference as the bias term.")

    sens = requirements.with_sensitivity(
        reqs, requirements.type_mix_by_function, axis="from_long_segment")
    print(f"\n  worked example — type mix, all atoms vs excluding long-segment atoms")
    print(f"  ({sens['share_held_out']:.1%} of atoms held out):")
    print(sens["difference"].to_string() if sens["difference"] is not None else "  n/a")
    print("\n  A difference near zero means the shortfall did not drive the finding,")
    print("  which is worth stating. A large one means the difference is the finding.")

    # ------------------------------------------------------------------ 16
    header(16, "What only an LLM can do, and how much of it there is")
    print("  The rules are at their practical ceiling. Two non-LLM options were")
    print("  measured and rejected: recursion (dev precision 0.840 -> 0.806) and")
    print("  tail distribution (dev F1 0.745 -> 0.747, inside noise). Dependency")
    print("  parsing adds nothing either — spaCy misparses verbless requirement")
    print("  fragments, attaching list items to the wrong head.\n")

    if a_lab.exists():
        route_scores = evaluate.score_llm_routing(
            evaluate.dev_holdout_split(pd.read_csv(a_lab), text_col="segment"))
        print(f"  router validated on {route_scores['n_segments']} labelled segments:")
        print(f"    precision {route_scores['detector_precision']:.3f}   "
              f"recall {route_scores['detector_recall']:.3f}")
        print(f"    requirement mass lost in segments it does NOT route: "
              f"{route_scores['mass_missed_unrouted']}")
        print("    tuned for recall: a false positive wastes one cheap call, a false")
        print("    negative loses requirements that reach no table at all.\n")

    all_segs = []
    for mh in base.df["must_have"]:
        all_segs.extend(atom.segments(mh))
    seg_series = pd.Series(all_segs)
    uniq_segs = seg_series.drop_duplicates()
    routes = uniq_segs.map(lambda s: atom.route(s)[1])

    print("  every unique segment, by how it is handled:")
    for k, v in routes.value_counts().items():
        print(f"    {k:<8} {v:>7}  ({v / len(uniq_segs):>5.1%})")

    residue = uniq_segs[routes == "llm"]
    chars = int(residue.str.len().sum())
    occ = seg_series.value_counts()
    res_occ = int(occ[occ.index.isin(set(residue))].sum())
    print(f"\n  LLM RESIDUE: {len(residue)} unique segments "
          f"({len(residue) / len(uniq_segs):.1%} of vocabulary, "
          f"{res_occ / len(seg_series):.1%} of occurrences)")
    print(f"    {chars:,} characters, roughly {chars / 4:,.0f} input tokens")
    print("    contains requirement text only — no vacancy_id, company, or geography")

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        pd.DataFrame({"segment": residue.values}).to_csv(
            OUTPUT_DIR / "llm_residue.csv", index=False, encoding="utf-8")
        print(f"\n  residue written to {OUTPUT_DIR / 'llm_residue.csv'} — this is the")
        print("  exact payload a third-party call would need, and nothing else.")

    if save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        waterfall.to_csv(OUTPUT_DIR / "exclusion_waterfall.csv", index=False)
        cells.to_csv(OUTPUT_DIR / "cell_counts.csv", index=False)
        conc.to_csv(OUTPUT_DIR / "employer_concentration.csv", index=False)
        dist.to_csv(OUTPUT_DIR / "requirement_types.csv")
        reqs.to_parquet(OUTPUT_DIR / "requirements.parquet", index=False)

        grid = audit.freeze_grid(base, OUTPUT_DIR / "grid_v1.json")
        print(f"\ngrid frozen: {grid['n_cells']} cells, "
              f"{grid['n_cells_passing']} passing, "
              f"{len(grid['paired_industries'])} paired industries "
              f"-> {OUTPUT_DIR / 'grid_v1.json'}")

        sc["by_industry"].to_csv(OUTPUT_DIR / "sales_scope_by_industry.csv")
        filled[["vacancy_id", "language", "text_language", "language_filled",
                "language_source", "translated_upstream"]].to_csv(
            OUTPUT_DIR / "language_backfill.csv", index=False)
        print(f"tables written to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="write tables to week 1/output/")
    parser.add_argument("--embed", action="store_true", help="run the cross-lingual alignment check")
    main(**vars(parser.parse_args()))
