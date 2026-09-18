"""Detecting the language of a posting, to backfill the field where it is empty.

`language` is empty for roughly a sixth of the export, and the validation sample
is stratified by language — so the gap is not cosmetic: it decides which rows
can be sampled at all, and leaving those postings out would stratify on
"postings whose language the upstream pipeline happened to record", which is not
a property of the labour market.

The method is deliberately dull. Requirement text is short, so a model that
needs a paragraph is the wrong tool; function words are the most reliable signal
available at this length and they cost nothing. Every decision carries a margin
so that a weak call can be reported as unknown rather than guessed, and the
detector is scored against the postings that *do* carry a language before it is
trusted on the ones that do not — a detector is only as good as the control that
shows it agreeing where the answer is already known.

**What that control actually found, and it matters more than the backfill.**
Agreement is 86.5%, and the disagreement is not detector error. 1,026 of 3,175
postings recorded as `Français` carry `must_have` text that is plainly English
— `First successful experience in an AWS environment | Mastery of
infrastructure software` — while still naming French credentials (`Bac +3 to
Bac +5`, `BTS, DEUST, or BUT`). Postings recorded as `Polski` do the same. So
`language` is a property of the *original advertisement*, and `must_have` has
been partly translated into English upstream of this export.

Two consequences follow. Stratifying validation on `language` stratifies on the
language of a document nobody is labelling, so ``text_language`` — detected from
the requirement text itself — is the correct axis. And the corpus is
linguistically heterogeneous in a way no downstream model can see: some postings
retain their original wording and others have been rewritten in English, which
bears directly on the cross-lingual claims and on how much of the Hypothesis 2
residual is the upstream extractor's vocabulary rather than the employer's.
"""

from __future__ import annotations

import pandas as pd

from . import atomise as atom

# Function words are chosen for being frequent, short, and where possible
# distinctive. Overlaps between related languages are unavoidable — Dutch and
# German share `de`, `in`, `van` — so the score is a count over many markers
# rather than a lookup of any single one.
MARKERS: dict[str, set[str]] = {
    "English": {
        "the", "and", "with", "for", "you", "your", "are", "have", "will", "our",
        "experience", "skills", "knowledge", "ability", "work", "team", "strong",
        "good", "years", "of", "in", "to", "a", "an", "is", "as", "or", "we",
    },
    "Deutsch": {
        "und", "mit", "der", "die", "das", "den", "dem", "des", "ein", "eine",
        "einer", "im", "zu", "von", "fuer", "fur", "sie", "wir", "ist", "sind",
        "erfahrung", "kenntnisse", "sowie", "gute", "sehr", "oder", "auch",
        "abgeschlossenes", "studium", "bereitschaft", "faehigkeit",
    },
    "Français": {
        "et", "de", "des", "du", "la", "le", "les", "un", "une", "dans", "pour",
        "avec", "vous", "nous", "est", "sont", "experience", "connaissance",
        "maitrise", "capacite", "bonne", "sur", "au", "aux", "ou", "en", "chez",
        "ans", "esprit", "equipe", "gout",
    },
    "Italiano": {
        "e", "di", "del", "della", "dei", "delle", "il", "lo", "la", "gli", "le",
        "un", "una", "con", "per", "nel", "nella", "sono", "esperienza",
        "conoscenza", "capacita", "buona", "ottima", "su", "al", "alla", "che",
        "anni", "gestione",
    },
    "Español": {
        "y", "de", "del", "la", "el", "los", "las", "un", "una", "con", "para",
        "en", "es", "son", "experiencia", "conocimiento", "capacidad", "buena",
        "habilidades", "al", "por", "que", "anos", "gestion", "sobre", "como",
    },
    "Nederlands": {
        "en", "van", "de", "het", "een", "met", "voor", "je", "jij", "wij", "is",
        "zijn", "ervaring", "kennis", "vaardigheden", "goede", "sterke", "aan",
        "bij", "of", "die", "dat", "jaar", "werken", "ook", "naar",
    },
    "Português": {
        "e", "de", "do", "da", "dos", "das", "o", "a", "os", "as", "um", "uma",
        "com", "para", "em", "no", "na", "experiencia", "conhecimento",
        "capacidade", "boa", "competencias", "que", "anos", "gestao", "ao",
    },
    "Svenska": {
        "och", "av", "en", "ett", "med", "for", "att", "du", "vi", "ar", "som",
        "erfarenhet", "kunskap", "goda", "starka", "till", "eller", "pa", "har",
        "arbeta", "ar", "inom",
    },
}

