"""The explorer agent: a language model reads what the run made of an item and says what looks wrong.

The inspector's detectors find only the kinds someone already named
(`errors.inspect`); batch 1 showed what that misses. The explorer reads the
employer's item beside the requirements the run made of it, with the counting
guide and the archivist's catalogue, and answers per item: fine, or each
problem with the catalogue's id when it is a known kind and ``new`` when it is
not, plus a short general pattern a person can turn into a detector.

Measured 2026-11-16 (`New project/score_explorer.py`, prompt x1): Gemini 3.5
Flash and Qwen3-14B both found 40 of 40 known errors in batch 1, Gemini naming
97.5% with the catalogue's id; on items no detector flagged, about two of
Gemini's flags in three read as real, several of kinds nobody had named. But
against the hand counts both were right on 33% of their split flags, under
the 60% bar: a model's verdict is NOT an error count. So, the user's call of
the same day: Gemini reads a SAMPLE of each run (`explore`), groups what it
finds into kinds (`group`), and reports them; a kind not in the catalogue is a
candidate a person confirms before it gets a detector. It never colours a run.

Any OpenAI-compatible chat endpoint: llama-server, or Vertex AI's on the EU
multi-region (`aiplatform.eu.rep.googleapis.com`, location `eu`), the only
place this project reaches a Gemini model; never the global endpoint.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections import defaultdict

import requests

from . import archivist

AGENT = "explorer"
PROMPT_VERSION = "x2"
SAMPLE = 30
MODEL = "google/gemini-3.5-flash"
EU_HOST, EU_LOCATION = "aiplatform.eu.rep.googleapis.com", "eu"

_RULES = """\
You check an automatic pipeline that turns one line of a job advert (an "item")
into separate requirements and gives each a normalised key. Say whether what it
made is right.

How requirements are counted (the guide the people who checked it used):
- one per thing in a list: "Experience with AWS, Azure or GCP" = 3;
- skills sharing one noun split: "Analytical and problem-solving skills" = 2;
- alternatives multiply: "Bachelor's or Master's in CS or Maths" = 4;
- verbs sharing one object are one: "building and maintaining CI/CD pipelines" = 1;
- modes of one skill are one: "Excellent written and verbal communication" = 1;
- one per language: "Fluent German and English" = 2;
- a generic category before examples does not count: "Scripting languages such as Python or Bash" = 2;
- "ideally", "preferably", "is a plus", "preferred" qualify and add nothing; an item
  that is optional as a whole is marked optional;
- "or a related field", "or similar", "or equivalent qualification" add nothing;
  "or equivalent experience" is a second route and counts.

How keys look:
- a skill is its object, without "experience with", "knowledge of", "strong",
  years or level: "5+ years of strong Python experience" -> "Python";
- a language: "language: German"; a degree: "education: Bachelor in Computer
  Science", "education: Master (any field)";
- years, level and how much it is wanted live in other columns, not in the key.

Wrong is: a requirement lost or two left in one; a piece that is not a whole
requirement; a key that lost the object or names another thing; a frame or
marker word kept as the requirement ("Desirable", "is a plus"); a degree not read
as a degree; text left in another language or translated into nonsense.
Not wrong: wording you would have chosen differently when the object is right.
Judge the KEY: the requirement's own text is the employer's words, and may keep
"is a plus" or "required" when its key does not.
"""

_ANSWER = """\
Answer with JSON only:
{"ok": true}
or
{"ok": false, "problems": [{"stage": "split" | "normalisation" | "translation",
  "kind": "<an id from the known kinds, or new>",
  "what": "<what is wrong here, in a few words>",
  "pattern": "<the general shape of the mistake, for any item like this>"}]}
