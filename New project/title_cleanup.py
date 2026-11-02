"""How much title fragmentation is cosmetic, and how much needs a model?

17,190 distinct titles across 25,800 postings is the binding constraint on the
map (see `role_depth.py`). Before proposing a grouping model it is worth knowing
what a regex already gets, because the part a regex can take is the part nobody
should spend a model on - and the remainder is the real size of the problem.

Four layers, applied cumulatively, each a thing actually seen in the data:

1. **gender markers** - `(d/f/m)`, `(m/w/d)`, `(f/m/x)`, `- H/F`, `F/H`,
   `(all genders)`, `(m/f)`. European advert convention, carries nothing about
   the role, and neither `title_norm` nor `job_title_english` removes it;
2. **bracketed asides** - whatever is left in brackets;
3. **seniority** - the base already carries a clean `seniority` field (5 values,
   100% filled), so seniority in the title is duplicated information. Stripping it
   makes seniority a separate axis rather than a different node, which is what a
   career map wants;
4. **trailing qualifiers** after a dash or slash - location, contract, division.

Run: python title_cleanup.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karimi import data  # noqa: E402

GENDER = re.compile(
    r"\(?\b(?:all\s+genders|[dmfwhx](?:\s*[/|]\s*[dmfwhx]){1,3})\b\)?",
    re.I)
BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
SENIORITY = re.compile(
    r"\b(senior|junior|lead|principal|staff|head\s+of|chief|sr|jr|"
    r"intern|graduate|trainee|apprentice|stagiaire|praktikant|werkstudent|"
    r"alternance|stage|tirocinio|becario|estagi\w+)\b", re.I)
# A SPACED separator only. The first version of this rule was `[-/|]` with
# optional spaces, and a hyphen is a word boundary - so it cut inside words and
# collapsed `it-systemadministrator` to `it`, `hw/sw system engineer` to `hw`,
# `ar/vr software engineer` to `ar`. 513 postings became 1-2 character stubs, and
# because they all collapse to the SAME few stubs it manufactured large fake
# roles - which is where most of the apparent coverage gain came from.
# Fourth instance of this trap in the project, and the same fix as `atomise`:
# never let a boundary match inside a hyphenated word.
TAIL = re.compile(r"\s+[-–—/|]\s+.*$")
MIN_HEAD_TOKENS = 2
SPACE = re.compile(r"\s+")


def tidy(s: str) -> str:
    return SPACE.sub(" ", s).strip(" -–—/|,.").strip()


def report(titles: pd.Series, n: int, label: str) -> None:
    vc = titles.value_counts()
    row = f"{label:<34} {len(vc):>7,} distinct"
    for t in (10, 50):
        hit = vc[vc >= t]
        row += f"   >={t}: {len(hit):>5,} ({hit.sum() / n:>5.1%})"
    print(row)


def main() -> None:
    b = data.build_analysis_base().df
    n = len(b)
    print(f"{n:,} postings\n")

    t = b["job_title"].fillna("").str.lower()
    report(t, n, "raw job_title")
    report(b["title_norm"], n, "title_norm (current)")
    print()

    t = t.map(lambda s: tidy(GENDER.sub(" ", s)))
    report(t, n, "+ gender markers removed")

    t = t.map(lambda s: tidy(BRACKETS.sub(" ", s)))
    report(t, n, "+ bracketed asides")

    t = t.map(lambda s: tidy(SENIORITY.sub(" ", s)))
    report(t, n, "+ seniority (own field already)")

    def cut_tail(s: str) -> str:
        head = tidy(TAIL.sub("", s))
        # Never trade a real title for a stub.
        return head if len(head.split()) >= MIN_HEAD_TOKENS else s

    t_tail = t.map(cut_tail)
    report(t_tail, n, "+ tail after SPACED dash/slash")

    print()
    vc = t_tail.value_counts()
    print(f"still singletons: {(vc == 1).sum():,} titles "
          f"({(vc == 1).sum() / len(vc):.1%} of titles, "
          f"{vc[vc == 1].sum() / n:.1%} of postings)")
    print("\ntop 15 after cleanup:")
    print(vc.head(15).to_string())
    print("\n15 random singletons - what a model would have to group:")
    print(vc[vc == 1].sample(15, random_state=20261012).index.to_series()
          .to_string(index=False))


if __name__ == "__main__":
    main()
