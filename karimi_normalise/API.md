# karimi-normalise API

The same results as the `karimi-normalise` library, computed on our side, in
the EU (Google Cloud, `europe-west1`). Every answer carries the version of
the rules and of the dictionary that made it.

Interactive documentation, generated from the code: `<URL>/docs`.

## The quickest try: your own CSV

```bash
pip install requests
curl -O <URL>/try_api.py
python try_api.py adverts.csv --url <URL> --key <KEY> --limit 200
```

It reads your CSV, sends the rows in batches of 200, and writes next to it
`adverts_normalised.csv`: **your rows, every column kept**, plus the added
ones (the role, the counts, the groups and topics found). Add
`--per-requirement` for a second file with one row per requirement, if you
want to count or pivot by requirement.

It finds the columns `must_have` (required), `id`, `title` (or `job_title`,
`job_title_english`) and `language` by name; other names with
`--col-must-have`, `--col-id`, `--col-title`. A `must_have` cell can be a JSON
list, one requirement per line, or items separated by ` | ` or `;`.

**What is most useful to us:** 100-200 software or data adverts (the
dictionary was built from those; other roles mostly come back `nuovo`), in
any language, with an `id`. Then a look at 20 rows of `adverts_normalised.csv`
and `adverts_requirements.csv`: is the advert split into the right number of
requirements? are the groups sensible? Rows that look wrong, with their `id`,
are the most valuable thing you can send back.

All processing happens in the EU (Google Cloud, Belgium); nothing is sent to
any other service. The input and results of each run are kept in our project
for 30 days, so we can read them with you, then deleted; the public site
shows only aggregate numbers, never the text of an advert.

## Access

For the trial, every request carries the key we sent you, in the `X-API-Key`
header. Keep it out of code you share; we can rotate it at any time. If the
service becomes permanent, access moves to Google identities (IAM), which
needs no key.

```python
import requests

URL = "https://karimi-api-....run.app"       # sent separately
H = {"X-API-Key": "..."}                      # sent separately
requests.get(f"{URL}/health").json()          # open: versions in service
```

Or from a shell:

```bash
curl -X POST "$URL/v1/process" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"postings":[{"id":"1","title":"Data Engineer","must_have":["3+ years of Python and SQL"]}]}'
```

## A posting

The same fields as the library's `process()`:

| Field | Type | |
|---|---|---|
| `must_have` | list of str | required |
| `title` | str | optional; the English title if you have one |
| `id` | str or int | optional; returned as given |
| `language` | str, e.g. `"Deutsch"` | optional fallback for very short items |
| `must_have_english` | list of str, aligned with `must_have` | optional: your own translation, used as given |

## Up to 200 postings: one call

```python
r = requests.post(f"{URL}/v1/process", headers=H, json={"postings": [
    {"id": "ad-1", "title": "Senior Data Engineer (m/w/d)",
     "must_have": ["3+ years of Python and SQL", "Fließende Deutschkenntnisse"]}]})
r.json()["postings"][0]["requirements"]    # one dict per requirement
r.json()["report"]["overall"]              # green / yellow / red
```

`"translate": false` in the body skips translation: non-English items are
then split as written.

The answer also carries `job` and `files`: the call is kept like a job, so
the same CSV tables and the check (below) exist for it. Any extra scalar
field you put on a posting (`company`, `country`, your own ids) is ignored by
the rules and comes back as a column of `postings.csv`.

## More: a job

A job runs for as long as it needs. Measured: about 1.3 minutes per 1,000
`must_have` items with a quarter of them translated, so 100,000 requirements
(~50,000 items) take about an hour. Most of it is translation: send
`must_have_english` and it is faster still. `/v1/process` answers 200
postings in one to three minutes.

