"""The LLM splitting pass: generative re-heading, on the residue only.

Everything cheaper has been tried and measured. Rules took atomisation from
0.66/0.41 to 0.761/0.612 and reach 0.897/0.787 on short segments; recursion made
precision worse; dependency parsing misreads verbless fragments; POS-based
modifier distribution is correct but moves no gate figure. What remains is the
one operation none of them can perform — **inventing a head that is not in the
source text**. The labeller turns

    Experience applying AI to complex financial domains, including credit

into `Experience with credit`, and no pattern, parse or tagger produces
`Experience with` from that sentence. That is generation, and it is why this
module exists.

Three properties matter more than the prompt.

**It runs on the residue, not the corpus.** `atomise.route` labels each segment
and only `llm` rows arrive here — 31,510 unique segments, 23.8% of the
vocabulary, about 616k input tokens. The router was tuned for recall (0.880,
0.929 held out) because a wasted call is cheap and a dropped requirement is
permanent.

**Nothing identifying is sent.** The payload is requirement text and nothing
else: no `vacancy_id`, no company, no industry, no geography. `dry_run` writes
the exact bytes that would leave the machine so they can be reviewed first.

**It is cached and resumable by content.** The cache key is the normalised
segment, so a rerun costs nothing on work already done and the corpus can be
processed in batches over several sessions without double billing.

The prompt is versioned. Any change to it invalidates the cache for affected
rows, because a split produced under different instructions is not comparable
to one produced under these.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import atomise as atom
from . import config

PROMPT_VERSION = "split-v3-paren"

# Mirrors `validation/GUIDE.md`, because the extractor and the reference
# standard have to encode the same convention or the measured gap is our own
# specification error rather than a property of the model. The rules below are
# the ones the human labeller was given, in the same order.
SYSTEM_PROMPT = """\
You split job-requirement text into individual requirements.

Return ONLY a JSON array of strings. No prose, no explanation, no markdown.

Rules, in order of precedence:

1. Each requirement must STAND ON ITS OWN when read in isolation. Repeat the
   governing head on every item: "Experience with Python and SQL" becomes
   ["Experience with Python", "Experience with SQL"], never ["Python", "SQL"].
2. Where the natural head is not in the text, WRITE ONE. In "Experience
   applying AI to complex financial domains, including credit, restructuring",
   the listed items are separate requirements and their natural head is
   "Experience with": ["Experience applying AI to complex financial domains",
   "Experience with credit", "Experience with restructuring"].
3. Alternatives are separate requirements, and the cross-product is FULL —
   expand EVERY list of alternatives in the sentence, including qualifiers and
   context, not just the first list. "Bachelor's or Master's in CS or Maths"
   becomes four: Bachelor's/CS, Master's/CS, Bachelor's/Maths, Master's/Maths.
   "3 years as an A, B or C engineer, in a D or E context" becomes six: each
   role against each context.
4. Vague filler that names nothing is DROPPED, not kept as a requirement:
   "or similar", "and more", "etc.", "or a related field", "or equivalent".
5. Modifiers of one thing stay together. "excellent written and verbal
   communication" is ONE requirement. "fluent German and English" is TWO,
   because two distinct languages are named.
6. A requirement plus its qualifier stays together: "5 years of experience in
   sales" is one requirement, not two.
7. Brackets depend on how many items they hold. ONE example stays attached:
   "version control (such as Git)" is one requirement. A LIST of two or more
   items inside brackets is a list to expand, distributing the head and
   dropping the generic noun it exemplifies: "at least one integration platform
   (Boomi, MuleSoft, Talend, etc.)" becomes ["Experience with Boomi",
   "Experience with MuleSoft", "Experience with Talend"].
7b. A slash between two words joined to a shared noun expands: "sizing/error
   budget development" becomes ["sizing development", "error budget
   development"], and "and/or" means both. Leave product names alone —
   "ACC/BIM360" and "C#" are single names.
8. Preserve the SOURCE LANGUAGE. Do not translate. Do not correct spelling.
9. Invent no requirement that is not asked for in the text. If the text
   contains no requirement at all, return [].

