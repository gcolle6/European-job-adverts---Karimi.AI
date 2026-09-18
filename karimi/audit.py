"""Descriptive checks on the delivered data.

Everything here answers a question that has to be settled before measurement:
what is in the export, does the grid survive the exclusions, and how much of any
given cell is one employer talking.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config


def dataset_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Postings, companies, countries and date span, per function."""
    rows = []
    for fn in config.FUNCTIONS:
        sub = df[df["macro_function"] == fn]
        rows.append(
            {
                "function": fn,
                "postings": len(sub),
                "companies": sub["company"].nunique(),
                "countries": sub["geo_country"].replace("", pd.NA).nunique(),
                "cities": sub["geo_city"].replace("", pd.NA).nunique(),
                "expired_pct": round(sub["expired"].mean() * 100, 1),
                "first": sub["created_at"].min().date(),
                "last": sub["created_at"].max().date(),
            }
        )
    return pd.DataFrame(rows)


def field_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Fill rate per field per function, plus distinct-value counts.

    This is the data dictionary: what exists, how often, and how varied.
    """
    rows = []
    for col in df.columns:
        row = {"field": col}
        for fn in config.FUNCTIONS:
            sub = df[df["macro_function"] == fn][col]
            filled = sub.notna() & (sub.astype(str).str.strip() != "")
            row[fn] = round(filled.mean() * 100, 1)
        row["distinct"] = df[col].replace("", pd.NA).nunique()
        rows.append(row)
    return pd.DataFrame(rows)


def function_profile(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Share of each categorical value within each function, side by side."""
    columns = columns or ["seniority", "work_type", "company_industry", "company_size", "company_type"]
    rows = []
    for col in columns:
        for fn in config.FUNCTIONS:
            sub = df[df["macro_function"] == fn]
            counts = sub[col].replace("", "(missing)").value_counts(normalize=True) * 100
            for value, share in counts.items():
                rows.append({"field": col, "value": value, "function": fn, "pct": round(share, 1)})
    out = pd.DataFrame(rows)
    return out.pivot_table(index=["field", "value"], columns="function", values="pct").reset_index()


def cell_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Postings per (industry, function) cell, with the threshold verdict.

    Two verdicts, because they answer different questions. ``<fn>_passes`` is
    per cell and decides what enters a descriptive or core/shell table.
    ``paired`` requires both functions to clear the threshold in the same
    industry, which is what a between-function variance comparison needs — so an
    industry can contribute one cell and still be unusable for Hypothesis 1.
    """
    rows = []
    for industry in config.ALL_INDUSTRIES:
        row = {"industry": industry}
        for fn in config.FUNCTIONS:
            row[fn] = int(((df["company_industry"] == industry) & (df["macro_function"] == fn)).sum())
        for fn in config.FUNCTIONS:
            row[f"{fn}_passes"] = row[fn] >= config.MIN_CELL_SIZE
        row["paired"] = all(row[fn] >= config.MIN_CELL_SIZE for fn in config.FUNCTIONS)
        rows.append(row)
    return pd.DataFrame(rows)


def freeze_grid(base, path=None) -> dict:
    """Write the grid as a versioned artefact, and return it.

    The point of freezing it is that every later table has to be readable
    against the grid that produced it. Cell counts move whenever the exclusion
    chain moves, so a published figure without a recorded grid cannot be
    reproduced — and a grid recorded only as prose cannot be diffed. Each cell
    carries its raw count, its count after exclusions, and its own threshold
    verdict, plus whether its industry supports a paired comparison.
    """
    import json
    from datetime import date

    from . import data as _data

    raw = _data.load_raw()
    df = base.df

    cells = []
    for industry in config.ALL_INDUSTRIES:
        for fn in config.FUNCTIONS:
            n_raw = int(((raw["company_industry"] == industry) & (raw["macro_function"] == fn)).sum())
            n_base = int(((df["company_industry"] == industry) & (df["macro_function"] == fn)).sum())
            cells.append({
                "industry": industry,
                "function": fn,
                "n_raw": n_raw,
                "n_after_exclusions": n_base,
                "passes": n_base >= config.MIN_CELL_SIZE,
                "pre_committed_industry": industry in config.GRID_INDUSTRIES,
            })

    paired = sorted({
        c["industry"] for c in cells
        if all(d["passes"] for d in cells if d["industry"] == c["industry"])
    })

    grid = {
        "version": 1,
        "frozen_on": date.today().isoformat(),
        "min_cell_size": config.MIN_CELL_SIZE,
        "functions": config.FUNCTIONS,
        "pre_committed_industries": config.GRID_INDUSTRIES,
        "admitted_industries": config.ADDITIONAL_INDUSTRIES,
        "raw_postings": int(len(raw)),
        "analysis_base": int(len(df)),
        "exclusions": [
            {"step": s.reason, "removed": s.removed, "remaining": s.remaining}
            for s in base.steps
        ],
        "paired_industries": paired,
        "n_cells": len(cells),
        "n_cells_passing": sum(c["passes"] for c in cells),
        "cells": cells,
    }

    if path is not None:
        Path(path).write_text(json.dumps(grid, indent=2, ensure_ascii=False), encoding="utf-8")
    return grid


def employer_concentration(df: pd.DataFrame) -> pd.DataFrame:
    """Largest single-employer share within each cell.

    Where one employer supplies a quarter of a cell, an apparent industry
    pattern is substantially that employer's posting template. Cells at or above
    the flag threshold require employer-level clustering downstream.
    """
    rows = []
    for fn in config.FUNCTIONS:
        for industry in config.ALL_INDUSTRIES:
            cell = df[(df["macro_function"] == fn) & (df["company_industry"] == industry)]
            if cell.empty:
                continue
            counts = cell["company"].value_counts()
            rows.append(
                {
                    "function": fn,
                    "industry": industry,
                    "postings": len(cell),
                    "companies": cell["company"].nunique(),
                    "top_employer": counts.index[0],
                    "top_n": int(counts.iloc[0]),
                    "top_share": round(counts.iloc[0] / len(cell) * 100, 1),
                }
            )
    out = pd.DataFrame(rows).sort_values("top_share", ascending=False)
    out["flagged"] = out["top_share"] >= config.EMPLOYER_CONCENTRATION_FLAG * 100
    return out.reset_index(drop=True)


def function_separation(df: pd.DataFrame) -> dict:
    """Is function assignment mutually exclusive, and how confident is it?

    `confidence` is constant per `label_source` — lexicon is always 1.0, priority
    is 0.85 or 0.90 — so only the embedding-sourced rows carry a real score. It
    cannot be used as a single filtering threshold, and this reports why.
    """
    titles = {fn: set(df[df["macro_function"] == fn]["title_norm"]) for fn in config.FUNCTIONS}
    shared_titles = titles[config.FUNCTIONS[0]] & titles[config.FUNCTIONS[1]]
    by_source = df.groupby("label_source")["confidence"].agg(["count", "nunique", "min", "max"])
    return {
        "shared_titles": len(shared_titles),
        "shared_ids": int(df["vacancy_id"].duplicated().sum()),
        "confidence_by_source": by_source,
    }