```python
job = requests.post(f"{URL}/v1/jobs", headers=H, json={}).json()
# 1. upload: one posting per line (JSONL), to the signed URL; no token needed there
up = job["upload"]
requests.put(up["url"], headers=up["headers"], data=open("postings.jsonl", "rb"))
# 2. start
requests.post(f"{URL}/v1/jobs/{job['job']}/start", headers=H)
# 3. wait: state goes created -> queued -> running -> done (or failed)
requests.get(f"{URL}/v1/jobs/{job['job']}", headers=H).json()     # postings_done / postings_total
# 4. fetch: signed links, valid one hour
res = requests.get(f"{URL}/v1/jobs/{job['job']}/result", headers=H).json()
results = requests.get(res["results"]).text.splitlines()          # JSONL, one posting per line
report = requests.get(res["report"]).json()
open("postings.csv", "wb").write(requests.get(res["postings"]).content)
open("requirements.csv", "wb").write(requests.get(res["requirements"]).content)
```

Poll every minute or two; a job's files are deleted after **30 days**.

`res["check"]` appears a few minutes after `done`: our check of the run
(below). It may be `null` until then.

## The two CSV tables

For spreadsheets, beside the JSONL:

| File | One row per | Columns |
|---|---|---|
| `postings.csv` | posting | every scalar field you sent (`id`, `title`, ...), then the added ones: `title_role`, `title_level`, `title_name`, `title_match`, `n_items`, `n_requirements`, `n_known`, `n_group`, `n_topic`, `n_nuovo`, `n_items_kept_whole`, `req_names` (every counted requirement by name), `req_groups`, `req_topics` (joined with ` \| `), versions |
| `requirements.csv` | requirement | `posting_id`, the item as written, the requirement, its fields, group, topic, `match`, `match_cosine`, `match_via`, the title's role repeated |

Join `postings.csv` to your own table on `id`: that is the "added columns"
view. UTF-8, comma-separated, header row.

## What comes back

Each requirement:

| Field | |
|---|---|
| `item`, `item_split` | the item as written, and what was split (its English translation, or itself) |
| `translated`, `translated_by` | whether it was translated, and by what (`opus-mt`, `given`) |
| `atom`, `atom_norm` | the single requirement, as split and normalised |
| `req_name` | the requirement as a reader names it: `Python`, `English`, `Education in Physics` |
| `years_min`, `years_max`, `level` | taken out of the text into their own fields |
| `degree` | for a degree: `bachelor`, `master`, `phd`, `mba`, `degree` (level not named) or `student` |
| `head`, `head_group`, `core` | how it is asked (`experience`, `competence`, `ability`, `language`, `education`) and what is asked for |
| `req_group`, `req_topic` | same requirement, same theme. Since rules 0.3.0 the group does not depend on how it is asked: `Experience with Python` and `Knowledge of Python` are both `python`; degrees are `education: physics` whatever the level |
| `match`, `match_cosine`, `match_via` | how it was found (below), how close, and the known requirement it was placed by |
| `nice_to_have`, `counted` | flagged as optional; counted in the requirement total |
| `rules_version`, `dict_version` | what made this row |

`match`:

| | |
|---|---|
| `known` | the dictionary holds this requirement, word for word |
| `group` | the nearest known one is very close (cosine >= 0.90): same requirement |
| `topic` | close (0.80-0.90): same theme, not the same requirement |
| `nuovo` | nothing close enough: new to the dictionary |
| `empty` | nothing left once years and level were taken out |

A title: `title_role`, `title_level`, `title_extra`, `title_group`,
`title_name`, and `match` = `known`, `variant` (a spelling variant of a known
role) or `nuovo`.

## The report and the check

`report` compares your run with runs of the same size from the data our
quality figures were measured on: each signal green, yellow or red, and
`to_check`, the items worth reading. It says whether the run looks like the
measured data, not how much of it is right; for that, `GET /quality`.

`check` is what our check found after the run: whether it ended well, the
report's lights, a sample of the decisions taken by similarity judged by a
calibrated model, and whether a signal has been drifting over recent jobs.
It flags, it never changes a result. A red check alerts us too.

## Errors

| Code | Meaning |
|---|---|
| 400 | a line of the upload is not a posting (the message names the line) |
| 401 / 403 | no token, or an account without access |
| 404 | no such job |
| 409 | the job is not in the state the call needs (e.g. starting it twice) |
| 413 | more than 200 postings in `/v1/process`: use a job |

## What we keep

`must_have` and titles only, never whole adverts. Job files 30 days, then
deleted. Logs hold counts and codes, never requirement text. Everything in
the EU.