Output the JSON array only."""


# --- few-shot variant --------------------------------------------------------
# Every example below is drawn from the DEVELOPMENT half of the labelled sample.
# None comes from the held-out half, so the holdout score stays an out-of-sample
# measurement — showing the model a holdout row would make the gate figure a
# report on its own answer key.
#
# The examples exist because the convention is idiosyncratic and the rules alone
# leave it underdetermined. Measured evidence for that: 108 of 435 predicted
# atoms went unmatched under rules-only prompting, diffusely rather than in one
# systematic error, which is the signature of a model guessing at wording rather
# than misreading structure.
FEWSHOT_EXAMPLES = [
    (
        "3+ years of experience as a Product Assurance, Software Quality Assurance, "
        "or Software V&V engineer, preferably in a space or safety-critical "
        "embedded systems context.",
        [
            "3+ years of experience as a Product Assurance engineer in a space context",
            "3+ years of experience as a Product Assurance engineer in a safety-critical embedded systems context",
            "3+ years of experience as a Software Quality Assurance engineer in a space context",
            "3+ years of experience as a Software Quality Assurance engineer in a safety-critical embedded systems context",
            "3+ years of experience as a Software V&V engineer in a space context",
            "3+ years of experience as a Software V&V engineer in a safety-critical embedded systems context",
        ],
    ),
    (
        "Experience applying AI to complex financial and legal domains, including "
        "credit, restructuring, debt instruments",
        [
            "Experience applying AI to complex financial domains",
            "Experience applying AI to complex legal domains",
            "Experience with credit",
            "Experience with restructuring",
            "Experience with debt instruments",
        ],
    ),
    (
        "Strong programming skills in languages such as Python, Java, or similar",
        [
            "Strong programming skills in Python",
            "Strong programming skills in Java",
        ],
    ),
    (
        "Solid understanding of customer data flows, including consent, identity, "
        "preferences and segmentation",
        [
            "Solid understanding of customer data flows",
            "Understanding of consent",
            "Understanding of identity",
            "Understanding of preferences",
            "Understanding of segmentation",
        ],
    ),
    (
        "Erfolgreich abgeschlossenes Studium der Betriebswirtschaft, "
        "Wirtschaftswissenschaften oder einer vergleichbaren Fachrichtung",
        [
            "Erfolgreich abgeschlossenes Studium der Betriebswirtschaft",
            "Erfolgreich abgeschlossenes Studium der Wirtschaftswissenschaften",
        ],
    ),
    (
        "Excellent written and verbal communication and a proactive attitude",
        [
            "Excellent written and verbal communication",
            "A proactive attitude",
        ],
    ),
]


def _render_fewshot() -> str:
    lines = ["", "Worked examples. Match this style exactly.", ""]
    for seg, atoms in FEWSHOT_EXAMPLES:
        lines.append(f"INPUT: {seg}")
        lines.append("OUTPUT: " + json.dumps(atoms, ensure_ascii=False))
        lines.append("")
    return "\n".join(lines)


SYSTEM_PROMPT_FEWSHOT = SYSTEM_PROMPT + "\n" + _render_fewshot()

PROMPTS = {
    "split-v3-paren": SYSTEM_PROMPT,
    "split-v1": SYSTEM_PROMPT,
    "split-v2-fewshot": SYSTEM_PROMPT_FEWSHOT,
}


def _cache_key(segment: str, prompt_version: str | None = None) -> str:
    """Content-addressed, and versioned by prompt.

    Keying on the normalised segment means the same wording anywhere in the
    corpus is paid for once. Including the prompt version means a change to the
    instructions does not silently reuse splits made under the old ones.
    """
    version = prompt_version or PROMPT_VERSION
    payload = f"{version}\x00{atom.normalise(segment)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class SplitCache:
    """A JSONL cache on disk, appended to as work completes.

    Append-only rather than rewritten so an interrupted run — a dropped
    connection, a rate limit, a closed laptop — loses at most the batch in
    flight, and so the file is a readable audit trail of what was asked and
    what came back.
    """

    path: Path
    prompt_version: str = PROMPT_VERSION
    entries: dict[str, list[str]] = field(default_factory=dict)

    def load(self) -> "SplitCache":
        if self.path.exists():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("prompt_version", PROMPT_VERSION) != self.prompt_version:
                        continue
                    self.entries[rec["key"]] = rec["atoms"]
        return self

    def get(self, segment: str) -> list[str] | None:
        return self.entries.get(_cache_key(segment, self.prompt_version))

    def put(self, segment: str, atoms: list[str]) -> None:
        key = _cache_key(segment, self.prompt_version)
        self.entries[key] = atoms
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "key": key, "prompt_version": self.prompt_version,
                "segment": segment, "atoms": atoms,
            }, ensure_ascii=False) + "\n")


def residue(df) -> list[str]:
    """The unique segments the rules could not split, in corpus order."""
    seen, out = set(), []
    for must_have in df["must_have"]:
        for seg in atom.segments(must_have):
            if seg in seen:
                continue
            seen.add(seg)
            if atom.route(seg)[1] == "llm":
                out.append(seg)
    return out


def dry_run(segments: list[str], out_path) -> dict:
    """Write exactly what would be sent, and send nothing.

    The point is that the data-sharing decision should be made against the real
    payload rather than a description of it. This writes that payload, reports
    its size, and asserts that no identifying field is present.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chars = sum(len(s) for s in segments)
    with open(out_path, "w", encoding="utf-8") as fh:
        for s in segments:
            fh.write(json.dumps({"segment": s}, ensure_ascii=False) + "\n")

    return {
        "n_segments": len(segments),
        "characters": chars,
        "approx_input_tokens": round(chars / 4),
        "prompt_version": PROMPT_VERSION,
        "payload": str(out_path),
        "fields_sent": ["segment"],
        "identifiers_sent": [],
    }


