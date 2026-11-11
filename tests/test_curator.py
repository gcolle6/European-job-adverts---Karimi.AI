"""The curator agent: detect a spelling of a known requirement, have it judged, apply it.

    python -m pytest tests/test_curator.py

A dictionary of three cores in memory, a store in a temp folder, the judge
mocked: no model, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from karimi_normalise import Dictionary, curator, dashboard, tester  # noqa: E402
from karimi_normalise.store import LocalStore, jf  # noqa: E402


def _dictionary():
    cores = pd.DataFrame({"req_space": ["", "", ""], "req_head_group": ["", "", ""],
                          "req_core": ["Redshift", "AWS", "data platform"],
                          "req_group": ["redshift", "aws", "data platform"],
                          "req_topic": ["redshift", "cloud", "data platform"], "n": [50, 400, 20]})
    titles = pd.DataFrame({"title_key": [], "title_group": [], "title_name": []})
    manifest = {"dict_version": "test", "group_threshold": 0.9, "topic_threshold": 0.8}
    def no_model(texts):
        raise ImportError("no embedding here: what is not known is `non_cercato`")
    d = Dictionary.from_tables(manifest, cores, np.eye(3, 4, dtype=np.float32), titles, {}, no_model)
    # a name by the dictionary's own capitals (`Dictionary.casing`), as a real one learns from its cores
    d.casing["en"] = {"redshift": "Redshift"}
    return d


def _run(*cores: str) -> list[dict]:
    return [{"id": "1", "requirements": [{"core": c, "space": "", "match": "nuovo"} for c in cores]}]


def _judge(reply: str, monkeypatch, tmp_path):
    monkeypatch.setattr(tester, "OUT", tmp_path / "tester")
    monkeypatch.setattr(tester, "CACHE", tmp_path / "tester" / "answers.jsonl")
    monkeypatch.setattr(tester, "_chat", lambda url, m, n: reply)


def test_detects_only_spellings_of_known_names():
    p = curator.detect(_run("Amazon Redshift", "Amazon Web Services (AWS)", "modern data platform",
                            "Snowflake"), _dictionary(), "j1")
    assert [(x["variant"], x["target_group"], x["detector"]) for x in p] == [
        ("Amazon Redshift", "redshift", "vendor_prefix"), ("Amazon Web Services (AWS)", "aws", "bracket")]
    assert all(x["detected_by"] == "curator" and x["job"] == "j1" for x in p)


def test_resolved_by_the_judge_then_applied(tmp_path, monkeypatch):
    store, d = LocalStore(tmp_path), _dictionary()
    assert [m.status for m in d.lookup_requirements([("", "Amazon Redshift")])] == ["non_cercato"]
    curator.save_detected(store, "j1", curator.detect(_run("Amazon Redshift"), d, "j1"))
    _judge("SAME\nthe same product, named with its vendor", monkeypatch, tmp_path)
    assert curator.resolve(store, "j1", "http://judge")["resolved"] == 1
    e = curator.log(store)[0]
    assert e["status"] == "resolved" and e["resolved_by"].startswith("curator+judge")
    assert curator.attach(d, store) == 1 and d.version == "test+a1"
    m = d.lookup_requirements([("", "Amazon Redshift"), ("", "amazon redshift")])
    assert [(x.group, x.status, x.by) for x in m] == [("redshift", "known", "curator")] * 2
    # a second run asks the judge nothing new
    curator.save_detected(store, "j2", curator.detect(_run("Amazon Redshift"), _dictionary(), "j2"))
    assert curator.resolve(store, "j2", "http://judge")["resolved"] == 0


def test_rejected_or_unjudged_is_never_applied(tmp_path, monkeypatch):
    store, d = LocalStore(tmp_path), _dictionary()
    curator.save_detected(store, "j1", curator.detect(_run("Amazon Redshift"), d, "j1"))
    assert curator.resolve(store, "j1", None)["pending"] == 1          # no judge: waits
    _judge("DIFFERENT\nnot the same", monkeypatch, tmp_path)
    assert curator.resolve(store, "j1", "http://judge")["rejected"] == 1
    assert curator.attach(d, store) == 0 and d.version == "test"
    assert [x["status"] for x in curator.log(store)] == ["detected", "rejected"]


def test_the_site_gets_the_log(tmp_path, monkeypatch):
    store, d = LocalStore(tmp_path), _dictionary()
    curator.save_detected(store, "j1", curator.detect(_run("Amazon Redshift"), d, "j1"))
    _judge("SAME\nsame", monkeypatch, tmp_path)
    curator.resolve(store, "j1", "http://judge")
    a = dashboard.aggregate(store, None, "test")["agents"]["curator"]
    assert a["totals"]["resolved"] == 1
    assert a["entries"][0] | {"detected_at": None, "resolved_at": None} == {
        "variant": "Amazon Redshift", "target_name": "Redshift", "detector": "vendor_prefix",
        "status": "resolved", "detected_by": "curator", "resolved_by": a["entries"][0]["resolved_by"],
        "job": "j1", "detected_at": None, "resolved_at": None}
    assert store.exists(jf("j1", "curator.json"))


def test_variants_propose_little_and_well():
    casing = {"java": "Java", "flink": "Flink", "linux": "Linux"}
    assert curator._variants("Java 17", casing) == [("version", "Java")]
    assert curator._variants("Apache Flink", casing) == [("vendor_prefix", "Flink")]
    assert curator._variants("SQL language", casing) == [("generic_suffix", "SQL")]
    # measured as wrong on the dictionary's own cores, 2026-11-11
    for core in ("ISO 27001", "Microsoft 365", "SOC 2", "Information Technology", "SAP ERP", "Oracle PaaS",
                 "Salesforce CRM management", "versions 8", "Java frameworks", "Power Platform"):
        assert curator._variants(core, casing) == [], core


def test_a_person_overrules_the_agent(tmp_path, monkeypatch):
    store, d = LocalStore(tmp_path), _dictionary()
    curator.save_detected(store, "j1", curator.detect(_run("Amazon Redshift"), d, "j1"))
    _judge("SAME\nsame", monkeypatch, tmp_path)
    curator.resolve(store, "j1", "http://judge")
    curator.overrule(store, "Amazon Redshift", why="checked by hand")
    assert curator.attach(d, store) == 0
    assert [e["status"] for e in curator.log(store)] == ["resolved", "rejected"]
