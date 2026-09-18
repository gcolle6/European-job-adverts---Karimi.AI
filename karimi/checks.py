"""Validation of the exclusion rules.

An exclusion rule that looks reasonable can still be wrong. These checks test
the two rules that discard postings, so the waterfall in the write-up rests on
evidence rather than on the rules sounding sensible.

Both were run in Week 1 and both changed the analysis:

* ``repeat_posting_diagnostic`` showed the first rule (company + title + city)
  collapsing postings that differed in their requirement text, seniority and
  even country. The key now includes the requirement text and the country.
* ``must_have_recoverability`` showed that requirements are *not* recoverable
  from ``role_summary``, which is what justifies dropping those postings.
"""

from __future__ import annotations

import re

import pandas as pd

from . import config

# Identity fields are expected to differ between two rows; everything else is
# content, and content differing means the rows are not the same advertisement.
IDENTITY_FIELDS = ["vacancy_id", "job_id", "created_at"]

# Requirement-like language, across the languages present in the export.
REQUIREMENT_LANGUAGE = re.compile(
    r"\b(?:require|required|requirement|must have|should have|need to|looking for|seeking|"
    r"ideal candidate|qualification|\d+\+? years?|years of experience|experience (?:in|with|as)|"
    r"degree|bachelor|master|proficien|fluen|knowledge of|skills? in|ability to|familiar with|"
    r"erforderlich|voraussetzung|kenntnisse|erfahrung|abschluss|"
    r"requis|exig|exp[ée]rience|dipl[oô]me|ma[iî]trise|comp[ée]tences|"
    r"richiesto|requisiti|esperienza|laurea|conoscenz|"
    r"vereist|ervaring|kennis|requisito|experiencia|conocimiento)",
    re.I,
)


def repeat_posting_diagnostic(df: pd.DataFrame, key: list[str] | None = None) -> dict:
    """Are rows collapsed by `key` actually the same advertisement?

    Returns the share of candidate groups that are identical on every content
    field, and which fields vary inside a group. A high variation rate means the
    key is too loose and the rule is destroying distinct observations.
    """
    key = key or config.REPEAT_POSTING_KEY
    content = [c for c in df.columns if c not in IDENTITY_FIELDS and c not in key]

    sizes = df.groupby(key, sort=False).size()
    dup_keys = sizes[sizes > 1]
    if dup_keys.empty:
        return {"groups": 0, "rows_removed": 0, "identical_pct": None, "varying_fields": pd.Series(dtype=int)}

    dups = df.set_index(key).loc[dup_keys.index].reset_index()
    nunique = dups.groupby(key, sort=False)[content].nunique()
    varies = (nunique > 1)

    varying_fields = varies.sum().sort_values(ascending=False)
    return {
        "groups": len(nunique),
        "rows_removed": int(dup_keys.sum() - len(dup_keys)),
        "identical_pct": round((~varies.any(axis=1)).mean() * 100, 1),
        "varying_fields": varying_fields[varying_fields > 0],
    }


def compare_repeat_rules(df: pd.DataFrame, rules: dict[str, list[str]]) -> pd.DataFrame:
    """How many postings each candidate key would remove."""
    rows = []
    for name, key in rules.items():
        kept = df.drop_duplicates(subset=key, keep="first")
        rows.append({"rule": name, "removed": len(df) - len(kept), "remaining": len(kept)})
    return pd.DataFrame(rows)


def must_have_recoverability(df: pd.DataFrame) -> dict:
    """Are requirements recoverable from `role_summary` when `must_have` is empty?

    The control is the point. Requirement-like language appearing in summaries of
    postings *without* requirements only means something if it appears less often
    than in summaries of postings *with* them. If the two rates match, the
    pattern is detecting generic recruitment phrasing and nothing is recoverable.
    """
    missing = df[df["must_have"].str.strip() == ""]
    present = df[df["must_have"].str.strip() != ""]

    hit = missing["role_summary"].str.contains(REQUIREMENT_LANGUAGE, na=False)
    ctrl = present["role_summary"].str.contains(REQUIREMENT_LANGUAGE, na=False)

    def n_signals(text: str) -> int:
        return len({m.group(0).lower() for m in REQUIREMENT_LANGUAGE.finditer(text or "")})

    signals = missing["role_summary"].map(n_signals)
    return {
        "n_missing": len(missing),
        "has_role_summary_pct": round((missing["role_summary"].str.strip() != "").mean() * 100, 1),
        "requirement_language_pct": round(hit.mean() * 100, 1),
        "control_pct": round(ctrl.mean() * 100, 1),
        "two_or_more_signals_pct": round((signals >= 2).mean() * 100, 1),
        "top_companies": missing["company"].value_counts().head(5),
    }
