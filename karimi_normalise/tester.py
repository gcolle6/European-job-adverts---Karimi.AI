"""The tester agent: a local LLM judges pairs the way the human labeller did.

    llama-server -m <model.gguf> --port 8080            # any OpenAI-compatible local server
    python -m karimi_normalise.tester --name qwen3_4b --prompt v2 --part dev
    python -m karimi_normalise.tester --name qwen3_4b --prompt v2 --part holdout

Phase 6 of `New project/PIANO_SVILUPPO.md`. Before it may replace a human
check it is CALIBRATED against answers it did not write. Three sources, never
pooled into one number:

* `human`    — the 74 pairs of `validation/pairs*_LABELLED.csv`. Roles are
  read both blind and after `pairs*_corrections.csv`; the rechecked reading is
  the project's settled definition, the blind one the independent reading;
* `dev_eng`  — the 83 `X Developer` / `X Engineer` decisions the user took one
  by one (`validation/developer_engineer_REVIEW.csv`), `merge_safe` as the
  answer, "doubtful counts as different"; the 2 parse artefacts left out;
* `controls` — requirement pairs that BOTH name a different product, standard
  or degree (`GitHub` / `GitLab`, `Bachelor's` / `Master's`), at cosine 0.80+.
  Different by the project's rule (`normalise_req.names`, the guide's `SQL` /
  `PostgreSQL`), not by a person: they test the side the human labels cannot,
  since the human said "different" about one requirement pair in 44, and a
  judge that always says "same" would otherwise score 0.98.

Every source is split once into `dev` and `holdout` (`split`, seed fixed,
stratified on kind and answer). Prompts are changed on dev; the holdout is
read once per prompt and never used to choose wording.

Two questions for requirements, not one. The human's "same" on near misses
reads as "same theme" (`risk` ~ `risk mitigation`), against the guide's
"narrower = different"; so the judge is asked both: `theme` (for `req_topic`)
is scored on every human pair, `strict` (for `req_group`) only on the pairs the
rules MERGED, where the human's "same" does mean the same requirement. Both are
scored on the controls. Roles get one question.

Thresholds fixed 2026-11-04, BEFORE the first calibration run:

* agreement >= 0.85, per question and per source;
* Cohen's kappa >= 0.60 where both answers occur at least 5 times.

Added 2026-11-04 after the first run and before any prompt change, stricter
and not looser: on requirements, where kappa is undefined on human labels, the
judge must ALSO reach 0.85 on the controls.

Agreement is not accuracy: the labels are one person's, and the controls are a
rule's. The prompt author had seen every row before splitting, so the holdout
guards against tuning to rows, not against knowing them; prompt examples are
therefore taken from outside all three sources.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "New project"
VAL = NEW / "validation"
# Where answers are cached and calibrations written; the check job points it at /tmp.
OUT = Path(os.environ.get("KARIMI_TESTER_OUT", NEW / "output" / "tester"))
# The labeller's guide, shipped inside the package so the judge runs where the
# validation folder does not exist (the check job). A test keeps it identical.
GUIDE = Path(__file__).resolve().parent / "PAIRS_GUIDE.md"
DICT = NEW / "output" / "dictionaries" / "0.1.0"
CACHE = OUT / "answers.jsonl"

MIN_AGREEMENT = 0.85
MIN_KAPPA = 0.60
MIN_PER_CLASS = 5
SEED = 20261104
CONTROL_MIN_N = 5          # both cores seen in at least 5 atoms
CONTROL_COSINE = (0.80, 0.97)
CONTROL_MAX = 40

# ---------------------------------------------------------------- the pairs


def _human() -> pd.DataFrame:
    """The 74 labelled pairs, with the text the human saw and both readings."""
    spec = importlib.util.spec_from_file_location("score_pairs", NEW / "score_pairs.py")
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    out = []
    for tag in ("pairs", "pairs_r2"):
        with contextlib.redirect_stdout(io.StringIO()):
            b, r = sp.load(tag, False)
        sheet = pd.read_csv(VAL / f"{tag}_LABELLED.csv", encoding="utf-8-sig", dtype=str).fillna("")
        # The key may swap a/b relative to the sheet: take the text the human saw.
        sheet = sheet[["pair", "a", "b", "context", "a_example", "b_example"]]
        d = b[["pair", "kind", "decision", "cosine", "same"]].rename(columns={"same": "same_blind"})
        d["same"] = (r if r is not None else b).same.values
        d = d.merge(sheet, on="pair")
        out.append(d.assign(source="human", id=tag + "#" + d.pair))
    return pd.concat(out, ignore_index=True).drop(columns="pair")


def _dev_eng() -> pd.DataFrame:
    d = pd.read_csv(VAL / "developer_engineer_REVIEW.csv", encoding="utf-8-sig", dtype=str).fillna("")
    d = d[d.verdict != "artifact"]
    same = d.merge_safe == "yes"
    return pd.DataFrame({
        "source": "dev_eng", "id": "dev_eng#" + d.index.astype(str), "kind": "role",
        "a": d.developer_title.str.replace("(s)", "", regex=False).values,
        "b": d.engineer_title.str.replace("(s)", "s", regex=False).values,
        "context": "", "a_example": "", "b_example": "", "decision": "", "cosine": "",
        "same": same.values, "same_blind": same.values})


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _controls() -> pd.DataFrame:
    """Requirement pairs under one head that each name ONE thing, a different one.

    Spelling variants of one name are left out (`Power BI` / `PowerBI`, `CSS` /
    `CSS3`, `GIT` / `GitHub`): `names` counts them as different, which is a
    defect of `names`, not a different requirement. So are names in the prompt.
    """
    from karimi.normalise_req import _CREDENTIALS, names

    c = pd.read_parquet(DICT / "req_cores.parquet")
    v = np.load(DICT / "req_vectors.npy")
    c["names"] = [names(x) for x in c.req_core]
    top = c[(c.n >= CONTROL_MIN_N) & (c.names.map(len) == 1)]
    rows = []
    for head, s in top.groupby("req_head_group"):
        idx = s.index.to_numpy()
        if len(idx) < 2:
            continue
        m = v[idx].astype(np.float32)
        m /= np.linalg.norm(m, axis=1, keepdims=True)
        sim = m @ m.T
        near = np.argwhere(np.triu((sim >= CONTROL_COSINE[0]) & (sim < CONTROL_COSINE[1]), 1))
        for i, j in near:
            a, b = c.loc[idx[i]], c.loc[idx[j]]
            na, nb = next(iter(a.names)), next(iter(b.names))
            la, lb = _letters(na), _letters(nb)
            if (na == nb or la in lb or lb in la or la[:5] == lb[:5] or {na, nb} & _PROMPT_NAMES
                    # each name absent from the other side: not a narrower case
                    or na in _words(b.req_core) or nb in _words(a.req_core)
                    # a degree against a degree, a tool against a tool
                    or (na in _CREDENTIALS) != (nb in _CREDENTIALS)):
                continue
            rows.append({"head": head, "a": a.req_core, "b": b.req_core, "cos": float(sim[i, j]),
                         "n": int(min(a.n, b.n)), "pair": tuple(sorted((la, lb)))})
    d = pd.DataFrame(rows).sort_values(["n", "cos"], ascending=False)
    # One pair of names once, whatever the head or the spelling around them.
    d = d.drop_duplicates("pair").head(CONTROL_MAX).reset_index(drop=True)
    return pd.DataFrame({
        "source": "controls", "id": "controls#" + d.index.astype(str), "kind": "requirement",
        "a": d.a, "b": d.b, "context": d["head"].replace("", "(no head)"),
        "a_example": "", "b_example": "", "decision": "", "cosine": d.cos.round(3).astype(str),
        "same": False, "same_blind": False})


def split(d: pd.DataFrame) -> pd.Series:
    """`dev` or `holdout`, half each within source x kind x answer, fixed once."""
    h = [hashlib.sha256(f"{SEED}|{i}".encode()).hexdigest() for i in d.id]
    order = pd.Series(h, index=d.index)
    part = pd.Series("dev", index=d.index)
    for _, s in d.groupby(["source", "kind", "same"]):
        ranked = order[s.index].sort_values().index
        part[ranked[1::2]] = "holdout"
    return part


def pairs() -> pd.DataFrame:
    d = pd.concat([_human(), _dev_eng(), _controls()], ignore_index=True)
    d["same"] = d.same.astype(bool)
    d["same_blind"] = d.same_blind.astype(bool)
    d["part"] = split(d)
    d["group"] = [group(r.kind, r.a, r.b) for r in d.itertuples()]
    return d

# ---------------------------------------------------------------- the groups


def _words(s: str) -> list[str]:
    return [w.rstrip("s") if len(w) > 3 else w for w in re.findall(r"[a-z0-9+#]+", s.lower())]


_JOB = ("developer", "engineer")


def group(kind: str, a: str, b: str) -> str:
    """What kind of near miss a pair is, read off its text, so it applies to new pairs."""
    wa, wb = _words(a), _words(b)
    if _letters("".join(wa)) == _letters("".join(wb)) or sorted(wa) == sorted(wb):
        return "spelling"
    if kind == "role":
        if {wa[-1], wb[-1]} == set(_JOB):
            return "developer_engineer"
        if wa[-1] == wb[-1]:
            return "same_job_word"
        return "different_job_word"
    from karimi.normalise_req import names
    na, nb = names(a), names(b)
    if na and nb and na != nb:
        return "different_names"
    if set(wa) <= set(wb) or set(wb) <= set(wa):
        return "narrower_broader"
    if set(wa) & set(wb):
        return "share_a_word"
    return "no_shared_word"

# ---------------------------------------------------------------- the prompts

# Examples come from OUTSIDE the three sources, so no scored row is in the prompt.
_PROMPT_NAMES = {"jira", "confluence", "react", "rust", "aws", "azure"}

_PROJECT = """
## Decisions the project has taken (they override the general guide where they differ)