Report only clear mistakes. When it is right, answer {"ok": true}.
"""


def system_prompt(entries: list[dict] | None = None) -> str:
    known = "\n".join(f"- {e['id']}: {e['title']}" for e in (entries if entries is not None else archivist.catalogue())
                      if e.get("detector"))
    return f"{_RULES}\nKnown kinds of mistake:\n{known}\n\n{_ANSWER}"


def item_message(item: str, english: str | None, reqs: list[dict]) -> str:
    lines = [f"Item: {item}"]
    if english and english != item:
        lines.append(f"Item in English (machine translation): {english}")
    lines.append("Requirements made:" if reqs else "Requirements made: none")
    for r in reqs:
        flag = "" if r.get("counted", True) else "  [optional, not counted]"
        lines.append(f"- {r.get('atom', '')!r} -> key {r.get('key', '')!r}{flag}")
    return "\n".join(lines)


def _parse(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict) or "ok" not in out:
        return None
    out["problems"] = [p for p in out.get("problems") or [] if isinstance(p, dict)]
    if out["problems"]:
        out["ok"] = False
    return out


class Client:
    """One OpenAI-compatible chat endpoint. ``token`` is a function, called per
    request, so a Vertex AI access token can be refreshed."""

    def __init__(self, base_url: str, model: str, token=None, timeout: int = 600, extra: dict | None = None):
        self.base_url, self.model, self.token, self.timeout = base_url.rstrip("/"), model, token, timeout
        self.extra = extra or {}

    def ask(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token()}"
        # room for a model that reasons before it answers: at 600 half of
        # Gemini 3.5 Flash's answers came back empty, cut inside its reasoning
        body = {"model": self.model, "temperature": 0, "max_tokens": 4000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                **self.extra}
        for attempt in range(4):
            r = requests.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            if r.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        return ""


def read(client: Client, items: list[dict], entries: list[dict] | None = None) -> list[dict | None]:
    """Per item ({item, english, requirements}): the explorer's answer, or None when unreadable."""
    system = system_prompt(entries)
    out = []
    for it in items:
        try:
            out.append(_parse(client.ask(system, item_message(it["item"], it.get("english"), it["requirements"]))))
        except requests.RequestException:
            out.append(None)
    return out


