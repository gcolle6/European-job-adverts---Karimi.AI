"""Six-way classification in the embedding space, and its arbitration with the lexicon.

The lexicon in ``classify`` recognises *names*. Five of the six types name
things — a tool, a language, a certificate — so a vocabulary works on them. The
sixth does not: **domain knowledge is written as description**, and on the
labelled sample the lexicon placed 1 of 31 domain items correctly. No amount of
added vocabulary fixes that, because there is no word to add.

Embedding similarity does not depend on naming, so it reaches those items. The
two methods are therefore combined by *type* rather than by confidence:

* Where the lexicon fires on a marker that is nearly unambiguous — a named
  language, a named certificate — it wins. These are the types embeddings
  confuse, since `fluent in German` and `knowledge of German law` sit close
  together in vector space.
* Everywhere else the embedding decides, and the lexicon is not consulted.

That asymmetry is the point. A hybrid that simply lets the lexicon go first is
*worse* on domain knowledge than embeddings alone, because the lexicon does not
abstain on those items — it actively claims them as `technical` on the strength
of an incidental noun. Precedence has to be earned per type, and it is measured
on the development half of the labelled sample only.

Prototypes rather than nearest neighbours: with roughly a dozen labelled
examples per type, a centroid is far more stable than a k-NN vote, and the seed
phrases below are written by hand so the method needs no labels at all to run.
"""

from __future__ import annotations

import numpy as np

from . import atomise as atom
from . import config

# Seed phrases defining each type. Deliberately multilingual — the embedding
# space is shared, but a type seeded only in English drifts towards English
# phrasing and then the classifier's accuracy tracks language rather than type.
# These describe the *kind* of requirement, not any particular one.
PROTOTYPES: dict[str, list[str]] = {
    "technical": [
        "experience with Python and SQL",
        "proficiency in Java programming",
        "knowledge of Docker and Kubernetes",
        "data modelling and ETL pipelines",
        "Erfahrung mit Kubernetes und Docker",
        "Kenntnisse in SQL und Datenbanken",
        "maîtrise de Python et des bases de données",
        "connaissance des outils de développement",
        "esperienza con framework di sviluppo software",
        "conocimiento de herramientas de programación",
        "ervaring met cloud infrastructuur",
        "hands-on experience building software systems",
    ],
    "soft": [
        "excellent communication skills",
        "ability to work independently and take initiative",
        "team player with a positive attitude",
        "attention to detail and analytical mindset",
        "ausgeprägte Kommunikationsfähigkeit",
        "selbstständige und strukturierte Arbeitsweise",
        "esprit d équipe et bon relationnel",
        "capacité à travailler en autonomie",
        "ottime capacità relazionali e di squadra",
        "habilidades de comunicación y trabajo en equipo",
        "goede communicatieve vaardigheden",
        "genuine interest and curiosity",
    ],
    "domain": [
        "understanding of the financial services industry",
        "knowledge of GDPR and data protection regulation",
        "familiarity with medical device regulatory requirements",
        "experience in the retail sector",
        "understanding of insurance underwriting processes",
        "Kenntnisse der regulatorischen Anforderungen im Bankwesen",
        "Verständnis für die Automobilbranche",
        "connaissance du secteur bancaire et de la réglementation",
        "conoscenza del settore farmaceutico",
        "conocimiento del sector energético",
        "kennis van de zorgsector",
        "experience with capital markets and trading workflows",
    ],
    "credential": [
        "Bachelor's degree in Computer Science",
        "Master's degree or equivalent qualification",
        "PhD in a scientific discipline",
        "ITIL certification",
        "valid driving licence",
        "abgeschlossenes Studium der Informatik",
        "erfolgreich abgeschlossene Berufsausbildung",
        "diplôme d ingénieur ou équivalent",
        "laurea in ingegneria",
        "titulación universitaria",
        "afgeronde opleiding HBO of WO",
        "professional accreditation or chartered status",
    ],
    "language": [
        "fluent in English",
        "fluency in English both written and spoken",
        "German at C1 level",
        "good knowledge of the Dutch language",
        "verhandlungssichere Deutschkenntnisse",
        "sehr gute Englischkenntnisse in Wort und Schrift",
        "maîtrise du français et de l anglais",
        "buona conoscenza della lingua inglese",
        "nivel alto de inglés",
        "uitstekende kennis van het Nederlands",
        "native level Spanish speaker",
        "English is our working language",
    ],
    "availability": [
        "willingness to travel frequently",
        "available to work weekends and shifts",
        "based in Berlin or willing to relocate",
        "on site presence three days per week",
        "Reisebereitschaft innerhalb Deutschlands",
        "Bereitschaft zu Schichtarbeit",
        "disponibilité pour des déplacements réguliers",
        "disponibilità a trasferte sul territorio nazionale",
        "disponibilidad para viajar",
        "bereidheid om te reizen",
        "full time availability",
        "able to start immediately",
    ],
}

# Types where a lexicon hit is trusted over the embedding. Both are recognised
# by markers that are close to unambiguous — a named natural language, a named
# qualification — and both are types the embedding space genuinely confuses:
# `fluent in German` and `knowledge of German employment law` are neighbours.
LEXICON_PRECEDENCE = ("language", "credential")


def fit_prototypes(model=None, prototypes: dict[str, list[str]] | None = None):
    """Encode the seed phrases and return one unit-norm centroid per type.

    Returns the type order alongside the matrix so that a caller never has to
    assume dictionary ordering matches the rows.
    """
    from . import embed

    prototypes = prototypes or PROTOTYPES
    model = model or embed.load_model()

    types = list(prototypes)
    centroids = []
    for t in types:
        vecs = embed.encode(model, prototypes[t])
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        c = vecs.mean(axis=0)
        centroids.append(c / np.linalg.norm(c))
    return types, np.vstack(centroids)


def classify_vectors(vectors: np.ndarray, types: list[str], centroids: np.ndarray) -> tuple[list[str | None], np.ndarray, np.ndarray]:
    """Assign each row to its nearest type centroid.

    Abstains — returns None — when the best similarity is weak or the margin
    over the runner-up is thin. Abstention is reported rather than hidden,
    because an accuracy computed only over assigned items can be improved by
    abstaining more, and would then say nothing about the corpus.
    """
    v = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    sims = v @ centroids.T

    order = np.argsort(-sims, axis=1)
    best = sims[np.arange(len(sims)), order[:, 0]]
    second = sims[np.arange(len(sims)), order[:, 1]]
    margin = best - second

    out: list[str | None] = []
    for i in range(len(sims)):
        if best[i] < config.EMBED_MIN_SIMILARITY or margin[i] < config.EMBED_MIN_MARGIN:
            out.append(None)
        else:
            out.append(types[order[i, 0]])
    return out, best, margin


def classify_hybrid(phrases: list[str], model=None, types=None, centroids=None) -> list[str | None]:
    """Lexicon where it is trusted, embedding everywhere else.

    See the module docstring for why precedence is per type rather than global.
    """
    from . import classify as lex
    from . import embed

    model = model or embed.load_model()
    if centroids is None:
        types, centroids = fit_prototypes(model)

    vectors = embed.encode(model, phrases)
    emb, _, _ = classify_vectors(vectors, types, centroids)

    out: list[str | None] = []
    for phrase, e in zip(phrases, emb):
        hit = lex.classify(atom.normalise(phrase))
        out.append(hit if hit in LEXICON_PRECEDENCE else (e if e is not None else hit))
    return out