# --- request construction ----------------------------------------------------

MODEL = "claude-opus-5"

# Segments per request. The system prompt is the same on every call, so sending
# one segment per call would pay for it 31,510 times — it dominates the bill at
# that granularity. Packing amortises it, and a numbered input with an
# id-keyed schema keeps the mapping unambiguous, which a flat list of arrays
# would not: a model that returns 19 arrays for 20 inputs would silently
# misalign every subsequent requirement.
SEGMENTS_PER_REQUEST = 20

# `effort` is deliberately a parameter and deliberately starts high. Splitting
# with generative re-heading is the intelligence-sensitive part of this
# pipeline, and the honest order is to measure quality on the 149 labelled
# segments first — pennies — and only then decide whether the corpus run can
# drop to `medium`. Choosing low effort before measuring would trade the gate
# for a saving of a few dollars.
DEFAULT_EFFORT = "high"

# Structured output: one entry per input id. `additionalProperties: false` and a
# full `required` list are what make the schema strict rather than advisory.
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "atoms": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "atoms"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    },
}


def build_request(chunk: list[str], index: int, model: str = MODEL, effort: str = DEFAULT_EFFORT):
    """One batch request covering several segments.

    The system prompt carries `cache_control`, so after the first request it is
    read from cache at a fraction of the price rather than re-billed 1,575
    times. Nothing volatile precedes it — the numbered segments go in the user
    turn, which is where the per-request variation belongs.
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    numbered = "\n".join(f"{i}. {seg}" for i, seg in enumerate(chunk))
    return Request(
        custom_id=f"seg-{index}",
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            output_config={"effort": effort, "format": RESPONSE_SCHEMA},
            messages=[{
                "role": "user",
                "content": (
                    "Split each numbered requirement text below. Return one "
                    "entry per id, with the same id.\n\n" + numbered
                ),
            }],
        ),
    )


def submit_batch(segments: list[str], client=None, model: str = MODEL,
                 effort: str = DEFAULT_EFFORT) -> str:
    """Submit the residue as one batch and return its id.

    The Batches API is the right surface here for two reasons beyond the 50%
    price: nothing about this job is latency-sensitive, and a batch is a single
    reviewable submission rather than 1,576 opportunities for a partial run.
    """
    if client is None:
        raise RuntimeError(
            "No client configured. This sends requirement text to a third-party "
            "API — review `dry_run`'s payload first, then pass a client."
        )

    chunks = [segments[i:i + SEGMENTS_PER_REQUEST]
              for i in range(0, len(segments), SEGMENTS_PER_REQUEST)]
    requests = [build_request(c, i, model, effort) for i, c in enumerate(chunks)]
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def collect_batch(batch_id: str, segments: list[str], cache_path, client=None) -> dict:
    """Read a finished batch into the cache, keyed by segment text.

    Results arrive in **any** order, so they are matched by `custom_id` and the
    id inside each entry — never by position. A request that errored is counted
    and left uncached so a rerun retries exactly those and nothing else.
    """
    import json as _json

    if client is None:
        raise RuntimeError("No client configured.")

    cache = SplitCache(Path(cache_path)).load()
    chunks = [segments[i:i + SEGMENTS_PER_REQUEST]
              for i in range(0, len(segments), SEGMENTS_PER_REQUEST)]

    ok = errored = expired = 0
    for result in client.messages.batches.results(batch_id):
        kind = result.result.type
        if kind != "succeeded":
            errored += kind == "errored"
            expired += kind in ("expired", "canceled")
            continue

        chunk_index = int(result.custom_id.split("-")[1])
        chunk = chunks[chunk_index]
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            payload = _json.loads(text)
        except _json.JSONDecodeError:
            errored += 1
            continue

        for entry in payload.get("results", []):
            i = entry.get("id")
            if not isinstance(i, int) or not 0 <= i < len(chunk):
                continue
            atoms = [a.strip() for a in entry.get("atoms", []) if a and a.strip()]
            if atoms:
                cache.put(chunk[i], atoms)
                ok += 1

    return {"cached": ok, "errored": errored, "expired": expired,
            "cache_path": str(cache_path)}


def split_batch(segments: list[str], client=None, model: str = MODEL,
                effort: str = DEFAULT_EFFORT) -> dict[str, list[str]]:
    """Submit, wait, and return segment -> atoms.

    Raises rather than silently falling back: a splitter that quietly returned
    the input unsplit would produce a recall figure that looks like a
    measurement and is not.
    """
    import time

    if client is None:
        raise RuntimeError(
            "No LLM client configured. This pass sends requirement text to a "
            "third-party API, which needs Karimi's explicit agreement first — "
            "see the conventions in CLAUDE.md. Run `dry_run` to review the "
            "exact payload, then pass a configured client here."
        )

    batch_id = submit_batch(segments, client=client, model=model, effort=effort)
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        time.sleep(60)

    import tempfile

    tmp = Path(tempfile.gettempdir()) / f"karimi_split_{batch_id}.jsonl"
    collect_batch(batch_id, segments, tmp, client=client)
    return SplitCache(tmp).load().entries


def split_with_cache(segments: list[str], cache_path, client=None, model: str | None = None) -> dict:
    """Return cached splits and report what is still outstanding.

    Usable before any API access exists: with no client it reports how much of
    the residue is already covered and what a run would still cost, which is
    the number needed to decide whether to run it at all.
    """
    cache = SplitCache(Path(cache_path)).load()

    done, todo = {}, []
    for seg in segments:
        hit = cache.get(seg)
        if hit is None:
            todo.append(seg)
        else:
            done[seg] = hit

    if todo and client is not None:
        fresh = split_batch(todo, client=client, model=model)
        for seg, atoms in fresh.items():
            cache.put(seg, atoms)
            done[seg] = atoms
        todo = []

    chars = sum(len(s) for s in todo)
    return {
        "cached": len(done),
        "outstanding": len(todo),
        "outstanding_chars": chars,
        "outstanding_approx_tokens": round(chars / 4),
        "prompt_version": PROMPT_VERSION,
        "splits": done,
    }


def api_key_present() -> bool:
    """Whether any provider key is configured in the environment."""
    return any(os.environ.get(k) for k in
               ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"))


# --- OpenAI path -------------------------------------------------------------
#
# Karimi's choice, 2026-09-04: run the residue through a mini model. The
# architecture is unchanged — routing, the prompt, the cache and the dry run are
# provider-agnostic, and only the call differs — so the provider is a parameter
# of the experiment rather than a property of the pipeline.
#
# The model ID is pinned to a dated snapshot, not the floating alias. The Week 1
# task list requires the model and parameters to be logged, and `gpt-5.4-mini`
# silently becoming a different model between the validation run and the corpus
# run would invalidate the comparison between them.

OPENAI_MODEL = "gpt-5.4-mini-2026-03-17"

OPENAI_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "requirement_splits",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "atoms": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "atoms"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["results"],
            "additionalProperties": False,
        },
    },
}


def load_openai_client(env_path: str = ".env"):
    """Read the key from `.env` and return a client.

    The variable is read by name rather than relying on the SDK's own lookup,
    because this project stores it as `OpenAi_API_key` and the SDK expects
    `OPENAI_API_KEY`. The key is never logged or returned.
    """
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(env_path)
    key = (os.environ.get("OpenAi_API_key")
           or os.environ.get("OPENAI_API_KEY"))
    if not key:
        raise RuntimeError(
            f"No OpenAI key found. Expected `OpenAi_API_key` or "
            f"`OPENAI_API_KEY` in {env_path}."
        )
    return OpenAI(api_key=key)


def _user_turn(chunk: list[str]) -> str:
    numbered = "\n".join(f"{i}. {seg}" for i, seg in enumerate(chunk))
    return ("Split each numbered requirement text below. Return one entry per "
            "id, with the same id.\n\n" + numbered)


def openai_body(chunk: list[str], model: str = OPENAI_MODEL,
                prompt_version: str = PROMPT_VERSION) -> dict:
    """The request body for one chunk, shared by the sync and batch paths."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPTS[prompt_version]},
            {"role": "user", "content": _user_turn(chunk)},
        ],
        "response_format": OPENAI_SCHEMA,
    }