### Roles
1. The last word names the job: Engineer, Developer, Manager, Consultant, Analyst,
   Architect, Specialist, Administrator, Lead, Tester, Designer. A different job
   word is a different role (`Data Lead` / `Data Manager` -> DIFFERENT).
2. The one exception is Developer / Engineer. `X Developer` = `X Engineer` only
   when X names a programming language, a framework or a kind of software or of
   software work (`React Developer` = `React Engineer`, `Rust Developer` =
   `Rust Engineer`). When X is a generic word that also names non-software jobs
   (process, industrial, infrastructure, hardware, customer-facing or pre-sales
   work) or there is no X at all, they are DIFFERENT
   (`Process Developer` / `Process Engineer` -> DIFFERENT, `Developer` /
   `Engineer` -> DIFFERENT). When in doubt: DIFFERENT.
3. Same job word, a different specialty in front -> DIFFERENT
   (`Backend Engineer` / `Frontend Engineer`, `Sales Consultant` / `IT Consultant`).
4. Spelling, plural, word order, hyphens and abbreviations make no new role -> SAME
   (`Front-End Engineer` = `Frontend Engineer`, `SW` = `Software`).

### Requirements
5. Spelling, plural, abbreviation, filler words -> SAME requirement
   (`Comfortable with Jira` = `Comfortable working with Jira`).
