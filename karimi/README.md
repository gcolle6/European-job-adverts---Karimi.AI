# Analysis code

Python package behind the weekly write-ups. Every figure reported in a week's
document is produced by that week's runner script, so the numbers can be
regenerated from source rather than trusted.

## Layout

```
karimi/                  reusable analysis code
  config.py              committed thresholds, the analytical grid, paths
  data.py                loading and the exclusion chain -> analysis base
  audit.py               coverage, cell counts, employer concentration
  checks.py              validation of the two exclusion rules that discard postings
  scope.py               role-family integrity: is SALES_BD all business development?
  language.py            detect the language of the text, not of the advert

  atomise.py             splitting compound requirements into single units
  atomise_parse.py       POS and dependency experiments. Both measured, both immaterial
  llm_split.py           the LLM splitting pass: routing, prompt, cache, dry run
  classify.py            six-way requirement typing, multilingual lexicon
  classify_embed.py      prototype classifier, arbitrated against the lexicon
  requirements.py        the requirement table, its summaries and its risk flags

  embed.py               multilingual embedding + the cross-lingual alignment check
  cluster.py             UMAP + HDBSCAN, the cluster dictionary, alias merging
  label.py               naming clusters
  esco.py                cosine shortlist against the ESCO taxonomy
  esco_adjudicate.py     LLM adjudication of that shortlist
  merge_adjudicate.py    LLM adjudication of candidate cluster merges
  intruders.py           finding members that do not belong in their cluster
  variance.py            cell profiles, the Jensen-Shannon index, its bootstrap

  evaluate.py            validation sampling, blind sheets, and scoring

week 1/run_week1.py      the Week 1 runner — reproduces every Week 1 figure
week 2/*.py, week 3/*.py one analysis per file, each printing what it measured
week 4/build_*.py        chart datasets and the published page
docs/                    the published page itself
```

The weekly write-ups those scripts produce are not in this repository; see the
root `README.md` for what is held back and why.

## Running

```bash
pip install -r requirements.txt
python "week 1/run_week1.py"                  # print all Week 1 figures
python "week 1/run_week1.py" --save           # also write tables and validation sheets
python "week 1/run_week1.py" --embed          # run the cross-lingual alignment check
```

`--embed` downloads a multilingual model on first use. Embedding the full corpus
is a separate, slower call:

```python
from karimi import data, requirements, embed
base = data.build_analysis_base()
reqs = requirements.build_requirement_table(base.df)
embed.embed_corpus(sorted(reqs["phrase_norm"].unique()), "week 1/output/embeddings.npz")
```

The runner expects the source export in `wetransfer_karimi-jobs_2026-08-25_1346/`.
That path, and every threshold, lives in `karimi/config.py`.

## Design notes

**Thresholds are declared, not inlined.** `MIN_CELL_SIZE`, the grid, the
exclusion list and the atomiser's shape guards all sit in `config.py`. A
sensitivity run varies them there without touching analysis code.

**The exclusion chain reports itself.** `build_analysis_base` returns the audit
trail alongside the data, so the waterfall from 28,487 delivered postings to the
analysis base is printed rather than asserted.

**The atomiser favours precision over recall.** An unsplit requirement can be
recovered by the LLM stage; a wrongly split one silently corrupts every
downstream measurement. Anything not matching a high-confidence list pattern is
left intact.

**The lexicon is triage, not the classifier.** It resolves about two thirds of
requirement occurrences deterministically and cheaply; the rest is routed to the
LLM stage. Two constraints are easy to violate and are documented in
`classify.py`: patterns anchor on a leading word boundary only, and they run
against normalised text where accents are stripped and apostrophes have become
spaces.

**The alignment check runs before the corpus is embedded, not after.** If a
multilingual model does not place translations near each other, every cluster
built on it is an artefact of language, and no downstream check would reveal it.
`alignment_check` uses a negative control alongside the positive pairs, because a
model that maps everything to nearly the same vector passes a positives-only test
and is useless.

**Validation sheets are blind, and this is enforced by construction.**
`write_blind_sheets` writes the raw text and nothing else — no predicted split,
no predicted type. The pipeline output is joined back only at scoring time.
Whoever wrote the rules must not label the sample: those labels inherit the same
assumptions the rules encode, so agreement would measure consistency rather than
correctness.

## Adding a week

Put shared, reusable logic in `karimi/` as a new module; put the narrative
sequence of calls in `week N/run_weekN.py`. Weeks 2–4 are expected to add
`embed.py` (multilingual embedding and the cross-lingual alignment check),
`cluster.py` (UMAP and HDBSCAN, with centroids fitted once and reused so that
month-over-month comparison is meaningful), `esco.py` (taxonomy anchoring and
the residual), and `evaluate.py` (validation sampling and accuracy metrics).
