# Same title, different job

Hold the role fixed and change the industry around it: how much of what employers
ask for actually moves? The part that stays is the **core** — what travels with
you between industries. The part that moves is the **shell** — what belongs to
the industry you happen to be in. Separating the two is the deliverable.

25,800 European job adverts, two role families (software and data; sales and
business development), eleven industries, four weeks.

**→ The findings, with the charts:
https://gcolle6.github.io/European-job-adverts---Karimi.AI/**

This repository holds the code behind that page.

## What is not here, and why

The data is not here, and neither is anything a model produced from it.

1. **The source export is licensed, not ours to redistribute.** 28,487 adverts
   delivered by a third party.
2. **The intermediate tables name employers and quote adverts verbatim.** Cluster
   member lists, review sheets and the employer-concentration tables all carry
   text straight from the source. Aggregates are publishable; the sentences are
   not ours to publish.
3. **Size.** The ESCO taxonomy source is 1.3 GB and the embedding stores are
   ~290 MB each — past what GitHub accepts.

Everything excluded regenerates from the scripts that are here, given the export.

The weekly write-ups are also held back until they are published in full. Each
has been rewritten several times as later measurements corrected earlier ones,
and a half-published record is worse than none: a reader landing on a figure that
a later section retracts has no way to know which one stands.

## Method, in one paragraph

Requirements are split out of each advert into single units, typed six ways
(technical, domain, soft, credential, language, availability), embedded with a
multilingual model, and clustered. Each cell of the industry × function grid gets
a profile over those clusters, and the distance between profiles is one number
per function: how much the same role changes with its context. Everything is
reported both weighted and unweighted by employer, because nine of twenty-two
cells have a single employer above 10% of the cell.

## Running it

Python 3.11.

```bash
pip install -r requirements.txt
python "week 1/run_week1.py"          # print the Week 1 figures
python "week 1/run_week1.py" --save   # also write tables and validation sheets
```

Two things to expect. The runner needs the source export in place — `config.py`
names the path, along with every threshold, and nothing is hard-coded elsewhere.
And the `week 2/`–`week 4/` scripts are one-off analyses rather than a library:
each was written to answer one question and print what it found, and they carry
absolute paths from the machine they ran on. The `karimi/` package resolves its
own paths and does not.

## What the code is built to make visible

**Thresholds are declared before results, in `config.py`,** and are not adjusted
to make something pass.

**The exclusion chain reports itself.** `build_analysis_base` returns its audit
trail beside the data, so the waterfall from 28,487 delivered adverts to the
analysis base is printed rather than asserted.

**Validation is blind by construction.** `write_blind_sheets` writes raw text and
nothing else — no predicted split, no predicted type — and the pipeline's output
is joined back only at scoring time. Whoever wrote the rules does not label the
sample: those labels would inherit the same assumptions the rules encode, so
agreement would measure consistency rather than correctness.

**Negative results are kept in the code, not deleted.** `atomise_parse.py` holds
two mechanisms that were built, measured, and found to change nothing; the
few-shot prompt that improved development scores and not held-out ones is still
in `llm_split.PROMPTS`. They are there so the negative result stays reproducible
and nobody spends the week again.
