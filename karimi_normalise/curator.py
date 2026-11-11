"""The curator agent: spellings of a known requirement, found in runs and joined to it.

Asked for by the user on 2026-11-11: the dictionary is frozen and its list of
product spellings (`normalise_req.ALIASES`) is written by hand, so `Amazon
Redshift` stays `nuovo` beside the known `Redshift` until someone notices. The
curator notices, the judge confirms, and the next run finds it. Three steps,
each where what it needs is:

1. **detect** — in the API and the batch job, at the end of every run, where
   the dictionary is: every requirement the run could not place (`nuovo`,
   `topic`) is tried against the dictionary in a few written-down ways
   (`DETECTORS`). A hit is a proposal, saved with the run (`curator.json`);
2. **resolve** — in the check job, where the judge is: each proposal is put to
   the judge as a pair. SAME -> ``resolved``, DIFFERENT -> ``rejected``, no
   judge -> stays ``detected``. Written once to ``curator/aliases.jsonl``,
   outside `jobs/` so it outlives the 30 days of a run;
3. **apply** — the API and the batch job read the resolved entries
   (`attach`) and the dictionary finds a variant as its target, marked
   ``match_by = curator`` and with the dictionary version ``0.2.0+a<n>``:
   every output says which entries made it.

Every entry says what found it (``detected_by``), what decided it
(``resolved_by``), on which run and when. The detectors only ever propose a
core that is ALREADY in the dictionary, in the same space, so the agent can
join a spelling to a group and never make or merge groups: that stays a new
freeze, a person's call.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from karimi import normalise_req as nr

from .store import jf, now, read_json, write_json

AGENT = "curator"
LOG = "curator/aliases.jsonl"
MAX_PER_RUN = 40          # proposals judged per run: the judge's time is the cost

# Vendor words a product is written with and without (`Amazon Redshift`, `Redshift`).
_VENDOR = re.compile(r"^(?:amazon|aws|microsoft|ms|google|gcp|apache|oracle|ibm|sap|adobe|atlassian|"
                     r"hashicorp|red\s?hat|salesforce|meta|elastic|mongodb|jetbrains|cisco|vmware)\s+(?=\S)", re.I)
# A version after a name (`Python 3`, `Angular 15+`, `Java 17`, `Vue 3.x`).
_VERSION = re.compile(r"\s+v?\d+(?:\.\d+|\.x)*\+?$", re.I)
# A generic word after a name (`Jira software`, `Terraform tool`).
# Not `frameworks`, `solutions`, `ecosystem`: `Java frameworks` are not Java.
_GENERIC = re.compile(r"\s+(?:software|tools?|platforms?|technology|services?|language|environment)$", re.I)
_BRACKET = re.compile(r"^(?P<out>.+?)\s*\((?P<in>[^()]+)\)$")


# What a vendor's name stands before without being the product: `SAP ERP` is not `ERP`.
_CATEGORY = {"erp", "crm", "sql", "bi", "ai", "ml", "api", "apis", "it", "ui", "ux", "soc", "iso", "qa", "hr",
             "seo", "etl", "os", "db", "iot", "nlp", "analytics", "project", "sheets", "workspace", "office",
             "cloud", "security", "data", "services", "tools", "platform", "paas", "saas", "iaas", "pm",
             "management", "development", "implementation", "administration", "rdbms", "dbms", "erp"}


def _is_name(form: str, casing: dict[str, str]) -> bool:
    """A product name, not a word: a capital inside a word, a digit, an acronym, or a word the
    dictionary always writes with a capital (`Jira`, `Linux`, from `Dictionary.casing`)."""
    for tok in form.split():
        if any(ch.isdigit() for ch in tok) or any(ch.isupper() for ch in tok[1:]):
            return True
        if casing.get(tok.lower(), "")[:1].isupper():
            return True
    return False


def _variants(core: str, casing: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(detector, form) the core might be a spelling of, each written to propose little and well.

    Measured 2026-11-11 on the dictionary's own cores: looser forms proposed
    1,257 joins, among them `Information Technology` -> `Information`, `ISO
    27001` -> `ISO`, `Microsoft 365` -> `Microsoft`, `SAP ERP` -> `ERP`."""
    casing = casing or {}
    out = []
    v = _VENDOR.sub("", core)
    # what is left must start with a product, not a category: not `Oracle PaaS`
    # -> `PaaS`, `Salesforce CRM management` -> `CRM management`
    if v != core and v.split()[0].lower() not in _CATEGORY and re.search(r"[^\W\d_]", v.split()[0]) \
            and _is_name(v.split()[0], casing):
        out.append(("vendor_prefix", v))
    m = _VERSION.search(core)
    if m:
        v = core[: m.start()]
        number = int(re.search(r"\d+", m.group(0)).group(0))
        # `Java 17`, `Python 3`; not `ISO 27001`, `Microsoft 365`, `SOC 2`
        if number < 100 and len(v) >= 4 and not v.isupper() and " " not in v and _is_name(v, casing):
            out.append(("version", v))
    m = _GENERIC.search(core)
    if m and m.group(0).strip().islower():
        # the generic word in lower case is not part of the name: `SQL language`
        # yes, `Spring Framework`, `Power Platform`, `Burp Suite` no
        v = core[: m.start()]
        if " " not in v and _is_name(v, casing):
            out.append(("generic_suffix", v))
    m = _BRACKET.match(core)
    if m:
        out += [("bracket", f) for f in (m.group("out"), m.group("in")) if _is_name(f, casing)]
    return [(d, f.strip()) for d, f in out if f.strip()]