6. One is a narrower or broader version of the other (`monitoring` /
   `application monitoring`, `Jira` / `Jira administration`): the same THEME,
   not the same requirement.
7. Both name a product, tool, language, standard or degree, and the names
   differ -> DIFFERENT, also for the theme question, even inside one category
   (`Jira` / `Confluence`, `AWS` / `Azure`, `Bachelor's` / `Master's`).
8. A name on one side only is the narrower case of rule 6
   (`cloud platforms` / `AWS cloud platforms`: same theme, different requirement).
"""

# v4: written after reading v2's dev errors. Rule 2 inverted to a default
# (v2 split `SW`, `Quant`, `MES`, `Big Data` and joined `Cloud`, `IAM`), rule 7
# names degree levels (v2 called Master's / PhD the same theme). Examples
# still from outside the three sources.
_PROJECT_V4 = _PROJECT.replace(
    """2. The one exception is Developer / Engineer. `X Developer` = `X Engineer` only
   when X names a programming language, a framework or a kind of software or of
   software work (`React Developer` = `React Engineer`, `Rust Developer` =
   `Rust Engineer`). When X is a generic word that also names non-software jobs
   (process, industrial, infrastructure, hardware, customer-facing or pre-sales
   work) or there is no X at all, they are DIFFERENT
   (`Process Developer` / `Process Engineer` -> DIFFERENT, `Developer` /
   `Engineer` -> DIFFERENT). When in doubt: DIFFERENT.""",
    """2. The one exception to rule 1 is Developer / Engineer, and it comes first.
   By DEFAULT `X Developer` = `X Engineer` -> SAME, whenever X is about building
   software: a language, framework, platform, device, stack layer or software
   field (`React Developer` = `React Engineer`, `Rust Developer` = `Rust Engineer`,
   `Game Developer` = `Game Engineer`). Only two cases are DIFFERENT:
   a) there is no X at all (`Developer` / `Engineer`);
   b) with Engineer, X commonly names a job that does NOT write software:
      running infrastructure or operations, hardware, manufacturing or process
      work, configuration or administration of a system, or customer-facing and
      pre-sales work (`Network Developer` / `Network Engineer`, `Process
      Developer` / `Process Engineer`, `Field Developer` / `Field Engineer`).
   When in doubt between SAME and b): DIFFERENT.""").replace(
    """7. Both name a product, tool, language, standard or degree, and the names
   differ -> DIFFERENT, also for the theme question, even inside one category
   (`Jira` / `Confluence`, `AWS` / `Azure`, `Bachelor's` / `Master's`).""",
    """7. Both name a product, tool, language, standard or degree, and the names
   differ -> DIFFERENT, also for the theme question, even inside one category
   and even when one product is part of or built on the other (`Jira` /
   `Confluence`, `AWS` / `Azure`, `AWS` / `AWS Lambda`). Every degree level is
   its own name: a diploma, a bachelor's, a master's and a doctorate are four
   DIFFERENT requirements, whatever the subject.""")

QUESTIONS = {
    "v1": {
        "strict": "Does an employer asking for `a` want the same thing as one asking for `b`? "
                  "If one is narrower or more specific than the other, they are DIFFERENT.",
        "theme": "Are `a` and `b` the same requirement or the same theme, even if one is a "
                 "narrower or broader version of the other?",
        "role": "Would a candidate for `a` also apply to `b`, and would the employer ask for the "
                "same things?",
    },
}
QUESTIONS["v2"] = {
    "strict": "Question: are `a` and `b` the SAME REQUIREMENT (rule 5), so that an employer "
              "asking for `a` would accept `b` with nothing lost? Narrower or broader is DIFFERENT.",
    "theme": "Question: are `a` and `b` the SAME THEME (rules 5, 6, 8: same requirement, or one a "
             "narrower or broader version of the other)? Different names (rule 7) or different "
             "things that only share a word are DIFFERENT.",
    "role": "Question: are `a` and `b` the same role (rules 1-4)? Would a candidate for `a` also "
            "apply to `b`, and would the employer ask for the same things?",
}
QUESTIONS["v3"] = QUESTIONS["v4"] = QUESTIONS["v2"]

PROMPTS = {
    # v1: the labeller's guide only, verdict first. The first calibration.
    "v1": {"project": None, "reason_first": False, "spelling_by_code": False},
    # v2: the guide plus the project's decisions, verdict first.
    "v2": {"project": _PROJECT, "reason_first": False, "spelling_by_code": False},
    # v3: as v2, reasoning before the verdict. REJECTED on dev 2026-11-05: the 4B
    # model talks itself out of rule 2 (`iOS`, `Mobile`, `Full Stack` "not
    # software"), role agreement 0.81 -> 0.50 on dev_eng.
    "v3": {"project": _PROJECT, "reason_first": True, "spelling_by_code": False},
    # v4: rules 2 and 7 rewritten; spelling pairs answered by code, not asked.
    # REJECTED on dev 2026-11-05: the 4B swings to "same" on every Developer /
    # Engineer pair, bare `Developer` / `Engineer` included; the 7B is no better.
    "v4": {"project": _PROJECT_V4, "reason_first": False, "spelling_by_code": True},
    # v5: v2's prompt, and what the project DEFINES is answered by code, never
    # asked: spelling, two different names (`names`), and Developer / Engineer
    # by the user's own list (`normalise_title._DEV_ENG_SAME`). That list was
    # decided X by X, so no principle reproduces it and no model can infer it
    # (v2, v4, both models). The LLM is left what no rule decides.
    "v5": {"project": _PROJECT, "reason_first": False, "spelling_by_code": True, "rules_by_code": True},
}
QUESTIONS["v5"] = QUESTIONS["v2"]
for _p in PROMPTS.values():
    _p.setdefault("rules_by_code", False)


def _dev_eng_by_list(a: str, b: str) -> bool:
    """`X Developer` = `X Engineer` exactly as the titles rule decides it."""
    from karimi import normalise_title as nt

    dev, eng = (a, b) if nt._developer_head(a) else (b, a)
    toks = nt._tokens(dev) + nt._tokens(eng)
    singular = nt.make_singular(set(toks))
    e = [singular(t) for t in nt._tokens(eng)]
    return bool({" ".join(sorted(set(e))), "#" + "".join(e)} & nt.variants(dev, singular))


def by_code(prompt: str, r) -> tuple[bool, str] | None:
    """The answer the project's own definitions give, or None: ask the model."""
    p = PROMPTS[prompt]
    if p["spelling_by_code"] and r.group == "spelling":
        # Plural, case, hyphen, word order: the same by definition. A model asked
        # this only adds noise (v2 split `Software Engineer` / `Software Engineers`).
        return True, "spelling"
    if p["rules_by_code"] and r.group == "different_names":
        return False, "two different names"
    if p["rules_by_code"] and r.group == "developer_engineer":
        return _dev_eng_by_list(r.a, r.b), "Developer / Engineer list"
    return None


