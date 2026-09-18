"""Multilingual embedding, and the check that has to pass before it is trusted.

Every cross-country statement this project makes rests on one assumption: that a
requirement written in Dutch lands near the same requirement written in Italian.
If that fails, every downstream cluster is an artefact of language rather than of
meaning, and nothing later in the pipeline would reveal it.

So the alignment check runs *first*, on sixty phrases, before the full corpus is
embedded. It uses two controls:

* **positive pairs** — the same concept in two different languages, which should
  be close;
* **negative pairs** — different concepts in two different languages, which
  should not.

The positive score alone proves nothing. A model that maps everything to nearly
the same vector scores high on positives and is useless; only the separation
between the two distributions says the space carries meaning.

The phrases are real requirement text drawn from the corpus, not invented
translations, so the check measures the model on the register it will actually
face — terse, abbreviated, recruitment-specific.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Open-source, downloaded once and run locally — no data leaves the machine.
# Fast, 384-dimensional, covers every language in the export. Provisional pending
# academic review; `alignment_check` is the instrument for judging a replacement.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Candidates compared on the alignment check. All are open-source and run locally.
# `prefix` is required by the E5 family, which is trained with instruction prefixes.
CANDIDATE_MODELS = {
    "paraphrase-multilingual-MiniLM-L12-v2": {
        "id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dims": 384, "params_m": 118, "licence": "Apache-2.0", "prefix": "",
    },
    "paraphrase-multilingual-mpnet-base-v2": {
        "id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "dims": 768, "params_m": 278, "licence": "Apache-2.0", "prefix": "",
    },
    "multilingual-e5-base": {
        "id": "intfloat/multilingual-e5-base",
        "dims": 768, "params_m": 278, "licence": "MIT", "prefix": "query: ",
    },
    "multilingual-e5-large": {
        "id": "intfloat/multilingual-e5-large",
        "dims": 1024, "params_m": 560, "licence": "MIT", "prefix": "query: ",
    },
}

LANGUAGES = ["English", "Deutsch", "Français", "Italiano", "Español", "Nederlands"]

# Ten concepts, each in six languages, taken verbatim from the corpus.
# The count after each phrase is how often it occurs in the analysis base.
TRANSLATION_PAIRS: dict[str, dict[str, str]] = {
    "english fluency": {
        "English": "fluency in english",
        "Deutsch": "englischkenntnisse",
        "Français": "maitrise de l anglais",
        "Italiano": "buona conoscenza della lingua inglese",
        "Español": "nivel alto de ingles",
        "Nederlands": "vloeiend in nederlands en engels",
    },
    "teamwork": {
        "English": "team player",
        "Deutsch": "teamfahigkeit",
        "Français": "capacite a travailler en equipe",
        "Italiano": "predisposizione al lavoro di squadra",
        "Español": "trabajo en equipo",
        "Nederlands": "teamplayer",
    },
    "driving licence": {
        "English": "full uk driving licence",
        "Deutsch": "fuhrerschein der klasse b",
        "Français": "permis b valide indispensable boite manuelle",
        "Italiano": "possesso della patente b",
        "Español": "carnet de conducir",
        "Nederlands": "rijbewijs b",
    },
    "communication": {
        "English": "strong communication skills",
        "Deutsch": "kommunikationsstarke",
        "Français": "aisance relationnelle",
        "Italiano": "buone capacita comunicative",
        "Español": "excelentes habilidades de comunicacion",
        "Nederlands": "goede communicatieve vaardigheden",
    },
    "autonomy": {
        "English": "ability to work independently",
        "Deutsch": "selbststandige arbeitsweise",
        "Français": "autonomie",
        "Italiano": "capacita di lavorare in autonomia",
        "Español": "autonomia",
        "Nederlands": "ondernemend en zelfstandig",
    },
    "degree": {
        "English": "bachelor s degree",
        "Deutsch": "abgeschlossenes studium der informatik",
        "Français": "bac+5",
        "Italiano": "laurea in informatica",
        "Español": "titulacion universitaria en similar",
        "Nederlands": "hbo werk en denkniveau",
    },
    "ms office": {
        "English": "proficiency in ms office",
        "Deutsch": "sicherer umgang mit ms office",
        "Français": "maitrise du pack office",
        "Italiano": "buona conoscenza del pacchetto office",
        "Español": "dominio del paquete office",
        "Nederlands": "zeer goede kennis van ms office word excel outlook",
    },
    "customer focus": {
        "English": "customer oriented",
        "Deutsch": "kundenorientierung",
        "Français": "sens du service client",
        "Italiano": "orientamento al cliente",
        "Español": "orientacion al cliente",
        "Nederlands": "klantgericht",
    },
    "problem solving": {
        "English": "problem solving skills",
        "Deutsch": "losungsorientierte arbeitsweise",
        "Français": "competences en resolution de problemes",
        "Italiano": "attitudine al problem solving",
        "Español": "resolucion de problemas",
        "Nederlands": "probleemoplossend vermogen",
    },
    "flexibility": {
        "English": "flexibility",
        "Deutsch": "flexibilitat",
        "Français": "flexibilite",
        "Italiano": "flessibilita",
        "Español": "flexibilidad",
        "Nederlands": "flexibiliteit",
    },
}


def load_model(name: str = DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name)


def encode(model, phrases: list[str], batch_size: int = 256) -> np.ndarray:
    """L2-normalised embeddings, so a dot product is the cosine similarity."""
    return model.encode(
        phrases,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def embed_corpus(phrases: list[str], out_path, model=None, batch_size: int = 256):
    """Embed the unique phrase vocabulary once and persist it.

    Keyed by phrase, so Week 2 never re-embeds and a rerun costs nothing.
    Only run this after ``alignment_check`` has passed.
    """
    model = model or load_model()
    vectors = encode(model, phrases, batch_size=batch_size)
    np.savez_compressed(out_path, phrases=np.array(phrases, dtype=object), vectors=vectors)
    return vectors


def top_up_corpus(phrases: list[str], path, model=None, batch_size: int = 256) -> dict:
    """Embed only the phrases not already in the store, and append them.

    A rebuild would re-encode 127,054 phrases that have not changed, and the
    store is the one expensive artefact in the project. Any change to the
    splitter alters the atom *strings*, so coverage drops without the vocabulary
    really turning over — after this week's rule work only 60% of the needed
    phrases were still present, and re-encoding everything would have cost
    twenty minutes to reproduce vectors that were already correct.

    Phrases no longer used are left in place rather than pruned. They cost disk
    and nothing else, and keeping them means reverting a splitter change does
    not trigger another full pass.
    """
    path = Path(path)
    if path.exists():
        known, vectors = load_corpus(path)
    else:
        known, vectors = [], np.zeros((0, 384), dtype="float32")

    have = set(known)
    missing = [p for p in dict.fromkeys(phrases) if p not in have]
    if not missing:
        return {"already": len(have), "added": 0, "total": len(have),
                "coverage": 1.0, "path": str(path)}

    model = model or load_model()
    new_vecs = encode(model, missing, batch_size=batch_size)

    all_phrases = known + missing
    all_vectors = np.vstack([vectors, new_vecs]) if len(vectors) else new_vecs
    np.savez_compressed(path, phrases=np.array(all_phrases, dtype=object),
                        vectors=all_vectors)

    wanted = set(phrases)
    return {"already": len(have), "added": len(missing), "total": len(all_phrases),
            "coverage": round(len(wanted & set(all_phrases)) / max(len(wanted), 1), 4),
            "stale": len(set(all_phrases) - wanted), "path": str(path)}


def load_corpus(path) -> tuple[list[str], np.ndarray]:
    data = np.load(path, allow_pickle=True)
    return list(data["phrases"]), data["vectors"]


def neighbour_language_mix(
    phrases: list[str], vectors: np.ndarray, phrase_language: dict[str, str],
    k: int = 10, sample_size: int = 800, seed: int = 20260830,
) -> pd.DataFrame:
    """Do a phrase's nearest neighbours share its language?

    ``alignment_check`` excludes same-language candidates by construction, which
    is the right way to test the model but not the situation clustering faces.
    Here nothing is excluded: every phrase competes with the morphological
    variants of its own language, which are numerous and very close.

    Returned per language: the observed same-language share of neighbours, the
    corpus share of that language (the share expected if neighbours were drawn at
    random), and their ratio. A ratio near 1 means language is not structuring the
    neighbourhood; a large ratio means Week 2 clustering risks recovering
    languages rather than concepts.
    """
    index = {p: i for i, p in enumerate(phrases)}
    labels = np.array([phrase_language.get(p) for p in phrases], dtype=object)
    known = np.array([l is not None for l in labels])

    rng = np.random.default_rng(seed)
    pool = np.array([index[p] for p in phrase_language if p in index])
    sample = rng.choice(pool, size=min(sample_size, len(pool)), replace=False)

    rows = []
    for start in range(0, len(sample), 100):
        block = sample[start:start + 100]
        sims = vectors @ vectors[block].T
        for col, i in enumerate(block):
            s = sims[:, col].copy()
            s[i] = -1
            cand = np.argpartition(-s, k * 4)[: k * 4]
            cand = cand[np.argsort(-s[cand])]
            cand = [j for j in cand if known[j]][:k]
            if cand:
                rows.append({
                    "language": labels[i],
                    "same_share": sum(labels[j] == labels[i] for j in cand) / len(cand),
                })
    return pd.DataFrame(rows)


def compare_models(names: list[str] | None = None, pairs: dict | None = None) -> pd.DataFrame:
    """Run the alignment check across candidate models and rank them.

    The decision is made on retrieval accuracy first and separation second: a
    model that places translations nearest each other is doing the job, and a
    wide gap to the negative control says it is doing it for the right reason.
    """
    names = names or list(CANDIDATE_MODELS)
    rows = []
    for name in names:
        spec = CANDIDATE_MODELS[name]
        model = load_model(spec["id"])
        result = alignment_check(model, pairs, prefix=spec["prefix"])
        rows.append({
            "model": name,
            "dims": spec["dims"],
            "params_m": spec["params_m"],
            "licence": spec["licence"],
            "retrieval": round(result["retrieval_accuracy"] * 100, 1),
            "positive_mean": round(result["positive_mean"], 3),
            "negative_mean": round(result["negative_mean"], 3),
            "separation": round(result["separation"], 3),
            "cohens_d": round(result["cohens_d"], 2),
            "auc": round(result["auc"], 3),
        })
    return pd.DataFrame(rows).sort_values(["retrieval", "separation"], ascending=False)


def alignment_check(model=None, pairs: dict | None = None, prefix: str = "") -> dict:
    """Do translations of one requirement land near each other?

    Returns the positive and negative similarity distributions, their separation,
    and cross-lingual retrieval accuracy — for each phrase, whether its nearest
    neighbour in another language is the same concept. Retrieval accuracy is the
    decisive number: similarity levels are hard to interpret in the abstract,
    but a nearest neighbour is either the right concept or it is not.
    """
    pairs = pairs or TRANSLATION_PAIRS
    model = model or load_model()

    concepts, langs, texts = [], [], []
    for concept, by_lang in pairs.items():
        for lang, phrase in by_lang.items():
            concepts.append(concept)
            langs.append(lang)
            texts.append(phrase)

    vectors = encode(model, [prefix + t for t in texts])
    sim = vectors @ vectors.T
    concepts_arr = np.array(concepts)
    langs_arr = np.array(langs)

    n = len(texts)
    same_concept = concepts_arr[:, None] == concepts_arr[None, :]
    same_language = langs_arr[:, None] == langs_arr[None, :]
    off_diagonal = ~np.eye(n, dtype=bool)

    positive_mask = same_concept & ~same_language & off_diagonal
    negative_mask = ~same_concept & ~same_language & off_diagonal

    positives = sim[positive_mask]
    negatives = sim[negative_mask]

    # cross-lingual retrieval: nearest neighbour outside the phrase's own language
    correct = []
    for i in range(n):
        candidates = np.where(langs_arr != langs_arr[i])[0]
        nearest = candidates[np.argmax(sim[i, candidates])]
        correct.append(concepts_arr[nearest] == concepts_arr[i])
    correct = np.array(correct)

    # per-concept retrieval, to expose a concept that fails on its own
    per_concept = (
        pd.DataFrame({"concept": concepts, "language": langs, "correct": correct})
        .groupby("concept")["correct"]
        .mean()
        .sort_values()
    )
    per_language = (
        pd.DataFrame({"language": langs, "correct": correct})
        .groupby("language")["correct"]
        .mean()
        .sort_values()
    )

    # Raw cosine separation is scale-dependent: a model that packs every vector
    # into a narrow band looks bad on it even when the structure is intact.
    # Cohen's d and AUC standardise for that, so models on different scales are
    # actually comparable.
    pooled_sd = np.sqrt((positives.var(ddof=1) + negatives.var(ddof=1)) / 2)
    cohens_d = (positives.mean() - negatives.mean()) / pooled_sd if pooled_sd else 0.0
    # AUC = probability a random positive pair scores above a random negative one
    auc = float((positives[:, None] > negatives[None, :]).mean())

    return {
        "n_phrases": n,
        "n_positive_pairs": int(positive_mask.sum() // 2),
        "n_negative_pairs": int(negative_mask.sum() // 2),
        "cohens_d": float(cohens_d),
        "auc": auc,
        "positive_mean": float(positives.mean()),
        "positive_min": float(positives.min()),
        "negative_mean": float(negatives.mean()),
        "negative_p95": float(np.percentile(negatives, 95)),
        "separation": float(positives.mean() - negatives.mean()),
        "retrieval_accuracy": float(correct.mean()),
        "per_concept": per_concept,
        "per_language": per_language,
        "similarity": sim,
        "labels": list(zip(concepts, langs, texts)),
    }
