# Splitting `must_have`: the pattern catalogue

Decided 2026-10-30: the splitter is a **deterministic model that must work on
`must_have` text we do not have yet**. So it is built from grammatical patterns,
not from fixes for strings we happened to see, and every change is judged on
postings that were never read while writing it (`datasets.py`).

A pattern is defined by **grammar** — parts of speech, the position of a
preposition, a conjunction, a bracket — never by a list of content words. Closed
word classes are fine as lists, because the language has no others: prepositions,
conjunctions, determiners, the names of languages. Open classes (verbs, adjectives,
nouns) are not: a list of verbs breaks on the first verb it does not contain. Those
are decided by a part-of-speech tagger (spaCy `en_core_web_sm`, local and
deterministic). That became affordable on 2026-10-29, when the text was
translated to English first: in Week 1 it needed six taggers, one per language.

Same input, same output, always. Nothing leaves the machine.

---

## The patterns

Each one: the shape, the solution, an example, and how it is detected today.
⚠️ marks detection that still rests on an open-class word list and is to be
moved to the tagger.

### P1. Head + list

**Shape.** A governing phrase ending in a preposition or an introducer, then a
list of noun phrases: `[head] X, Y and/or Z`.
**Solution.** One requirement per item, each carrying the head.
`3+ years in helpdesk or IT support` → `3+ years in helpdesk` · `3+ years in IT support`.
**Detected by.** Prepositions and introducers (closed lists, `TRIGGER_RE`,
`PREP_RE`, `INTRODUCER_RE_V2`), item-length limits (`_is_list`).
**Limit: `between`.** A list after `between` relates its members instead of listing
them (`trade-offs between scope, quality and timeline`, `switch between vision and
detail`), so the span is masked as one unit, like a bracket (`BETWEEN_RE`, with the
tagger flag). 2026-10-30: fires on 0.1–0.2% of occurrences; every change read was
right. `whole_compound` rises by design, as for P6.

### P2. Shared tail

**Shape.** Coordinated modifiers before one final noun: `X and Y [noun]`.
**Solution.** The noun goes onto each modifier.
`Analytical and problem-solving skills` → `Analytical skills` · `Problem-solving skills`;
`EEA or Swiss citizenship` → `EEA citizenship` · `Swiss citizenship`.
**Exception, P2a.** Modes of one skill stay one: `written and verbal communication`,
`spoken and written English` (guide convention).
**Detected by.** The tagger, `_shared_tail` (2026-10-30). Every test is a shape:
each conjunct but the last is one word; modifiers are parallel (adjective with
adjective, proper noun with proper noun) and never a plural noun; the tail is common
nouns only, so product names are not cut; no verb in front (`ability to write
maintainable and scalable code` rates one object); a common-noun modifier needs a
governing head and a two-word compound (`knowledge of networking and security
protocols`), because a bare common noun is often a requirement by itself (`Rigor and
team spirit`). The older word-list rules (`_distribute_skill_tail`, `ADJECTIVAL_RE`)
still run first and are to be retired.
**Measured 2026-10-30**: fires on 2.4% of item occurrences; ~28 of 30 read changes
right. Pieces cut off from their noun: dev 4.99% → 4.36%, holdout 4.99% → 4.44%.
Known misses: `EEA or Swiss citizenship` (tagged as different classes). Known
errors: a complete noun taking the tail (`math and computer science` → `math science`).

### P3. Alternatives inside the head

**Shape.** The head itself offers alternatives: `A or B [noun] in X, Y`.
**Solution.** Full cross-product (Week 1 convention, decided 2026-09-04).
`Bachelor's or Master's degree in CS or SE` → 4 requirements.
**Detected by.** `_head_alternatives`.

### P4. Coordinated verbs sharing an object

**Shape.** `verb, verb and verb [object]`.
**Solution.** ONE requirement (decided 2026-10-29); normalisation later reduces it
to `Experience with [object]`. If the object is a list, split on the objects.
`Ability to recruit, grow, and retain top talent` → 1;
`Experience designing and deploying services across Linux and Windows` → 2.
**Detected by.** The tagger (`karimi/pos.py`, `config.SPLIT_POS`): a base verb or
gerund by its tag, plus same-form check (`_merge_verb_runs`). The verb lists
(`_VERBS`, `_RUN_VERBS`) remain only as a safety net for the tagger's errors on
fragments — it reads `building` in `experience building X` as a noun.
**Measured 2026-10-30** (`split_quality.py`), orphaned verbs per atom, lists → tagger:
software dev 0.80% → 0.66%, software holdout 0.95% → 0.75%. Every other
measure unchanged within ±0.03pp.

