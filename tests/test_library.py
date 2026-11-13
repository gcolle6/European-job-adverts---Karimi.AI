"""The checks every change must pass before it is merged (phase 2).

    python -m pytest tests

What each one guards:

* the pattern cases (`New project/test_patterns.py`) — a rule that fixes one
  pattern and silently breaks another;
* the fingerprint — a rule changed without a new `RULES_VERSION`;
* the translation settings — the library translating differently from the
  batch the measures come from;
* the dictionary — an edited dictionary loaded as if it were the frozen one.

The measured scores (`score_counts.py`, `score_pairs.py`) join CI in phase 2,
as blocking gates with thresholds fixed before they run.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "New project"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(NEW))

from karimi_normalise import Dictionary, split_posting, versions  # noqa: E402
from karimi_normalise import translate as tr  # noqa: E402
from karimi_normalise.freeze import STORE  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, NEW / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_patterns():
    assert _load("test_patterns").main() == 0


def test_fingerprint_matches_version():
    got = versions.fingerprint()
    assert got == versions.RULES_FINGERPRINT, (
        f"rule sources changed: bump RULES_VERSION, add a line to karimi_normalise/CHANGELOG.md, "
        f"and set RULES_FINGERPRINT = {got!r}")


def test_translation_settings_match_batch():
    tm = _load("translate_must_have")
    assert (tr.CODE, tr.MODEL_FOR, tr.NUM_BEAMS, tr.BATCH) == (tm.CODE, tm.MODEL_FOR, tm.NUM_BEAMS, tm.BATCH)


def test_split_carries_versions():
    reqs = split_posting(["Experience with Docker and Kubernetes"], translate=False)
    assert [r.core for r in reqs] == ["Docker", "Kubernetes"]
    assert all(r.rules_version == versions.RULES_VERSION for r in reqs)


def _any_dictionary() -> Path | None:
    found = sorted(STORE.glob("*/manifest.json")) if STORE.exists() else []
    return found[-1].parent if found else None


@pytest.mark.skipif(_any_dictionary() is None, reason="no frozen dictionary on this machine")
def test_edited_dictionary_is_refused(tmp_path):
    src = _any_dictionary()
    dst = tmp_path / src.name
    shutil.copytree(src, dst)
    acr = json.loads((dst / "title_acronyms.json").read_text(encoding="utf-8"))
    acr["xyz"] = "edited by hand"
    (dst / "title_acronyms.json").write_text(json.dumps(acr), encoding="utf-8")
    with pytest.raises(ValueError, match="edited in place"):
        Dictionary(dst)


def test_run_light_reads_only_the_bad_side():
    from karimi_normalise.metrics import _light
    pct = {"1": 0.10, "5": 0.15, "50": 0.18, "95": 0.21, "99": 0.23}
    assert _light(0.18, pct, "high") == "green"
    assert _light(0.22, pct, "high") == "yellow"
    assert _light(0.30, pct, "high") == "red"
    assert _light(0.01, pct, "high") == "green"   # fewer `nuovo` than usual is no problem
    assert _light(0.01, pct, "low") == "red"


def test_run_smaller_than_the_reference_is_not_read():
    from types import SimpleNamespace

    from karimi_normalise.metrics import run_report
    pct = {"1": 0.0, "5": 0.0, "50": 0.02, "95": 0.05, "99": 0.06}
    ref = {"sizes": [10, 30], "signals": {"share_one_word": {"by_size": {"10": pct, "30": pct}}}}
    posting = split_posting(["Python", "Experience with SQL and Spark"])
    out = run_report([posting], dictionary=SimpleNamespace(reference=ref, version="x"))
    assert out["signals"]["share_one_word"]["light"] == "grey" and out["overall"] == "green"
    out = run_report([posting] * 10, dictionary=SimpleNamespace(reference=ref, version="x"))
    assert out["signals"]["share_one_word"]["light"] == "red" and out["overall"] == "red"


def test_cache_key_matches_batch(tmp_path):
    tm = _load("translate_must_have")
    assert tr.cache_key("de", "Teamfähigkeit") == tm._key("de", "Teamfähigkeit")
    c = tr.TranslationCache(tmp_path / "c.jsonl")
    c.put({("de", "Teamfähigkeit"): "Team skills"})
    again = tr.TranslationCache(tmp_path / "c.jsonl")
    # a cached item is not translated again: no model is loaded for it
    assert tr.translate([("de", "Teamfähigkeit")], again) == {("de", "Teamfähigkeit"): "Team skills"}


def test_process_returns_requirements_titles_and_report():
    from karimi_normalise import process
    out = process([{"id": "x", "must_have": ["Experience with Docker and Kubernetes"],
                    "title": "Senior Data Engineer"}], translate=False)
    p = out["postings"][0]
    assert p["id"] == "x" and len(p["requirements"]) == 2 and p["title"].title_role == "Data Engineer"
    assert out["report"]["summary"]["requirements"] == 2


def _tiny_dictionary(encoder=None):
    import numpy as np
    import pandas as pd
    cores = pd.DataFrame({"req_head_group": ["experience"], "req_core": ["Docker"],
                          "req_group": ["experience: docker"], "req_topic": ["experience: docker"]})
    titles = pd.DataFrame({"title_role": ["Full Stack Engineer"], "title_key": ["engineer full stack"],
                           "title_group": ["engineer full stack"], "title_name": ["Full Stack Engineer"]})
    manifest = {"dict_version": "test", "group_threshold": 0.90, "topic_threshold": 0.80}
    return Dictionary.from_tables(manifest, cores, np.ones((1, 4), dtype="float32") / 2, titles, {}, encoder)


def test_caller_translations_and_translator():
    from karimi_normalise import process
    out = process([{"must_have": ["Erfahrung mit Docker und Kubernetes"],
                    "must_have_english": ["Experience with Docker and Kubernetes"]}])
    assert [r.translated_by for r in out["postings"][0]["requirements"]] == ["given", "given"]

    def fake(pairs):
        return {p: "Experience with Docker and Kubernetes" for p in pairs}
    out = process([{"must_have": ["Erfahrung mit Docker und Kubernetes"]}], translator=fake)
    assert {r.translated_by for r in out["postings"][0]["requirements"]} == {"fake"}


def test_missing_embedding_is_not_searched_not_new():
    def missing(texts):
        raise ImportError("sentence-transformers")
    d = _tiny_dictionary(missing)
    got = d.lookup_requirements([("experience", "Docker"), ("experience", "Kubernetes")])
    assert [m.status for m in got] == ["known", "non_cercato"]


def test_title_variant_is_found():
    d = _tiny_dictionary()
    assert d.lookup_title("Full Stack Engineer")[3] == "known"
    assert d.lookup_title("Fullstack Engineer")[1:] == ("engineer full stack", "Full Stack Engineer", "variant")
    assert d.lookup_title("Data Scientist")[3] == "nuovo"