def _parse_chunk_response(text: str, chunk: list[str]) -> dict[str, list[str]]:
    """Map a response back onto its inputs by id, never by position."""
    out: dict[str, list[str]] = {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return out
    for entry in payload.get("results", []):
        i = entry.get("id")
        if not isinstance(i, int) or not 0 <= i < len(chunk):
            continue
        atoms = [a.strip() for a in entry.get("atoms", []) if a and a.strip()]
        if atoms:
            out[chunk[i]] = atoms
    return out


def split_openai_sync(segments: list[str], client, cache_path=None,
                      model: str = OPENAI_MODEL, per_request: int = SEGMENTS_PER_REQUEST,
                      prompt_version: str = PROMPT_VERSION) -> dict:
    """Split synchronously, for runs small enough not to need the batch queue.

    Used for the validation pass over the labelled segments: a few hundred
    items is not worth the upload/poll/download cycle, and getting the answer
    in one go is what makes it usable as a gate measurement.

    Token usage is returned as reported by the API rather than estimated, so
    the corpus projection rests on a measurement.
    """
    cache = SplitCache(Path(cache_path), prompt_version).load() if cache_path else None
    chunks = [segments[i:i + per_request] for i in range(0, len(segments), per_request)]

    splits: dict[str, list[str]] = {}
    in_tok = out_tok = failures = 0
    for chunk in chunks:
        resp = client.chat.completions.create(**openai_body(chunk, model, prompt_version))
        text = resp.choices[0].message.content or ""
        parsed = _parse_chunk_response(text, chunk)
        if not parsed:
            failures += 1
        for seg, atoms in parsed.items():
            splits[seg] = atoms
            if cache:
                cache.put(seg, atoms)
        if resp.usage:
            in_tok += resp.usage.prompt_tokens or 0
            out_tok += resp.usage.completion_tokens or 0

    return {"model": model, "prompt_version": prompt_version,
            "n_segments": len(segments), "n_requests": len(chunks),
            "n_split": len(splits), "chunk_failures": failures,
            "input_tokens": in_tok, "output_tokens": out_tok,
            "splits": splits}


def submit_openai_batch(segments: list[str], client, work_dir,
                        model: str = OPENAI_MODEL,
                        per_request: int = SEGMENTS_PER_REQUEST) -> str:
    """Upload the residue as a JSONL batch and return the batch id.

    The batch endpoint takes a file, not inline requests, so the payload is
    written to disk first — which has the useful side effect that the exact
    bytes being sent are reviewable before submission.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"batch_input_{PROMPT_VERSION}.jsonl"

    chunks = [segments[i:i + per_request] for i in range(0, len(segments), per_request)]
    with open(path, "w", encoding="utf-8") as fh:
        for i, chunk in enumerate(chunks):
            fh.write(json.dumps({
                "custom_id": f"seg-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": openai_body(chunk, model),
            }, ensure_ascii=False) + "\n")

    with open(path, "rb") as fh:
        uploaded = client.files.create(file=fh, purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    return batch.id


def collect_openai_batch(batch_id: str, segments: list[str], cache_path, client,
                         per_request: int = SEGMENTS_PER_REQUEST) -> dict:
    """Read a finished OpenAI batch into the cache.

    Results are keyed by `custom_id` and then by the id inside each entry;
    order is never assumed. Chunks that errored stay uncached so a rerun
    retries exactly those.
    """
    batch = client.batches.retrieve(batch_id)
    if batch.status != "completed":
        return {"status": batch.status, "cached": 0}

    cache = SplitCache(Path(cache_path)).load()
    chunks = [segments[i:i + per_request] for i in range(0, len(segments), per_request)]

    content = client.files.content(batch.output_file_id).text
    ok = errored = 0
    for line in content.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("error") or rec.get("response", {}).get("status_code") != 200:
            errored += 1
            continue
        idx = int(rec["custom_id"].split("-")[1])
        body = rec["response"]["body"]
        text = body["choices"][0]["message"]["content"] or ""
        parsed = _parse_chunk_response(text, chunks[idx])
        if not parsed:
            errored += 1
        for seg, atoms in parsed.items():
            cache.put(seg, atoms)
            ok += 1

    return {"status": batch.status, "cached": ok, "errored": errored,
            "cache_path": str(cache_path)}
