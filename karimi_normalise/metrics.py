"""How a run went: signals, read against what a normal run looks like.

A run has no human labels, so nothing here says how much of it is RIGHT.
`quality.py` says that, once per version, on labelled data. The run report says
whether this run LOOKS LIKE the data that was measured, so the user knows
whether the quality card applies to them:

* each signal is a share computed on the run (`run_metrics`);
* it is compared with random runs of the same size drawn from the corpus
  (`reference.py`, stored with the dictionary);
* 🟢 inside the 5th-95th percentile, 🟡 inside 1st-99th, 🔴 outside. Only the
  side that means trouble counts: fewer `nuovo` than usual is no problem.

And the items worth a look, so the user does not reread the whole run.

The monitor (phase 4) stores the same `run_metrics` row for every batch.
"""

from __future__ import annotations

import collections

from .requirements import Requirement
from .titles import Title

# name -> (what it says, the side that means trouble)
SIGNALS = {
    "requirements_per_item": ("requirements found per must_have item", "both"),
    "share_items_llm": ("items kept whole: they look compound and the rules cannot separate them", "high"),
    "share_items_damaged": ("items kept whole because the split came out broken", "high"),
    "share_one_word": ("one-word requirements: mostly names (`Python`), sometimes broken splits", "high"),
    "share_translated": ("requirements translated first: translation quality is not measured", "high"),
    "share_known": ("requirements the dictionary already holds, wording for wording", "low"),
    "share_group_nearest": ("placed in a group by similarity (cosine >= 0.90)", "high"),
    "share_topic_only": ("only the topic is known (cosine 0.80-0.90), not the exact group", "high"),
    "share_nuovo": ("requirements the dictionary does not know (cosine < 0.80)", "high"),
    "share_titles_nuovo": ("titles whose role the dictionary does not know", "high"),
}
TOP = 20


def run_metrics(postings: list[list[Requirement]], titles: list[Title] | None = None) -> dict:
    """The same ratios `reference.py` computes on the corpus, on one run."""
    reqs = [r for p in postings for r in p]
    items = [r for p in postings for r in {r.item_idx: r for r in p}.values()]
    match = collections.Counter(r.match for r in reqs)
    n, ni = len(reqs), len(items)

    def share(k, d):
        return round(k / d, 4) if d else None

    out = {
        "postings": len(postings), "items": ni, "requirements": n,
        "requirements_per_item": share(n, ni),
        "share_items_llm": share(sum(r.route == "llm" for r in items), ni),
        "share_items_damaged": share(sum(r.route == "damaged" for r in items), ni),
        "share_one_word": share(sum(len(r.atom.split()) == 1 for r in reqs), n),
        "share_translated": share(sum(r.translated for r in reqs), n),
    }
    if reqs and reqs[0].dict_version:
        out.update(share_known=share(match["known"], n), share_group_nearest=share(match["group"], n),
                   share_topic_only=share(match["topic"], n), share_nuovo=share(match["nuovo"], n),
                   share_not_searched=share(match["non_cercato"], n))
    if titles and titles[0].dict_version:
        out["titles"] = len(titles)
        out["share_titles_nuovo"] = share(sum(t.match == "nuovo" for t in titles), len(titles))
    return out


def log_run(report: dict, path) -> dict:
    """Append one line per run to a JSONL file: the history a dashboard reads.

    Only the versions, the counts and each signal's value and light: no
    requirement text, so the file can be shared without the ads.
    """
    import datetime as dt
    import json
    from pathlib import Path
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           **report["versions"], **report["summary"], "overall": report["overall"],
           **{f"{k}": v["value"] for k, v in report["signals"].items()},
           **{f"{k}_light": v["light"] for k, v in report["signals"].items()},
           "warnings": len(report.get("warnings", []))}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _light(value: float, pct: dict, side: str) -> str:
    lo5, hi95, lo1, hi99 = pct["5"], pct["95"], pct["1"], pct["99"]
    high = side in ("high", "both")
    low = side in ("low", "both")
    if (high and value > hi99) or (low and value < lo1):
        return "red"
    if (high and value > hi95) or (low and value < lo5):
        return "yellow"
    return "green"


def run_report(postings: list[list[Requirement]], titles: list[Title] | None = None,
               dictionary=None) -> dict:
    m = run_metrics(postings, titles)
    reqs = [r for p in postings for r in p]
    ref = dictionary.reference if dictionary is not None else None
    signals = {}
    # Added 2026-11-13: a run smaller than the smallest reference run is read
    # against runs ten times its size, so one one-word requirement in nine
    # turned a clean test red. Its signals are shown but go grey, as the
    # judge's do under MIN_PAIRS.
    too_small = bool(ref) and m["postings"] < ref["sizes"][0]
    if ref:
        sizes = [s for s in ref["sizes"] if s <= max(m["postings"], 1)] or ref["sizes"][:1]
        size = str(sizes[-1])
        for name, (meaning, side) in SIGNALS.items():
            if m.get(name) is None or name not in ref["signals"]:
                continue
            pct = ref["signals"][name]["by_size"][size]
            signals[name] = {"value": m[name], "typical": pct["50"], "normal_range": [pct["5"], pct["95"]],
                             "light": "grey" if too_small else _light(m[name], pct, side), "meaning": meaning}
    lights = collections.Counter(s["light"] for s in signals.values())
    # A setup problem, not a property of the run, so it is a warning and no band.
    warnings = []
    if m.get("share_not_searched"):
        warnings.append(f"{m['share_not_searched']:.1%} of requirements were not looked up: the embedding "
                        "model is not installed (pip install karimi-normalise[embed]). The match signals "
                        "are not comparable with the reference.")
        lights["yellow"] += 1
    whole = collections.Counter(r.item for p in postings for r in {r.item_idx: r for r in p}.values()
                                if r.route in ("llm", "damaged"))
    nuovo = collections.Counter(r.atom_norm for r in reqs if r.match == "nuovo")
    topic = collections.Counter((r.atom_norm, r.req_topic) for r in reqs if r.match == "topic")
    return {
        "versions": {"rules_version": reqs[0].rules_version if reqs else "",
                     "dict_version": dictionary.version if dictionary is not None else ""},
        "summary": {k: m[k] for k in ("postings", "items", "requirements", "requirements_per_item")},
        "overall": "red" if lights["red"] else "yellow" if lights["yellow"] else "green",
        "compared_with": (f"too few postings to read: the smallest reference run has {size}" if too_small
                          else f"random runs of {size} postings from the corpus the quality card "
                          f"was measured on" if ref else "no reference: dictionary has none"),
        "signals": signals,
        "warnings": warnings,
        "to_check": {
            "items_kept_whole": [{"item": k, "n": v} for k, v in whole.most_common(TOP)],
            "requirements_nuovo": [{"requirement": k, "n": v} for k, v in nuovo.most_common(TOP)],
            "requirements_topic_only": [{"requirement": k, "topic": t, "n": v}
                                        for (k, t), v in topic.most_common(TOP)],
        },
        "note": "Signals say whether this run resembles the measured data, not how much of it is "
                "right. For that, see /quality for these versions.",
    }
