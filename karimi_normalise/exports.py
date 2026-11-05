"""Flat files of a run's results, for people who work in spreadsheets.

Two tables beside `results.jsonl`:

* `requirements.csv` — one row per requirement: the posting it came from, the
  item as written, the single requirement, its fields, its group and topic,
  how it was found, and the title's role and group repeated on every row;
* `postings.csv`     — one row per posting, the input's own scalar fields
  (`id`, `title`, `language`, anything else the caller sent, except the
  lists) with the added columns: the role, the counts, the groups and topics
  found, joined with ` | `.

The second is what "a column added to your dataset" means in practice: join
it to the original table on `id`.
"""

from __future__ import annotations

import csv
import io

REQUIREMENT_COLUMNS = [
    "posting_id", "item_idx", "item", "item_split", "translated_by", "route", "atom_idx", "atom", "atom_norm",
    "counted", "nice_to_have", "years_min", "years_max", "level", "head", "head_group", "core", "extra",
    "req_group", "req_topic", "match", "match_cosine", "match_via",
    "title", "title_role", "title_level", "title_name", "title_match", "rules_version", "dict_version",
]
POSTING_ADDED = [
    "title_role", "title_level", "title_extra", "title_name", "title_match", "n_items", "n_requirements",
    "n_counted", "n_known", "n_group", "n_topic", "n_nuovo", "n_items_kept_whole", "req_groups", "req_topics",
    "rules_version", "dict_version",
]


def _rows(posting: dict, requirements: list[dict], title: dict | None) -> list[dict]:
    t = title or {}
    return [{**{c: r.get(c, "") for c in REQUIREMENT_COLUMNS}, "posting_id": posting.get("id", ""),
             "title": t.get("title", ""), "title_role": t.get("title_role", ""),
             "title_level": t.get("title_level", ""), "title_name": t.get("title_name", ""),
             "title_match": t.get("match", "")} for r in requirements]


def _posting_row(posting: dict, requirements: list[dict], title: dict | None) -> dict:
    t = title or {}
    given = {k: v for k, v in posting.items() if not isinstance(v, (list, dict))}
    items = {r["item_idx"]: r for r in requirements}
    row = dict(given)
    row.update({
        "title_role": t.get("title_role", ""), "title_level": t.get("title_level", ""),
        "title_extra": t.get("title_extra", ""), "title_name": t.get("title_name", ""),
        "title_match": t.get("match", ""),
        "n_items": len(posting.get("must_have") or []), "n_requirements": len(requirements),
        "n_counted": sum(1 for r in requirements if r.get("counted")),
        **{f"n_{m}": sum(1 for r in requirements if r.get("match") == m) for m in ("known", "group", "topic", "nuovo")},
        "n_items_kept_whole": sum(1 for r in items.values() if r.get("route") in ("llm", "damaged")),
        "req_groups": " | ".join(dict.fromkeys(r["req_group"] for r in requirements if r.get("req_group"))),
        "req_topics": " | ".join(dict.fromkeys(r["req_topic"] for r in requirements if r.get("req_topic"))),
        "rules_version": requirements[0]["rules_version"] if requirements else "",
        "dict_version": requirements[0]["dict_version"] if requirements else "",
    })
    return row


def tables(inputs: list[dict], results: list[dict]) -> tuple[str, str]:
    """(requirements.csv, postings.csv) as text, from the input postings and
    the result lines (`id`, `requirements`, `title`), matched by position."""
    req_rows, post_rows = [], []
    for p, r in zip(inputs, results):
        req_rows += _rows(p, r.get("requirements") or [], r.get("title"))
        post_rows.append(_posting_row(p, r.get("requirements") or [], r.get("title")))
    given = []
    for row in post_rows:
        given += [k for k in row if k not in POSTING_ADDED and k not in given]
    return _csv(REQUIREMENT_COLUMNS, req_rows), _csv(given + POSTING_ADDED, post_rows)


def _csv(columns: list[str], rows: list[dict]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    return out.getvalue()
