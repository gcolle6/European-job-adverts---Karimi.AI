"""Normalise the job titles of the software export into roles.

    python "New project/normalise_titles.py"           # write output/titles.parquet
    python "New project/normalise_titles.py" --show    # also print merged groups to read

Rules only, local, deterministic (`karimi/normalise_title.py`). Input is the
export's `job_title_english` (translated upstream). Where that is empty (71
postings) the original is used, translated locally first when it is not English
(`english_titles`). One row per posting, every removed part in its own column:

* ``title_role``  — the role as written, without gender, seniority and extras;
* ``title_level`` — seniority read from the title (`senior`, `intern`, ...);
* ``title_extra`` — brackets and trailing parts (location, team, contract);
* ``title_key``   — content words as a set: order and case make no new role;
* ``title_group`` — the key after spelling variants join (`group_titles`);
* ``title_name``  — the group's commonest wording, for display.
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from karimi import language  # noqa: E402
from karimi import normalise_title as nt  # noqa: E402
import translate_must_have as tm  # noqa: E402

EXPORT = HERE.parent / "wetransfer_karimi-jobs_2026-08-25_1346" / "software_data_europe.json"
OUT = HERE / "output"
FROZEN = HERE / "test_sets.json"


def _letters(title: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]{3,}", nt.clean(title).lower()))


def title_language(rows: list[dict]) -> dict[str, str]:
    """The language of each title the export left without an English version.

    Titles are too short for `language.detect`, which abstains on all 71. So the
    evidence is learned from the titles the export DID translate: a word counts
    as foreign when it appears in more translated originals than English titles,
    and it votes for the language of the postings it appears in. One vote per
    word, so `Ingénieur` decides, and a frequent `de` cannot outvote it. A title
    with no foreign word is English as written (`Data Consultant`).
    """
    english = collections.Counter(w for r in rows if (r["job_title_english"] or "").strip()
                                  for w in _letters(r["job_title_english"]))
    foreign: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        e = (r["job_title_english"] or "").strip()
        if e and e != r["job_title"].strip():
            lang = language.detect(" | ".join(r["must_have"] or []))[0]
            if lang and lang != "English":
                for w in _letters(r["job_title"]):
                    foreign[w][lang] += 1
    out = {}
    for r in rows:
        if (r["job_title_english"] or "").strip():
            continue
        votes = collections.Counter(foreign[w].most_common(1)[0][0] for w in _letters(r["job_title"])
                                    if sum(foreign[w].values()) > english[w])
        if votes:
            out[r["job_title"]] = votes.most_common(1)[0][0]
    return out


def english_titles(rows: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    """Each posting's English title, where it came from, and its parts.

    `export` — the export's own `job_title_english`; `translated` — the original,
    translated here with the same local opus-mt as `must_have` (shared cache);
    `original` — the original as written: English already, or a language with
    no local model (`Online kiemelt tanácsadó`, Hungarian).

    Only the ROLE is translated. Level and extras are read off the original
    first, by rules that already know `Alternance` and `Praktikant`; translated
    whole, `Alternance` comes back as `Alternative` and the level is lost.
    """
    langs = title_language(rows)
    role_of = {t: nt.decompose(t)["role"] for t in langs}
    todo = pd.DataFrame([(role_of[t], tm.CODE.get(l)) for t, l in langs.items() if role_of[t]],
                        columns=["item", "code"])
    cache = tm.translate_all(todo) if todo.code.notna().any() else {}
    titles, source, parts = [], [], []
    for r in rows:
        e = (r["job_title_english"] or "").strip()
        t = (r["job_title"] or "").strip()
        code = tm.CODE.get(langs.get(t))
        out = cache.get(tm._key(code, role_of[t])) if not e and code and role_of[t] else None
        if not out:
            titles.append(e or t); source.append("export" if e else "original")
            parts.append(nt.decompose(e or t))
            continue
        orig, tr = nt.decompose(t), nt.decompose(out)
        titles.append(out); source.append("translated")
        parts.append({"role": tr["role"],
                      "level": "|".join(dict.fromkeys(x for x in (orig["level"], tr["level"]) if x)),
                      "extra": " | ".join(x for x in (orig["extra"], tr["extra"]) if x)})
    return titles, source, parts


def build(rows: list[dict]) -> pd.DataFrame:
    src, source, parts = english_titles(rows)
    acronyms = nt.learn_acronyms(src)
    roles = [p["role"] for p in parts]
    groups = nt.group_titles(roles, acronyms)
    df = pd.DataFrame({
        "posting_id": [r["_id"] for r in rows],
        "job_title": [r["job_title"] for r in rows],
        "job_title_english": [r["job_title_english"] for r in rows],
        "title_english": src,
        "title_source": source,
        "seniority": [r["seniority"] for r in rows],
        "title_role": [p["role"] for p in parts],
        "title_level": [p["level"] for p in parts],
        "title_extra": [p["extra"] for p in parts],
        "title_key": [nt.key(r, acronyms) for r in roles],
    })
    df["title_group"] = df.title_key.map(groups).fillna("")
    # Named by the commonest written role among its members.
    name = (df[df.title_group != ""].groupby("title_group").title_role
            .agg(lambda s: s.str.strip().value_counts().index[0]))
    df["title_name"] = df.title_group.map(name).fillna("")
    return df, acronyms


def depth(s: pd.Series) -> dict:
    vc = s[s != ""].value_counts()
    n = len(s)
    return {"distinct": int(len(vc)),
            **{f"share_in_roles_{k}+": round(float(vc[vc >= k].sum() / n), 3) for k in (10, 50)},
            **{f"roles_{k}+": int((vc >= k).sum()) for k in (10, 50)}}


def main() -> None:
    rows = json.loads(EXPORT.read_text(encoding="utf-8"))
    df, acronyms = build(rows)
    OUT.mkdir(exist_ok=True)
    df.to_parquet(OUT / "titles.parquet", index=False)
    english = df.title_english
    stages = {
        "job_title as written": depth(df.job_title),
        "job_title_english": depth(english),
        "  lowercased": depth(english.str.lower()),
        "  without gender, seniority, extras": depth(df.title_role.str.lower()),
        "  word order free (key)": depth(df.title_key),
        "  spelling variants joined (group)": depth(df.title_group),
    }
    summary = {"postings": len(df), "stages": stages, "acronyms_learned": acronyms,
               "with_level": round(float((df.title_level != "").mean()), 3),
               "with_extra": round(float((df.title_extra != "").mean()), 3)}
    (OUT / "titles_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(pd.DataFrame(stages).T.to_string())
    print(f"\nacronyms learned: {acronyms}")
    print(f"with level {summary['with_level']:.1%}, with extra {summary['with_extra']:.1%}")
    print("\ntop roles:\n" + df[df.title_name != ""].title_name.value_counts().head(30).to_string())

    if "--show" in sys.argv:
        # Reading is done on dev postings only; the holdout stays unread.
        hold = set(json.loads(FROZEN.read_text(encoding="utf-8"))["software_holdout"])
        dev = df[~df.posting_id.isin(hold)]
        multi = dev.groupby("title_group").title_role.agg(lambda s: sorted(set(s)))
        multi = multi[multi.map(len) > 1]
        random.seed(20261102)
        for g in random.sample(list(multi.index), min(40, len(multi))):
            print(f"- [{g}] {multi[g][:8]}")


if __name__ == "__main__":
    main()