# Words that appear in several of the above. Counted for no language, so that a
# posting is decided on what distinguishes it rather than on shared filler.
_AMBIGUOUS = {w for w in set().union(*MARKERS.values())
              if sum(w in m for m in MARKERS.values()) >= 3}

DISTINCTIVE = {lang: markers - _AMBIGUOUS for lang, markers in MARKERS.items()}

# A call needs this many distinctive hits, and this much of a lead over the
# runner-up, or it is reported as unknown rather than forced.
MIN_HITS = 2
MIN_MARGIN = 1


def detect(text: str) -> tuple[str | None, int, int]:
    """Return ``(language, hits, margin)``; language is None when undecided."""
    tokens = set(atom.normalise(text or "").split())
    if not tokens:
        return None, 0, 0

    scores = sorted(
        ((len(tokens & markers), lang) for lang, markers in DISTINCTIVE.items()),
        reverse=True,
    )
    (top_hits, top_lang), (second_hits, _) = scores[0], scores[1]
    margin = top_hits - second_hits
    if top_hits < MIN_HITS or margin < MIN_MARGIN:
        return None, top_hits, margin
    return top_lang, top_hits, margin


def detect_series(text: pd.Series) -> pd.DataFrame:
    """Detect over a column, returning language, hits and margin."""
    out = [detect(t) for t in text.fillna("").astype(str)]
    return pd.DataFrame(out, index=text.index, columns=["detected", "hits", "margin"])


def validate(df: pd.DataFrame, text_col: str = "must_have") -> dict:
    """Score the detector on the postings that already carry a language.

    The control that licenses the backfill. Agreement is reported over the rows
    the detector was willing to decide, alongside how many it declined, because
    a detector that abstains on a third of the corpus is not usable for
    stratification however accurate it is on the rest.
    """
    known = df[df["language"].astype(str).str.strip() != ""].copy()
    det = detect_series(known[text_col])
    known = known.join(det)

    decided = known[known["detected"].notna()]
    agree = (decided["detected"] == decided["language"]).mean() if len(decided) else 0.0

    per_lang = (
        decided.assign(ok=decided["detected"] == decided["language"])
        .groupby("language")["ok"]
        .agg(["mean", "size"])
        .round(3)
        .sort_values("size", ascending=False)
    )
    return {
        "n_known": len(known),
        "n_decided": len(decided),
        "decision_rate": round(len(decided) / len(known), 3) if len(known) else 0.0,
        "agreement": round(float(agree), 3),
        "by_language": per_lang,
        "confusion": pd.crosstab(decided["language"], decided["detected"]),
    }


def backfill(df: pd.DataFrame, text_col: str = "must_have") -> pd.DataFrame:
    """Add ``text_language``, ``language_filled``, ``language_source`` and a flag.

    Three columns rather than one, because the export conflates two things:

    * ``text_language`` — the language of the requirement text, detected. This
      is the axis to stratify validation on, since it describes what a labeller
      is actually reading.
    * ``language_filled`` — the recorded language, with the empty sixth filled
      in by detection. Use it to describe the *market* a posting came from.
    * ``translated_upstream`` — recorded and detected disagree, so the text has
      been rewritten in another language before it reached us.

    The original column is never overwritten, and ``language_source`` says
    whether a row was recorded or inferred, so the write-up can state the mix
    instead of quietly merging the two.
    """
    out = df.copy()
    recorded = out["language"].astype(str).str.strip()
    det = detect_series(out[text_col])

    out["text_language"] = det["detected"].fillna("(undetected)")
    out["language_filled"] = recorded.where(recorded != "", det["detected"])
    out["language_filled"] = out["language_filled"].fillna("(undetected)")
    out["language_source"] = "recorded"
    out.loc[recorded == "", "language_source"] = "detected"
    out.loc[(recorded == "") & det["detected"].isna(), "language_source"] = "undetected"
    out["translated_upstream"] = (
        (recorded != "") & det["detected"].notna() & (recorded != det["detected"])
    )
    return out