DETECTORS = ("vendor_prefix", "version", "generic_suffix", "bracket")


def detect(postings: list[dict], dictionary, job: str = "") -> list[dict]:
    """Proposals from one run's results: a requirement the run left unplaced, and the known
    requirement it looks like a spelling of. Nothing here is decided."""
    seen, out = set(), []
    for p in postings:
        for r in p.get("requirements") or []:
            if r.get("match") not in ("nuovo", "topic") or not r.get("core"):
                continue
            space, core = r.get("space", ""), r["core"]
            key = (space, nr.canon(core))
            if key in seen:
                continue
            for detector, form in _variants(core, dictionary.casing.get("en", {})):
                hit = dictionary._known(space, form)
                if hit is not None and hit.status == "known" and hit.group:
                    seen.add(key)
                    out.append({"kind": "alias", "space": space, "variant": core, "target_core": hit.via or form,
                                "target_group": hit.group, "target_topic": hit.topic,
                                "target_name": dictionary.name(hit.group), "detector": detector,
                                "detected_by": AGENT, "job": job, "detected_at": now()})
                    break
    return out


def save_detected(store, job: str, proposals: list[dict]) -> None:
    write_json(store, jf(job, "curator.json"), {"job": job, "proposals": proposals})


def log(store) -> list[dict]:
    text = store.read_text(LOG) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def resolve(store, job: str, judge_url: str | None) -> dict:
    """Put a run's proposals to the judge and write the outcome to the log. Counts only back."""
    from . import check

    proposals = (read_json(store, jf(job, "curator.json")) or {}).get("proposals") or []
    known = {(e["space"], nr.canon(e["variant"])) for e in log(store) if e.get("status") != "detected"}
    todo = [p for p in proposals if (p["space"], nr.canon(p["variant"])) not in known][:MAX_PER_RUN]
    counts = {"detected": len(proposals), "resolved": 0, "rejected": 0, "pending": 0}
    if not todo:
        return counts
    verdicts: list[bool | None] = [None] * len(todo)
    text = [""] * len(todo)
    if judge_url:
        from . import tester

        d = pd.DataFrame([{"sample": "group", "kind": "requirement", "a": p["variant"], "b": p["target_core"],
                           "context": "(no head)", "a_example": p["variant"], "b_example": ""} for p in todo])
        # The judge's code answers `two different names` with DIFFERENT before
        # asking; a vendor or an acronym IS the difference these detectors look
        # for (`Amazon Web Services (AWS)` / `AWS`), so the model decides them.
        # A spelling stays the code's SAME.
        groups = [tester.group("requirement", a, b) for a, b in zip(d.a, d.b)]
        d = d.assign(id=[f"c{i}" for i in range(len(d))], question=check.QUESTION["group"],
                     group=["narrower_broader" if g == "different_names" else g for g in groups])
        judged = d.merge(tester.ask(judge_url, check.JUDGE_NAME, check.JUDGE_PROMPT, d)
                         [["id", "judge_same", "text"]], on="id")
        verdicts = [None if pd.isna(x) else bool(x) for x in judged.judge_same]
        text = [str(t)[:200] for t in judged.text]
    lines = []
    for p, same, why in zip(todo, verdicts, text):
        status = "detected" if same is None else ("resolved" if same else "rejected")
        counts["pending" if same is None else status] += 1
        lines.append({**p, "status": status,
                      "resolved_by": f"{AGENT}+judge:{check.JUDGE_NAME}" if same is not None else "",
                      "resolved_at": now() if same is not None else "", "judge_text": why})
    old = store.read_text(LOG) or ""
    store.write_text(LOG, old + "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    return counts


def aliases(store) -> dict[tuple[str, str], dict]:
    """(space, canon of the variant) -> the resolved entry. A later verdict on the same variant wins."""
    out = {}
    for e in log(store):
        k = (e["space"], nr.canon(e["variant"]))
        if e.get("status") == "resolved":
            out[k] = e
        elif e.get("status") == "rejected":
            out.pop(k, None)
    return out


def attach(dictionary, store) -> int:
    """Give the dictionary the resolved entries; returns how many. Safe to call again."""
    if dictionary is None:
        return 0
    try:
        entries = aliases(store)
    except Exception:   # a store that cannot be read leaves the dictionary as frozen
        return 0
    dictionary.set_aliases(entries)
    return len(entries)


def overrule(store, variant: str, space: str = "", by: str = "person", why: str = "") -> dict:
    """A person's verdict on an agent's entry: written as `rejected`, so `aliases` drops it.
    The agent's own line stays in the log; the log is never edited, only added to."""
    e = {"kind": "alias", "space": space, "variant": variant, "status": "rejected", "detected_by": AGENT,
         "resolved_by": by, "resolved_at": now(), "judge_text": why, "job": "", "detector": "overruled"}
    store.write_text(LOG, (store.read_text(LOG) or "") + json.dumps(e, ensure_ascii=False) + "\n")
    return e


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .store import open_store

    p = argparse.ArgumentParser(description="The curator's log: list it, or overrule an entry.")
    p.add_argument("--reject", metavar="VARIANT", help="a person rejects the agent's join of this spelling")
    p.add_argument("--space", default="")
    p.add_argument("--why", default="")
    a = p.parse_args(argv)
    store = open_store()
    if a.reject:
        print(json.dumps(overrule(store, a.reject, a.space, why=a.why), ensure_ascii=False))
    for e in log(store)[-30:]:
        print(f"{e.get('status', ''):9} {e.get('variant', '')[:40]:40} -> {e.get('target_name', '')[:30]:30} "
              f"{e.get('resolved_by', '')}")



def summary(store, last: int = 50) -> dict:
    """What the site shows: totals and the latest entries. A variant is a requirement's name,
    not an advert's text; kept to six words, as longer phrases can be one employer's own."""
    entries = [e for e in log(store) if len(e.get("variant", "").split()) <= 6]
    totals = {s: sum(e.get("status") == s for e in entries) for s in ("resolved", "rejected", "detected")}
    keep = ("variant", "target_name", "detector", "status", "detected_by", "resolved_by", "job",
            "detected_at", "resolved_at")
    return {"agent": AGENT, "detectors": list(DETECTORS), "totals": totals,
            "entries": [{k: e.get(k) for k in keep} for e in entries[-last:]][::-1]}


if __name__ == "__main__":
    main()
