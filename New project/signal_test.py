"""Does the vocabulary carry enough signal for a model to learn on?

The ML layer proposed for the new project only makes sense if a posting's
requirement profile - its vector over the vocabulary - is predictive of something
the vocabulary never saw. This is the decisive test, and it doubles as a
measurement of the vocabulary's own quality: if a 617-dimension profile cannot
beat a bag of words on the raw text, the normalisation layer is not earning its
place and that is a finding.

The task is the core/shell question stated as supervised learning: **holding the
job family fixed, can a model tell which industry an advert comes from, using
nothing but its requirements?** Chance is ~1/11. Anything well above it means the
shell is real and measurable rather than a reading of a chart.

Three guards, each paid for earlier in this project:

* **split by EMPLOYER, never by posting.** One employer posts the same advert 41
  times and `Empathy` is 90% one company - a posting-level split would score
  memorisation of templates. `company_industry` is also a company attribute, so a
  posting-level split leaks the answer outright;
* **two baselines**, because an accuracy with nothing to beat means nothing: the
  majority class, and TF-IDF over the raw phrase text. The second is the one that
  matters - it is the "would raw strings have done just as well" control;
* **a label-shuffle control.** If the pipeline scores above chance on shuffled
  labels, the split leaks and every number above it is void.

Run: python signal_test.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")
REQS = ROOT / "week 1" / "output" / "requirements.parquet"
CLUSTERS = ROOT / "week 2" / "output" / "phrase_clusters.parquet"
SEED = 20261012
TEST_SIZE = 0.30
MIN_POSTINGS_PER_INDUSTRY = 150


def build(function: str) -> tuple:
    """One row per posting: profile over the vocabulary, raw text, labels."""
    reqs = pd.read_parquet(REQS)
    clu = pd.read_parquet(CLUSTERS)[["phrase_norm", "cluster"]].drop_duplicates("phrase_norm")
    df = reqs[reqs["macro_function"] == function].merge(clu, on="phrase_norm", how="left")

    keep = df.groupby("company_industry")["vacancy_id"].nunique()
    keep = keep[keep >= MIN_POSTINGS_PER_INDUSTRY].index
    df = df[df["company_industry"].isin(keep)]

    vac = pd.factorize(df["vacancy_id"])[0]
    n_vac = vac.max() + 1

    # Profile: binary presence of each concept. Noise (-1) is dropped rather than
    # given a column - it is "no concept", not a concept.
    cl = df["cluster"].fillna(-1).astype(int).to_numpy()
    ok = cl >= 0
    cols = pd.factorize(cl[ok])[0]
    X_prof = sparse.csr_matrix(
        (np.ones(ok.sum()), (vac[ok], cols)), shape=(n_vac, cols.max() + 1)
    )
    X_prof.data[:] = 1.0

    # One text per posting, for the bag-of-words control.
    per_vac = df.groupby(vac).agg(
        text=("phrase_norm", lambda s: " | ".join(s.astype(str))),
        industry=("company_industry", "first"),
        company=("company", "first"),
    ).sort_index()

    return X_prof, per_vac["text"].to_numpy(), per_vac["industry"].to_numpy(), \
        per_vac["company"].to_numpy()


N_SPLITS = 5


def splits(X, y, groups):
    """Repeated employer-grouped splits.

    One split cannot separate 0.194 from 0.224 - that is inside the spread a
    different draw produces, and this project has a standing rule against ranking
    on differences smaller than the noise. Five draws, mean and spread reported,
    so a gap is only claimed where it survives the draw.
    """
    gss = GroupShuffleSplit(n_splits=N_SPLITS, test_size=TEST_SIZE,
                            random_state=SEED)
    return list(gss.split(X, y, groups))


def run(X, y, groups, name: str, balanced: bool = True) -> None:
    """Both metrics, always.

    ``class_weight="balanced"`` deliberately trades accuracy on the dominant
    class for recall on the rare ones, so its accuracy must NOT be read against a
    majority-class baseline - that comparison is rigged against it. macro-F1 is
    the comparable number; accuracy is reported unweighted as well so the two
    baselines meet the model on their own terms.
    """
    accs, f1s = [], []
    for tr, te in splits(X, y, groups):
        clf = LogisticRegression(max_iter=2000, C=1.0,
                                 class_weight="balanced" if balanced else None)
        clf.fit(X[tr], y[tr])
        p = clf.predict(X[te])
        accs.append(accuracy_score(y[te], p))
        f1s.append(f1_score(y[te], p, average="macro"))
    tag = "" if balanced else " [unweighted]"
    print(f"  {name + tag:<40} acc {np.mean(accs):>6.1%}  "
          f"macro-F1 {np.mean(f1s):>6.3f} +/- {np.std(f1s):.3f}  "
          f"[{min(f1s):.3f}-{max(f1s):.3f}]")


def baseline_majority(X, y, groups) -> None:
    """What always guessing the largest industry would score, same splits."""
    accs, f1s = [], []
    for tr, te in splits(X, y, groups):
        top = pd.Series(y[tr]).value_counts().index[0]
        p = np.full(len(te), top, dtype=object)
        accs.append(accuracy_score(y[te], p))
        f1s.append(f1_score(y[te], p, average="macro"))
    print(f"  {'BASELINE always-largest-industry':<40} "
          f"acc {np.mean(accs):>6.1%}  macro-F1 {np.mean(f1s):>6.3f}")


def main() -> None:
    for function in ("SOFTWARE_DATA", "SALES_BD"):
        X_prof, texts, y, companies = build(function)
        n_cls = len(np.unique(y))
        chance = pd.Series(y).value_counts(normalize=True).iloc[0]
        print(f"\n=== {function} ===")
        n_emp = len(np.unique(companies))
        print(f"  {len(y):,} postings, {n_emp:,} employers, "
              f"{n_cls} industries, {X_prof.shape[1]} concepts")
        print(f"  largest industry is {chance:.1%} of postings; "
              f"uniform chance is {1 / n_cls:.1%}")

        baseline_majority(X_prof, y, companies)
        tfidf = TfidfVectorizer(min_df=3, max_features=50_000, sublinear_tf=True)
        X_txt = tfidf.fit_transform(texts)

        for bal in (True, False):
            run(X_prof, y, companies, f"vocabulary profile ({X_prof.shape[1]}d)", bal)
            run(X_txt, y, companies, f"TF-IDF raw text ({X_txt.shape[1]}d)", bal)

        rng = np.random.default_rng(SEED)
        run(X_prof, rng.permutation(y), companies, "CONTROL: shuffled labels")


if __name__ == "__main__":
    main()
