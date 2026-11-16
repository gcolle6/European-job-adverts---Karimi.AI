"""The explorer agent: a language model reads what the run made of an item and says what looks wrong.

The inspector's detectors find only the kinds someone already named
(`errors.inspect`); batch 1 showed what that misses. The explorer reads the
employer's item beside the requirements the run made of it, with the counting
guide and the archivist's catalogue, and answers per item: fine, or each
problem with the catalogue's id when it is a known kind and ``new`` when it is
not, plus a short general pattern a person can turn into a detector.

Asked 2026-11-16. NOT TRUSTED YET: a model reading splits was tried on
2026-11-07 (the local judge counting items: 28% and 21% of its flags right,
against 60% fixed before) and failed. So the explorer runs only in
`New project/score_explorer.py` until a model passes the same bar on the blind
half of the hand counts; which model is the user's call on the numbers
(Gemini on Vertex AI in the EU, or an open model we run).

Any OpenAI-compatible chat endpoint: llama-server, or Vertex AI's
`.../locations/europe-west1/endpoints/openapi` (a regional endpoint, so the
text is processed in the EU; never the global one).
"""

from __future__ import annotations

import json
import re
import time

import requests

from . import archivist

PROMPT_VERSION = "x1"

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
