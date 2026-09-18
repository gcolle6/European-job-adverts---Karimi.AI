"""Loading and the exclusion chain that produces the analysis base.

The chain is deliberately explicit and ordered: each step states why postings
leave the dataset, and `build_analysis_base` returns the audit trail alongside
the data so the waterfall can be reported rather than asserted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from . import config


def load_raw() -> pd.DataFrame:
    """Read both source files into one frame.

    Every field arrives as a string, `confidence` and `expired` included, so the
    two that carry non-string meaning are cast here and nowhere else.
    """
    frames = []
    for function, path in config.SOURCE_FILES.items():
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        df = pd.DataFrame(rows)
        if "macro_function" not in df.columns:
            df["macro_function"] = function
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
    df["expired"] = df["expired"].map({"True": True, "False": False})
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].fillna("")
    return df


@dataclass
class ExclusionStep:
    reason: str
    removed: int
    remaining: int


@dataclass
class AnalysisBase:
    """The postings that carry a measurable requirement profile, plus the
    audit trail explaining everything that was dropped."""

    df: pd.DataFrame
    steps: list[ExclusionStep] = field(default_factory=list)
    raw_count: int = 0

    def waterfall(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"step": s.reason, "removed": s.removed, "remaining": s.remaining} for s in self.steps]
        )


def collapse_repeat_postings(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the earliest of any rows identical on ``config.REPEAT_POSTING_KEY``.

    Re-advertising one opening is how a single employer's wording enters a cell
    several times. The key includes the requirement text, so two ads that differ
    in what they ask for are kept as two observations — see the note in
    ``config`` for why a looser key removed genuinely distinct postings.

    No longer applied by default; ``mark_repeat_postings`` weights instead of
    dropping. Retained so the Week 1 collapsed base stays reproducible.
    """
    return (
        df.sort_values("created_at")
        .drop_duplicates(subset=config.REPEAT_POSTING_KEY, keep="first")
        .sort_index()
    )


def mark_repeat_postings(df: pd.DataFrame) -> pd.DataFrame:
    """Label repeat groups instead of collapsing them.

    Adds three columns so that the two questions hiding in the old rule can be
    answered separately: how much demand there is (count rows) and what is being
    asked for (weight by ``repeat_weight``, so a template posted 41 times counts
    once). ``is_repeat_first`` marks the earliest row of each group, which
    reproduces the collapsed base as a filter rather than a deletion.
    """
    out = df.copy()
    key = config.REPEAT_POSTING_KEY
    grouped = out.groupby(key, dropna=False)

    out["repeat_group_size"] = grouped["job_id"].transform("size")
    out["repeat_weight"] = 1.0 / out["repeat_group_size"]

    earliest = out.sort_values("created_at").groupby(key, dropna=False).head(1).index
    out["is_repeat_first"] = out.index.isin(earliest)
    return out


def build_analysis_base(df: pd.DataFrame | None = None) -> AnalysisBase:
    """Apply the exclusions in order, recording each one.

    Two of the original four are now parameters in ``config`` rather than fixed
    steps, so a step that is switched off still appears in the waterfall with
    zero removed — a reader can see the rule was considered and what it would
    have cost. Only a missing industry value removes rows unconditionally,
    because a posting with no industry cannot be placed in the grid at all.
    """
    if df is None:
        df = load_raw()

    raw_count = len(df)
    steps: list[ExclusionStep] = []

    def drop(mask: pd.Series, reason: str, frame: pd.DataFrame) -> pd.DataFrame:
        kept = frame[mask]
        steps.append(ExclusionStep(reason, len(frame) - len(kept), len(kept)))
        return kept

    out = df
    out = drop(out["company_industry"].str.strip() != "", "no industry value", out)
    out = drop(
        ~out["company_industry"].isin(config.EXCLUDED_INDUSTRIES),
        "excluded industry (none by name; MIN_CELL_SIZE decides)",
        out,
    )

    if config.COLLAPSE_REPEAT_POSTINGS:
        collapsed = collapse_repeat_postings(out)
        steps.append(ExclusionStep("repeat postings", len(out) - len(collapsed), len(collapsed)))
        out = collapsed
    else:
        out = mark_repeat_postings(out)
        steps.append(ExclusionStep("repeat postings (kept, weighted)", 0, len(out)))

    if config.REQUIRE_MUST_HAVE:
        out = drop(out["must_have"].str.strip() != "", "no must_have value", out)
    else:
        steps.append(ExclusionStep("no must_have value (kept)", 0, len(out)))

    if config.FLAG_SHOP_FLOOR:
        # Flagged, never dropped. Every headline estimate is reported on all of
        # SALES_BD and on B2B only — see the note in `config`.
        from . import scope

        out = scope.flag_roles(out)
        steps.append(ExclusionStep(
            f"shop-floor retail (flagged, kept: {int(out['shop_floor'].sum())})", 0, len(out)))

    return AnalysisBase(df=out.reset_index(drop=True), steps=steps, raw_count=raw_count)