### P5. Category + examples

**Shape.** A category followed by examples, in brackets or after `such as`,
`including`, `e.g.`, `:`.
**Solution.** One requirement per example. The category is a requirement of its
own when it is a real concept (`ERP systems such as SAP` → 3), and is dropped
when it is a generic container (`languages such as Python, Java` → 2). Read off
the Week 1 human labels, 2026-10-30.
**Detected by.** Introducers and brackets (closed), ⚠️ generic container nouns
(`GENERIC_TAIL_RE`, `PAREN_GENERIC_RE_V2`, `_GENERIC_CATEGORY_RE`).

### P6. Qualifiers

**Shape.** A phrase that narrows or rates a requirement rather than adding one:
`ideally …`, `preferably …`, `particularly …`, `if possible …`, `… is a plus`,
`both in …`.
**Solution.** Stays attached to the requirement it qualifies, never split off.
`Expertise in Power BI, particularly in complex data modeling` → 1.
**Detected by.** The tagger, `_qualifier` / `_split_qualified` (2026-10-30): an
adverb after a noun or a comma and before a preposition (`particularly in`,
`preferably with`, `ideally within`), or the fixed `if/where possible`. The
requirement before it is split as usual; the qualifier rejoins the last piece, lists
inside it included (`ideally within life sciences or healthcare operations` adds
nothing). Not a qualifier: an adverb after a verb (`communicate clearly with`), an
adverb before a bare noun phrase, which may add one (`Fluent English, ideally
German` stays 2), additive adverbs (`also`), `e.g.` (P5).
Variant `both/either` + preposition: `skills, both in Dutch and English` is the skill
in each language (2), unless the list is modes (`both in speech and writing`, P2a).
**Measured 2026-10-30**: fires on 0.9% of occurrences, −0.6% atoms; ~24 of 30 read
changes right. `whole_compound` rises 7.66% → 7.96% on the holdout by design: it
counts the lists inside qualifiers. Older partial handling (`_PAREN_LEAD_RE_V2`,
`_EVALUATIVE_RE`) still runs.

### P7. Independent requirements

**Shape.** Two complete requirements, each with its own head, joined by `and`,
`;`, or `, with`: `Strong communication skills and openness to feedback`.
**Solution.** Split at the join.
**Detected by.** `_split_clauses`, `_split_ability`, a list of words that open a
requirement (`_OPENER_RE`, via `_opens_requirement`). ⚠️ Stays a list, on evidence:
2026-10-30 a shape test (any noun phrase of 3+ words opens a requirement) split
inside noun phrases on most of the 157 items it changed (`communication and
interpersonal skills`). One conjunction does not show where a requirement starts.

## Word lists moved to the tagger, and the ones that stayed

Compared one at a time with `compare_predicate.py`, all else equal, judged on the
holdout. 2026-10-30:

| Test | Old rule | Result | Kept |
|---|---|---|---|
| is it a verb? (P4) | `_VERBS`, `_RUN_VERBS` | orphaned verbs 0.95% → 0.75% | tagger, list as safety net |
| is it an adjective? (`_adjectival`) | English suffixes (`-al`, `-ive`, `-ly`…) | cut-off pieces 4.46% → 4.23%, compounds left whole 8.17% → 7.42%; ~19 of 30 read better, ~8 worse | tagger (adjective, adverb or participle) |
| is an `-ing` word a noun? (`_nominal_ing`) | `_ADJECTIVAL_ING` list | tagger worse on 12 of 13 disagreements (reads `solving`, `networking` as verbs) | old list |
| does the right side open a requirement? (P7) | `_OPENER_RE` | splits inside noun phrases | old list |
| is `R` in `ability to L and R` a verb? (`_ability_verb`) | `_VERBS` | 3 items change, all right (`... and derive clear specifications` = 2) | list + tagger base verbs |

**Old rules kept on purpose (2026-10-31).** `_distribute_skill_tail` is not a duplicate
of P2's `_shared_tail`: it handles mixed noun/adjective modifiers before
`skills/abilities/capabilities` (`Strong communication and interpersonal skills` = 2),
which the grammar-only rule rejects by design; switched off, ~190 dev items break.
Everything behind `SPLIT_REPAIRS` stays in the code anyway, because switched off it
must reproduce the published Week 1-4 output.

**Pinned behaviour.** `test_patterns.py` holds every example and control used to build
these rules (46 cases) with the count the conventions give. Run it after any change.

### P8. Fillers and alternative paths

