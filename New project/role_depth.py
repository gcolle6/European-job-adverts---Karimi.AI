"""How many roles can actually be nodes on a map?

The plan is "a map for every role". That assumes roles exist as a usable unit.
This checks whether they do, because a node needs enough adverts for its
requirement profile to be stable - one advert gives one employer's wording, not a
role.

The answer decides the shape of the whole deliverable, and it is also the sharpest
version of the question to put to Karimi, because it converts "send us more data"
into "how many nodes does more data buy".

Run: python role_depth.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karimi import data  # noqa: E402

TARGET_CORPUS = 500_000
MIN_FOR_A_NODE = (10, 25, 50, 100)
SENIORITY = r"\b(senior|junior|lead|principal|staff|head of|chief|sr|jr|intern|graduate|trainee|apprentice|stagiaire|praktikant|werkstudent|alternance)\b"


def depth(counts: pd.Series, n_postings: int, label: str) -> None:
    print(f"\n{label}: {len(counts):,} distinct, "
          f"{n_postings / len(counts):.1f} postings each on average")
    for t in MIN_FOR_A_NODE:
        hit = counts[counts >= t]
        print(f"  >= {t:>3} postings: {len(hit):>6,} roles, "
              f"{hit.sum() / n_postings:>5.1%} of postings")


def main() -> None:
    b = data.build_analysis_base().df
    n = len(b)
    print(f"{n:,} postings")

    counts = b["title_norm"].value_counts()
    depth(counts, n, "RAW title_norm")

    # Two cheap normalisations, to see how much of the fragmentation is
    # cosmetic rather than real. Neither is proposed as the method - they are a
    # lower bound on what any method would recover.
    stripped = (b["title_norm"].str.replace(SENIORITY, " ", regex=True)
                .str.replace(r"\s+", " ", regex=True).str.strip())
    depth(stripped.value_counts(), n, "minus seniority words")

    # Employer names leak into titles ("... seller grand frais"). Remove any
    # company name token that appears in the title of its own postings.
    comp = b["company"].fillna("").str.lower().str.replace(r"[^\w ]", " ", regex=True)
    cleaned = []
    for t, c in zip(stripped, comp):
        for tok in c.split():
            if len(tok) > 3:
                t = re.sub(rf"\b{re.escape(tok)}\b", " ", t)
        cleaned.append(re.sub(r"\s+", " ", t).strip())
    cleaned = pd.Series(cleaned, index=b.index)
    depth(cleaned.value_counts(), n, "minus seniority AND employer name")

    # What does more data buy? Scale every title's count by the corpus ratio.
    # Crude - it assumes the title mix is stable - but it brackets the answer.
    ratio = TARGET_CORPUS / n
    print(f"\nProjected to {TARGET_CORPUS:,} postings (x{ratio:.1f}), "
          "assuming the title mix holds:")
    for name, cc in (("raw", counts), ("cleaned", cleaned.value_counts())):
        for t in MIN_FOR_A_NODE:
            hit = cc[cc * ratio >= t]
            print(f"  {name:<8} >= {t:>3}: {len(hit):>6,} roles, "
                  f"{hit.sum() / n:>5.1%} of postings")

    print("\ntop 12 after cleaning:")
    print(cleaned.value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
