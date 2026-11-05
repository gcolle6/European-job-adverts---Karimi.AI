# karimi-normalise

Turns the `must_have` list of a job ad into single requirements, each with its
years, level and core in separate fields, a group (same requirement) and a
topic (same theme). Normalises job titles into roles the same way. Every
result carries the version of the rules and of the dictionary that made it.

It runs on your machine. No ad text leaves it: the models are downloaded once
and run locally.

## Install

Python 3.11 or later.

```bash
pip install "karimi-normalise[all] @ <package location>"
```

| Part | What it adds | Size on disk | Without it |
|---|---|---|---|
| base | the rules and the spaCy tagger (installed automatically) | ~15 MB plus spaCy | always needed |
| `[translate]` | opus-mt, the default translator: one model per source language, downloaded on first use | ~300 MB per model, 5 models for 7 languages | pass your own English text or your own translator |
| `[embed]` | the embedding model the dictionary was made with, downloaded on first use | ~460 MB | requirements the dictionary does not hold word for word come back `non_cercato` |
| `[all]` | both | | |

`torch` comes with either extra (~500 MB, CPU build is enough).

Then the **dictionary**, a folder you receive separately, one per version, for
example `dictionaries/0.1.0/`. It is checked on load: an edited dictionary is
refused.

To run without internet, download the models once with internet on, then set
`HF_HUB_OFFLINE=1`.

## Use

```python
from karimi_normalise import Dictionary, TranslationCache, process

d = Dictionary("dictionaries/0.1.0")
cache = TranslationCache("translate_cache.jsonl")      # optional; keep the file between runs

out = process([
    {"id": "ad-1", "title": "Senior Data Engineer (m/w/d)",
     "must_have": ["3+ years of Python and SQL", "Fließende Deutschkenntnisse"]},
], d, cache=cache)

for r in out["postings"][0]["requirements"]:
    print(r.atom_norm, "|", r.req_group, "|", r.req_topic, "|", r.match)
print(out["postings"][0]["title"].title_name)
print(out["report"]["overall"])                          # green / yellow / red
```

`process` is the one call to use. Pass many postings at once: translation, the
slow step, then runs once for the whole batch.

### Each posting

| Field | | |
|---|---|---|
| `must_have` | list of str | required |
| `title` | str | optional; give the English title if you have one |
| `id` | any | optional; returned as given |
| `language` | str, e.g. `"Deutsch"` | optional fallback, for very short items whose language cannot be read |
| `must_have_english` | list of str, aligned with `must_have` | optional: your own translation, used as given |

### Translation is your choice

Non-English items are translated to English before they are split; the rules
and the dictionary work on English. Three ways, in this order of preference
for you:

1. **your own English text**, in `must_have_english`;
2. **your own translator**: `process(..., translator=fn)`, where `fn` takes a
   list of `(language_code, text)` and returns `{(language_code, text): english}`;
3. **opus-mt**, the default, with `[translate]` installed.

The published quality figures were measured with opus-mt. With another
translator the split can differ slightly: compare the run report's signals
with a run made with opus-mt before relying on the figures. Every requirement
says which translator it went through (`translated_by`).

Languages without an opus-mt model (Polish, Czech, Lithuanian, ...) are split
as written: expect more `nuovo` there.

### The embedding is not your choice

The dictionary's vectors and its thresholds (0.90 same requirement, 0.80 same
theme) belong to one model, named in the dictionary's `manifest.json`. Another
model places phrases in a different space on a different scale, so it cannot
be swapped in: using one means rebuilding and re-validating the dictionary.

### What comes back

A requirement's `match`:

| `match` | meaning |
|---|---|
| `known` | the dictionary holds this requirement, word for word |
| `group` | the nearest known one is very close (cosine ≥ 0.90): same requirement |
| `topic` | close (0.80-0.90): same theme, not the same requirement |
| `nuovo` | nothing close enough: new to the dictionary |
| `non_cercato` | not looked up, because `[embed]` is not installed |
| `empty` | nothing left after years and level were taken out |

A title's `match`: `known`, `variant` (a spelling variant of a known role:
plural, `Fullstack` / `Full Stack`) or `nuovo`.

`out["report"]` compares the run with random runs of the same size from the
data the quality figures were measured on. Each signal gets green, yellow or
red, and `to_check` lists the items worth reading. It says whether the run
looks like the measured data, not how much of it is right: for that, see the
quality card of the version you use.

## Limits to know

* The dictionary was built from software and data job ads. Other roles split
  fine, but most of their requirements come back `nuovo`.
* One process handles one batch at a time: the rules keep state while they run.
  Run several processes for parallel work, not threads.
* Processing in the EU is recommended: the data are job ads, which can name
  the people who recruit.

## Keeping a history

```python
from karimi_normalise import log_run
log_run(out["report"], "runs.jsonl")
```

One line per run: versions, counts, each signal's value and light. No
requirement text, so the file can be shared without the ads, for example to
tell us when a signal drifts.
