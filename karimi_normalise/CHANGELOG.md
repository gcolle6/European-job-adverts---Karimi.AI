# Changelog — rules and dictionary

One line per change that can change an output. `RULES_VERSION` lives in
`versions.py`; a dictionary's version is in its `manifest.json`. A change to
the rules without a line here and a new fingerprint fails the build.

Format: version · date · what changed · how it was measured.

## Rules

- **0.1.0** · 2026-11-04 · first library version. Rules as in `karimi/`
  on this date, including P10–P15 (`New project/PATTERNS.md`). Measured:
  138/138 pattern cases; parity with the batch 97.8% of items identical on
  100 dev postings — every difference read was the batch predating P10–P15.
  Still unreleased, added the same day: `process()` (one call, with the
  run report) and `TranslationCache` (batch's cache format). Rules unchanged.
  Then: the translator is the caller's choice (`must_have_english`, a
  `translator` function, opus-mt by default; `translated_by` on every
  requirement); a title is also found as a spelling variant of a known role
  (`normalise_title.variants`, the batch's own variants); `non_cercato` when
  the embedding is not installed; base install plus `[translate]`, `[embed]`. Then (2026-11-05): `match_via` on every
  requirement, the known core it was placed by, so a check can show both
  sides of a similarity decision. Rules unchanged.

## Dictionary

- **0.0.dev1** · 2026-11-04 · development freeze of the current batch, NOT for
  release: `must_have_atoms.parquet` was split before P10–P15. Release starts
  at 0.1.0 after regenerating the batch with the current rules.
- **0.0.dev2** · 2026-11-04 · same batch as dev1, now with `reference.json`:
  the bands run reports are read against. Measured on 10% of dev postings
  the dictionary did not see: 59.6% of requirements found as written, 10.8%
  placed in a group by similarity, 11.5% topic only, 18.1% `nuovo`; 38% of
  titles `nuovo`. Lookup agrees with the batch group 76.8% when it places by
  similarity, and with the batch topic 46.3% when it gives a topic only.
- **0.1.0** · 2026-11-04 · first release candidate. Batch regenerated with
  the current rules (P10–P15 included); 98.4% of occurrences keep their group
  against dev2 (`freeze --diff`). Measured: parity with the batch 100% of 767
  items; blind count 78.0% exact (CI 67.8–88.1%); wrong merges 1/14
  requirements, 0/9 roles; all release gates pass (`pytest -m gates`). On
  postings the dictionary did not see: 59.7% known, 10.7% group by
  similarity, 11.5% topic only, 18.1% `nuovo`; titles `nuovo` 36.9% (38.0%
  before variant lookup).