def _messages(row, question: str, prompt: str) -> list[dict]:
    p = PROMPTS[prompt]
    guide = GUIDE.read_text(encoding="utf-8")
    system = "You label pairs from job ads, following this guide.\n\n" + guide
    if p["project"]:
        system += "\n" + p["project"]
    ex = lambda e, what: f"   ({what}: {e})" if e else ""  # noqa: E731
    if row.kind == "requirement":
        pair = (f"kind: requirement\ncontext (frame already removed): {row.context}\n"
                f"a: {row.a}{ex(row.a_example, 'as written in one ad')}\n"
                f"b: {row.b}{ex(row.b_example, 'as written in one ad')}")
    else:
        pair = (f"kind: role\na: {row.a}{ex(row.a_example, 'one ad title')}\n"
                f"b: {row.b}{ex(row.b_example, 'one ad title')}")
    if p["reason_first"]:
        ask = ("First give your reasoning in at most two sentences, naming the rule you apply. "
               "Then, on the last line, write exactly one word: SAME or DIFFERENT.")
    else:
        ask = ("Answer on the first line with exactly one word: SAME or DIFFERENT. "
               "On the second line give a reason of at most 15 words.")
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"{pair}\n\n{QUESTIONS[prompt][question]}\n{ask}"}]


def _verdict(text: str, last: bool = False) -> bool | None:
    found = re.findall(r"\b(SAME|DIFFERENT)\b", text.upper())
    return None if not found else (found[-1] if last else found[0]) == "SAME"