**Shape.** `or similar`, `or a related field`, `or the like` — no content; versus
`or equivalent experience` — a real alternative route into the job.
**Solution.** Fillers are dropped; an alternative path is a requirement of its own.
**Detected by.** `STOP_RE`, `_FILLER_LEAD_RE`, `_ALT_PATH_RE`.

### P9. Language lists

**Shape.** `Fluent German and English (written and spoken)`.
**Solution.** One requirement per language; the modes stay attached.
**Detected by.** Language names (closed list, `_split_languages`).

### P10–P15. Found on sales, stated as grammar (2026-11-02)

The frozen model (9c8b5f0) was run on 1,000 random SALES_BD postings
(`run_sales.py`). The errors fell into a few shapes, none of them specific to sales:
software has them too, only less often. Each is a grammatical rule, behind
`atomise.SALES_PATTERNS` so it can be measured on its own.

| | Shape | Was | Now |
|---|---|---|---|
| P10 | the item opens with its own preposition | `work in in the evening` | `work in the evening` |
| P11 | after `to` + verb, a bare noun is another object of that verb | `Proven ability to supplier networks` | `Proven ability to manage supplier networks` |
| P11b | a gerund, not a preposition, governs the list | `Comfortable discussing APIs`, `webhooks` | `Comfortable discussing webhooks` |
| P12 | an item ending in a frame noun has its own head | `Analytical skills with CRM system experience` | `CRM system experience` |
| P13 | adjectives on the object of a verb describe one object | `create a welcoming` · `inclusive customer experience` | one requirement |
| P14 | `noun or hyphenated-modifier + noun` | `Business` · `customer-related experience` | `Business experience` · `customer-related experience` |
| P15 | `head gerund X and gerund Y` | `Experience designing REST APIs` · `building data pipelines` | both with `Experience` |

**Limits, measured.** P13 applies only when the adjectives are the one coordination
(`manage ambiguity and operate in fast-evolving, early-stage environments` stays two).
P15 does not apply inside a comma list. `to` as a preposition (`Commitment to X and Y`)
is untouched by P11. Fixed adverbials (`in particular`) are not P10.

**Not done.** The first reading also blamed `Bachelor or Master` as two requirements: that
is the convention (alternative degrees count one each), so the error was in the reading,
not in the model. Translation artefacts (`carpenter, carpenter, carpenter`) and untranslated
languages (2.4% of sales items) are not splitting problems.

**How it was judged.** The first sample was read to find the shapes, so it is a
development set. A second sample of 1,000 postings, drawn from the rest and never read,
is the test (`run_sales.py --sample2`), beside `software_holdout` and the blind half of
the hand count.

**Result.** The rules change 2.3% of item occurrences on sales sample 2 and 1.9% on
software dev. Nothing gets worse: the blind hand count stays 78.0%, the general
label-free measures barely move (stranded modifiers 4.26% → 4.22% on software_holdout),
and with the flags off the output is identical to HEAD on 93,217 segments. The gain is
in wording, which those general measures do not see, so two targeted defects were
counted on the untouched sets:

| | sales sample 2 | software_holdout |
|---|---|---|
| atoms with a doubled preposition (`in in`) | 23 → 11 | 113 → 101 |
| `ability to <noun>` (verb lost) | 41 → 9 | 204 → 41 |

### Abstention

Whatever still looks broken after splitting (`damage_reason`) is kept whole in its
original wording: an unsplit requirement can be recovered later, a wrongly split one
cannot.

---

## The human count, and the conventions it settled (2026-10-30)

120 random item occurrences from `software_holdout`, counted by the user
(`validation/count_holdout_LABELLED.csv`, read-only; 5 left blank, 3 of them in
Lithuanian, Polish and Czech, which the pipeline does not translate). There will be
no more, so `score_counts.py` splits them once: a `read` half whose errors may be
read, and a `blind` half that never is.

| | exact count | total vs human |
|---|---|---|
| no split | 62.6% | 0.64 |
| Week 1 code, original text | 64.3% | 1.19 |
| before the count (translated + repairs + tagger) | 71.3% | 1.18 |
| after the first fixes, blind half | 76.3% (was 72.9%) | 1.14 (was 1.19) |
| **after the singular/plural rule, blind half** | **78.0%** | **1.15** |

The splitter **over-counts**: 17% of items get more requirements than the human
sees, 6% fewer. Most of the gap on the read half was convention, so the user fixed:

