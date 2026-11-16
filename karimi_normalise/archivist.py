"""The archivist agent: the kinds of error found so far, and what each one found in a run means.

    python -m karimi_normalise.archivist                 # the catalogue
    python -m karimi_normalise.archivist --job <id>      # that run's proposals, ready to paste

The inspector (`errors.inspect`) counts; the archivist reads the counts
against the catalogue (`error_catalogue.json`), so a kind seen before is
recognised and named, with what it means for this run:

* ``fixed_later`` — a rules version fixed it after the one this run used:
  re-running with newer rules repairs it;
* ``residual``    — fixed, and still found at about the rate measured when it
  was fixed: the leftovers the fix was known not to reach;
* ``recurs``      — fixed, and found well above that rate: the fix stopped
  working or the input changed. A yellow finding;
* ``open``        — known and not fixed: the archivist writes a proposal.

Asked 2026-11-16: "an agent that keeps the kinds of error, so that seeing them
again it can read them and solve them". It PROPOSES, a person approves (the
user's call of the same day, as for every rule since 2026-11-13): a proposal
is the failing cases drafted as a test, the files to change and the catalogue's
hint. It never changes a rule. Finding kinds nobody has named yet is not its
job: that is a reader of the run's text, measured before it is trusted.

Thresholds fixed 2026-11-16, before any run was reviewed: `recurs` needs at
least RECUR_MIN requirements AND a rate over RECUR_FACTOR times the residual.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

AGENT = "archivist"
CATALOGUE = Path(__file__).resolve().parent / "error_catalogue.json"
RECUR_MIN = 5
RECUR_FACTOR = 3.0
CASES = 5


def catalogue(path: Path = CATALOGUE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def by_detector(entries: list[dict] | None = None) -> dict[str, dict]:
    return {e["detector"]: e for e in (entries if entries is not None else catalogue()) if e.get("detector")}


def _v(s: str | None) -> tuple[int, ...] | None:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None


def verdict(entry: dict, count: int, of: int, rules_version: str | None) -> tuple[str, str]:
    """What `count` requirements of this kind, out of `of`, mean in a run made with `rules_version`."""
    if entry["status"] != "resolved":
        return "open", "known, not fixed yet: see the proposal"
    fixed, used = _v(entry.get("resolved_in")), _v(rules_version)
    if fixed and used and used < fixed:
        return "fixed_later", f"fixed in rules {entry['resolved_in']}; this run used {rules_version}: re-run it"
    rate = count / of if of else 0.0
    base = (entry.get("residual") or {}).get("rate")
    if base is not None and count >= RECUR_MIN and rate > RECUR_FACTOR * base:
        return "recurs", (f"fixed in {entry['resolved_in']}, yet found at {rate:.2%} against {base:.2%} "
                          f"when it was fixed")
    return "residual", f"fixed in {entry['resolved_in']}; the leftovers the fix does not reach"


def _draft(entry: dict, cases: list[dict], job: str | None, rules_version: str | None) -> str:
    """The failing cases as a test a person completes: the expected output is theirs to write."""
    lines = [f"# Archivist proposal: {entry['id']} ({entry['status']}), from job {job}, rules {rules_version}",
             f"# {entry['title']}. Why: {entry['cause']}"]
    if entry.get("fix_hint"):
        lines.append(f"# Hint: {entry['fix_hint']}")
    lines += [f"# Change: {', '.join(entry.get('rule_files') or [])}; then bump RULES_VERSION and the catalogue.",
              '@pytest.mark.parametrize("item, keys", [']
    for c in cases:
        lines.append(f"    ({c.get('item', '')!r}, [...]),  # now: {c.get('atom', '')!r} -> {c.get('key', '')!r}")
    lines.append("])")
    return "\n".join(lines)


def review(inspected: dict | None, rules_version: str | None, job: str | None = None,
           entries: list[dict] | None = None) -> dict | None:
    """The inspector's rows of one run, read against the catalogue.

    ``inspected``: `{"of", "rows", "examples"}` as the check keeps it. Returns
    the public part (`found`: per kind, a count, a verdict and why; no text),
    the `findings` it raises, and the private `proposals` (with the cases' text,
    for the job's own `check.json` only)."""
    if not inspected:
        return None
    known = by_detector(entries)
    of = (inspected.get("of") or {}).get("requirements") or 0
    cases = {x["cause"]: x["cases"] for x in inspected.get("examples") or []}
    found, findings, proposals = [], [], []
    for row in inspected.get("rows") or []:
        entry = known.get(row["cause"])
        if entry is None:
            found.append({"id": row["cause"], "count": row["count"], "verdict": "unknown",
                          "why": "the inspector has no catalogue entry for it"})
            continue
        v, why = verdict(entry, row["count"], of, rules_version)
        found.append({"id": entry["id"], "count": row["count"], "verdict": v, "why": why})
        if v == "recurs":
            findings.append({"level": "archivist", "light": "yellow", "code": f"archivist:{entry['id']}",
                             "what": f"{entry['title']}: {why}"})
        if v in ("open", "recurs"):
            cs = cases.get(row["cause"], [])[:CASES]
            proposals.append({"id": entry["id"], "verdict": v, "rule_files": entry.get("rule_files"),
                              "fix_hint": entry.get("fix_hint"), "cases": cs,
                              "draft": _draft(entry, cs, job, rules_version)})
    return {"agent": AGENT, "of": {"requirements": of}, "found": found, "findings": findings,
            "proposals": proposals}


def public(rv: dict | None) -> dict | None:
    """What leaves the job's files: counts, verdicts and codes, no text."""
    if not rv:
        return None
    return {"agent": rv["agent"], "of": rv["of"], "found": rv["found"],
            "proposals": [p["id"] for p in rv.get("proposals") or []]}


def summary(runs: list[dict], entries: list[dict] | None = None) -> dict:
    """What the site shows: the catalogue, and per kind what the latest runs found. No text from postings."""
    entries = entries if entries is not None else catalogue()
    seen: dict[str, dict] = {}
    for r in runs:                                   # oldest first: the last one wins
        for f in (r.get("archivist") or {}).get("found") or []:
            s = seen.setdefault(f["id"], {"runs": 0, "requirements": 0})
            s.update(runs=s["runs"] + 1, requirements=s["requirements"] + f["count"], last_job=r.get("job"),
                     last_checked=r.get("checked"), last_verdict=f["verdict"], last_count=f["count"])
    keep = ("id", "title", "stage", "found", "found_by", "cause", "status", "resolved_in", "detector", "guard")
    return {"agent": AGENT, "recur": {"min": RECUR_MIN, "factor": RECUR_FACTOR},
            "entries": [{**{k: e.get(k) for k in keep}, "seen": seen.get(e["id"])} for e in entries],
            "open": sum(e["status"] != "resolved" for e in entries)}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="The archivist: the catalogue of errors, or one run's proposals.")
    p.add_argument("--job", help="print the proposals the archivist wrote for this job")
    a = p.parse_args(argv)
    if a.job:
        from .store import jf, open_store, read_json

        c = read_json(open_store(), jf(a.job, "check.json")) or {}
        props = (c.get("archivist") or {}).get("proposals") or []
        print("\n\n".join(p["draft"] for p in props) or "no proposals for this job")
        return
    for e in catalogue():
        print(f"{e['status']:9} {e['id']:26} {e.get('resolved_in') or '':20} {e['title']}")


if __name__ == "__main__":
    main()