# ---------------------------------------------------------------- asking


def _chat(url: str, messages: list[dict], max_tokens: int) -> str:
    body = json.dumps({"messages": messages, "temperature": 0, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{url}/v1/chat/completions", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _key(name: str, messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps([name, messages], sort_keys=True).encode()).hexdigest()[:32]


def _cache() -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    return {x["key"]: x for x in map(json.loads, CACHE.read_text(encoding="utf-8").splitlines())}


def questions_for(kind: str) -> list[str]:
    return ["strict", "theme"] if kind == "requirement" else ["role"]


def ask(url: str, name: str, prompt: str, d: pd.DataFrame) -> pd.DataFrame:
    """One answer per pair and question. Cached by model, prompt and text: a
    re-run, or a second prompt sharing a message, asks nothing twice.

    A `question` column asks that one question only (the check asks `strict`
    of a group match and `theme` of a topic match); without it, every
    question of the pair's kind."""
    seen, rows = _cache(), []
    OUT.mkdir(parents=True, exist_ok=True)
    reason_first = PROMPTS[prompt]["reason_first"]
    with CACHE.open("a", encoding="utf-8") as f:
        for r in d.itertuples():
            for q in ([r.question] if "question" in d.columns else questions_for(r.kind)):
                code = by_code(prompt, r)
                if code is not None:
                    rows.append({"id": r.id, "question": q, "seconds": 0.0, "judge_same": code[0],
                                 "by": "code",
                                 "text": f"{'SAME' if code[0] else 'DIFFERENT'} (by code: {code[1]})"})
                    continue
                m = _messages(r, q, prompt)
                k = _key(name, m)
                if k not in seen:
                    s = time.time()
                    text = _chat(url, m, 160 if reason_first else 40)
                    seen[k] = {"key": k, "judge": name, "text": text.strip(),
                               "seconds": round(time.time() - s, 2)}
                    f.write(json.dumps(seen[k], ensure_ascii=False) + "\n")
                    f.flush()
                x = seen[k]
                rows.append({"id": r.id, "question": q, "text": x["text"], "seconds": x["seconds"],
                             "by": "model", "judge_same": _verdict(x["text"], last=reason_first)})
    return pd.DataFrame(rows)

# ---------------------------------------------------------------- scoring


def _kappa(h: pd.Series, m: pd.Series) -> float | None:
    if min(h.sum(), (~h).sum()) < MIN_PER_CLASS or min(m.sum(), (~m).sum()) < 1:
        return None
    po = (h == m).mean()
    pe = h.mean() * m.mean() + (1 - h.mean()) * (1 - m.mean())
    return round(float((po - pe) / (1 - pe)), 4) if pe < 1 else None


def _score(h: pd.Series, m: pd.Series) -> dict:
    ok = m.notna()
    h, m = h[ok].astype(bool), m[ok].astype(bool)
    agree = round(float((h == m).mean()), 4) if len(h) else None
    kappa = _kappa(h, m)
    return {"pairs": int(len(ok)), "answered": int(ok.sum()), "agreement": agree, "kappa": kappa,
            "human_same": int(h.sum()), "judge_same": int(m.sum()),
            "judge_different_truth_same": int((h & ~m).sum()),
            "judge_same_truth_different": int((~h & m).sum()),
            "passes": bool(agree is not None and agree >= MIN_AGREEMENT
                           and (kappa is None or kappa >= MIN_KAPPA))}


# What each question is scored on: (source, reading, which rows).
SCORED = {
    "role": [("human", "rechecked", None), ("human", "blind", None), ("dev_eng", "rechecked", None)],
    "theme": [("human", "blind", None), ("controls", "rechecked", None)],
    "strict": [("human", "blind", "merged"), ("controls", "rechecked", None)],
}


def evaluate(url: str, name: str, prompt: str, part: str) -> dict:
    d = pairs()
    d = d[d.part == part]
    a = ask(url, name, prompt, d).merge(d, on="id")
    out = {"judge": name, "prompt": prompt, "part": part,
           "seconds_per_question": round(float(a.seconds.mean()), 2),
           "thresholds": {"agreement": MIN_AGREEMENT, "kappa": MIN_KAPPA}, "scores": {}, "groups": {}}
    for q, cells in SCORED.items():
        for source, reading, only in cells:
            s = a[(a.question == q) & (a.source == source)]
            if only:
                s = s[s.decision == only]
            truth = s.same if reading == "rechecked" else s.same_blind
            label = f"{q}/{source}" + (f"/{reading}" if source == "human" and q == "role" else "") \
                + (f"/{only}" if only else "")
            out["scores"][label] = _score(truth, s.judge_same)
            if (s.by == "code").any():
                # The model's own share, without the pairs the code answered:
                # what the judge is actually worth where it is used.
                m = s.by == "model"
                out["model_only"] = out.get("model_only", {})
                out["model_only"][label] = _score(truth[m], s.judge_same[m])
            if reading == "rechecked" or q != "role":
                for g, sg in s.groupby("group"):
                    sc = _score(truth[sg.index], sg.judge_same)
                    out["groups"].setdefault(label, {})[g] = {k: sc[k] for k in (
                        "pairs", "agreement", "judge_different_truth_same", "judge_same_truth_different")}
    out["passes"] = {q: all(v["passes"] for k, v in out["scores"].items()
                            if k.startswith(q + "/") and "/blind" not in k) for q in SCORED}
    a["truth"] = a.same
    a.loc[(a.question != "role"), "truth"] = a.same_blind
    errors = a[a.judge_same.notna() & (a.judge_same.astype(bool) != a.truth)]
    if (a.question == "strict").any():
        errors = errors[~((errors.question == "strict") & (errors.source == "human")
                          & (errors.decision != "merged"))]
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"eval_{name}_{prompt}_{part}"
    errors[["id", "source", "kind", "group", "question", "a", "b", "context", "truth", "text"]].to_csv(
        OUT / f"{stem}_errors.csv", index=False, encoding="utf-8-sig")
    (OUT / f"{stem}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8080")
    p.add_argument("--name", required=True, help="the model's name: answers are cached under it")
    p.add_argument("--prompt", default="v2", choices=sorted(PROMPTS))
    p.add_argument("--part", default="dev", choices=["dev", "holdout"])
    args = p.parse_args(argv)
    out = evaluate(args.url, args.name, args.prompt, args.part)
    print(json.dumps({k: out[k] for k in ("judge", "prompt", "part", "seconds_per_question", "passes")}))
    for title, scores in (("all pairs", out["scores"]), ("model only", out.get("model_only", {}))):
        print(f" {title}")
        for k, v in scores.items():
            print(f"  {k:32} agree {v['agreement']}  kappa {v['kappa']}  n {v['answered']}"
                  f"  (judge diff/truth same {v['judge_different_truth_same']},"
                  f" judge same/truth diff {v['judge_same_truth_different']})")


if __name__ == "__main__":
    sys.exit(main())