- **degree × fields stays a full cross-product** (`Master's or PhD in A, B, C` = 6);
- **optional parts are not counted** when they add to a required part (`Fluent in
  English; Dutch is a strong plus` = 1); an item optional as a whole still counts
  (`Experience with Zendesk Apps Framework is a plus` = 1). Atoms stay, flagged
  `nice_to_have`; `atom.counted` decides; `requirements_counted` sums it;
- **coordinated adjectives before a SINGULAR noun are one requirement** (`Structured
  and project-based work`, `a calm, methodical and pragmatic approach`); before a
  plural noun they stay several (`analytical and problem-solving skills` = 2).
  Nouns and names as modifiers are unaffected (`Linux and Unix experience` = 2).
  `_shared_tail` returns `ONE_REQUIREMENT`; 0.7% of occurrences;
- **equivalent alternatives where one suffices count once**: scope after `within`
  (`within operations or planning`, `WITHIN_RE`, only after the requirement's own
  object); school-leaving qualifications too, NOT implemented — one example, and it
  cannot be told from degrees without a word list. Tools in alternative still count
  one each.

Real splitter errors found and fixed by pattern: thousands separators
(`100,000 endpoints`, `NUM_COMMA_RE`) and closing fillers (`... and related reference
architectures`, `... or a national equivalent`, `_is_tail_filler`).

## Normalised wording (2026-11-01)

Splitting fixes the COUNT; `karimi/normalise_req.py` fixes the WORDING, as a column
`atom_norm` beside the atom, never instead of it.

- **N1 translation calques**, translated atoms only: a closed list of one MT model's
  systematic errors, found by contrast with atoms that were English from the start
  (`Flowing` → `Fluent`, `in word and writing` → `written and spoken`, `Well-founded`
  → `Solid`, `Negotiable German` → `Business-fluent German`, `Exhibitable` →
  `Demonstrable`, `Safe handling of` → `Confident use of`, ...).
- **N2 activity verbs on an object**: `Experience building and maintaining CI/CD
  pipelines` → `Experience with CI/CD pipelines` (decided 2026-10-29). Verbs by the
  tagger, opening the run or after a conjunction only (`implementing monitoring
  solutions` keeps `monitoring`). Left as written: verbs that are the requirement
  (`leading`, `managing`, `mentoring`, ...), verbs with a complement (`turning X into
  Y`, `contributing to`), a second activity in the object. The light verb `working`
  before a preposition goes: `working in agile teams` → `Experience in agile teams`.

Read on dev: ~31 of 35 changes right; the misses come from atoms already cut badly
upstream. Pinned in `test_patterns.py`.

**N3 decomposition** (decided 2026-11-01: all three, losing nothing), `decompose`:
years (min, max, as written), level (basic / good / strong / advanced / expert, from
degree words and from the head itself: `familiarity` = basic, `expertise` = expert),
head and head group (competence / experience / ability / language), core, qualifier
(P6), extra (what follows a `X skills` head), and `key = group: core`. Languages are a
closed set, so every way of asking for one becomes `language: English`, the modes
(`written and spoken`) in their own column.

**N4 grouping by embedding** (`group_requirements.py`), on the core only, so years and
level can never be merged away. Threshold 0.90, chosen by reading pairs per cosine
band from dev: ≥0.95 nearly always the same demand, 0.90–0.95 ~22 of 25 with the guard
below, 0.85–0.90 ~6 of 10. Guards: same head group only; one hop to the most frequent
neighbour, no chains; proper names, acronyms, numbers and credential words must match
(`degree in Computer Science` ≠ `Computer Engineering`, `STP` ≠ `STL`, `Master's` ≠
`Bachelor`), because the embedding puts them at 0.95. A bare core joins the competence
group with the same core (`Communication` = `communication skills`).

| step | distinct |
|---|---|
| atoms as split | 151,535 |
| normalised wording | 150,314 |
| decomposition keys | 113,728 |
| **embedding groups** | **87,740** (half of all atoms in 4,110 groups) |

Known limits: status is merged into the credential (`Currently pursuing a Master's` with
`Master's degree`; the atom keeps it); a few topic merges (`quantum technologies` →
`quantum computing`); fragments cut badly upstream stay as their own groups.

## How a change is judged

1. **Develop** on `software_dev`. Samples may be read.
2. **Accept** only if the label-free quality measures (`split_quality.py`) do not get
   worse on `software_holdout`, which is not read.
3. **Count check by a person.** A sheet of `software_holdout` items where someone who did
   not write the rules writes how many requirements each holds. This is the only
   measure that does not share the tagger with the splitter.
4. With the flag off, the output stays identical to HEAD, so every published Week
   1-4 figure still reproduces.