def vertex_client(project: str | None = None, model: str = MODEL, token=None) -> Client:
    """Gemini on the EU multi-region. ``token`` defaults to the environment's
    Google credentials (the Cloud Run job's service account)."""
    project = project or os.environ.get("KARIMI_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if token is None:
        import google.auth
        import google.auth.transport.requests

        creds, found = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        project = project or found

        def token() -> str:
            if not creds.valid:
                creds.refresh(google.auth.transport.requests.Request())
            return creds.token

    url = f"https://{EU_HOST}/v1/projects/{project}/locations/{EU_LOCATION}/endpoints/openapi"
    return Client(url, model, token=token)


def sample(postings: list[dict], job: str, n: int = SAMPLE) -> list[dict]:
    """Up to ``n`` items of a run the inspector found nothing in: the known kinds
    are counted already, so the model's reading goes where no detector looks.
    Seeded by the job, so the same run draws the same items."""
    from .errors import inspector_flag

    items = []
    for p in postings:
        by_item: dict[int, list[dict]] = defaultdict(list)
        for r in p.get("requirements") or []:
            by_item[r.get("item_idx", 0)].append(r)
        for rs in by_item.values():
            if rs and not any(inspector_flag(r) for r in rs):
                items.append({"item": rs[0].get("item", ""),
                              "english": rs[0].get("item_split") if rs[0].get("translated") else None,
                              "requirements": rs})
    rnd = random.Random(job)
    return rnd.sample(items, min(n, len(items)))


_GROUP = """\
Below are problems a reviewer found in requirements extracted from job adverts.
Group them into KINDS of mistake: problems with the same cause go together.
For each kind give a short snake_case id, a title of a few words and one
sentence saying the general shape of the mistake. Never quote the adverts:
describe the shape ("a closing 'required' kept in the key"), not the case.
If a kind is one of these known ones, give its id as "catalogue": {known}.
Answer with JSON only:
{{"kinds": [{{"id": "...", "title": "...", "shape": "...", "stage": "split" | "normalisation" | "translation",
  "catalogue": "<known id or null>", "members": [<problem numbers>]}}]}}
"""


def group(client: Client, problems: list[dict], entries: list[dict] | None = None,
          rejected: list[str] = ()) -> list[dict]:
    """The problems of one run, grouped into kinds by the model; [] when unreadable.
    ``rejected``: kinds a person turned down, offered as known so the model
    names them again instead of proposing them as new."""
    if not problems:
        return []
    known = [e["id"] for e in (entries if entries is not None else archivist.catalogue())] + list(rejected)
    lines = [f"{k}. [{p.get('stage', '')}] {p.get('what', '')} | pattern: {p.get('pattern', '')}"
             for k, p in enumerate(problems)]
    try:
        text = client.ask(_GROUP.format(known=", ".join(known)), "\n".join(lines))
    except requests.RequestException:
        return []
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        kinds = json.loads(m.group(0)).get("kinds") if m else None
    except json.JSONDecodeError:
        kinds = None
    out = []
    for k in kinds or []:
        if not isinstance(k, dict) or not k.get("id"):
            continue
        members = [i for i in k.get("members") or [] if isinstance(i, int) and 0 <= i < len(problems)]
        cat = k.get("catalogue") if k.get("catalogue") in known else None
        out.append({"id": re.sub(r"\W+", "_", str(k["id"]).lower())[:40], "title": str(k.get("title", ""))[:80],
                    "shape": str(k.get("shape", ""))[:200], "stage": k.get("stage"), "catalogue": cat,
                    "members": members})
    return out


def _quotes(text: str, items: list[str]) -> bool:
    """Whether ``text`` repeats three words in a row of any item: then it is not
    a shape but a case, and does not leave the job's private files."""
    words = re.findall(r"\w+", text.lower())
    grams = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
    for it in items:
        w = re.findall(r"\w+", it.lower())
        if any(" ".join(w[i:i + 3]) in grams for i in range(len(w) - 2)):
            return True
    return False


def explore(postings: list[dict], job: str, client: Client, entries: list[dict] | None = None,
            n: int = SAMPLE, rejected: list[str] = ()) -> dict:
    """One run: a sample read, the problems grouped into kinds. Private (with cases).
    ``entries``: the catalogue with the kinds a person confirmed
    (`archivist.catalogue_with`); ``rejected``: the kinds a person turned down."""
    items = sample(postings, job, n)
    answers = read(client, items, entries)
    problems, owner = [], []
    for k, a in enumerate(answers):
        for p in (a or {}).get("problems") or []:
            problems.append(p)
            owner.append(k)
    kinds = group(client, problems, entries, rejected)
    texts = [it["item"] for it in items] + [r.get("atom", "") for it in items for r in it["requirements"]]
    for kd in kinds:
        kd["count"] = len({owner[i] for i in kd["members"]})
        kd["rejected_before"] = kd["catalogue"] in rejected
        kd["new"] = kd["catalogue"] is None
        kd["quotes"] = _quotes(f"{kd['title']} {kd['shape']}", texts)
        kd["cases"] = [{"item": items[owner[i]]["item"], "what": problems[i].get("what"),
                        "made": [(r.get("atom"), r.get("key")) for r in items[owner[i]]["requirements"]]}
                       for i in kd["members"][:5]]
    return {"agent": AGENT, "model": client.model, "prompt": PROMPT_VERSION, "sampled": len(items),
            "answered": sum(a is not None for a in answers), "flagged": sum(bool(a and not a["ok"]) for a in answers),
            "kinds": kinds}


def public(ex: dict | None) -> dict | None:
    """What leaves the job's files: counts, and a kind's title and shape only when
    they quote no item. No cases."""
    if not ex:
        return None
    keep = ("id", "stage", "catalogue", "new", "count", "rejected_before")
    return {k: ex.get(k) for k in ("agent", "model", "prompt", "sampled", "answered", "flagged")} | {
        "kinds": [{**{k: kd.get(k) for k in keep},
                   "title": None if kd.get("quotes") else kd.get("title"),
                   "shape": None if kd.get("quotes") else kd.get("shape")} for kd in ex.get("kinds") or []]}


def summary(runs: list[dict], last: int = 20, decided: dict[str, dict] | None = None) -> dict:
    """What the site shows: per run, what the explorer read and the kinds it found;
    the new ones are candidates a person confirms into the catalogue. ``decided``:
    kind id -> its latest decision (`archivist.latest_decisions`), so a candidate
    already decided shows its decision, never who took it."""
    decided = decided or {}
    entries = []
    for r in runs:
        ex = r.get("explorer")
        if ex:
            kinds = [{**kd, "decision": (decided.get(kd["id"]) or {}).get("decision")
                      if (decided.get(kd["id"]) or {}).get("job") == r.get("job") else None}
                     for kd in ex.get("kinds") or []]
            entries.append({"job": r.get("job"), "checked": r.get("checked"), **ex, "kinds": kinds})
    new = sum(bool(kd.get("new")) and not kd.get("decision") for e in entries for kd in e.get("kinds") or [])
    return {"agent": AGENT, "model": MODEL, "sample": SAMPLE, "runs": len(entries), "candidates": new,
            "entries": entries[-last:][::-1]}


def enabled() -> bool:
    return os.environ.get("KARIMI_EXPLORER", "").lower() == "vertex"


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .store import jf, open_store, read_json

    p = argparse.ArgumentParser(description="The explorer's kinds for one run, with their cases: what a person confirms.")
    p.add_argument("--job", required=True)
    a = p.parse_args(argv)
    ex = (read_json(open_store(), jf(a.job, "check.json")) or {}).get("explorer") or {}
    for kd in ex.get("kinds") or []:
        tag = "NEW" if kd.get("new") else f"= {kd.get('catalogue')}"
        print(f"{tag:28} {kd['id']} ({kd.get('count')}): {kd.get('title')} — {kd.get('shape')}")
        for c in kd.get("cases") or []:
            print(f"      {c['item'][:90]}\n        {c['what']}  | made: {c['made']}")
    if not ex:
        print("no explorer reading for this job")


if __name__ == "__main__":
    main()
