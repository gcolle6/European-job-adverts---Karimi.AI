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
- **0.2.0** · 2026-11-07 · the item is cleaned before it is read
  (`requirements.clean_item`): a bullet or list number, doubled spaces and
  one closing `.`/`;`/`,` are removed, and an item with NO capital at all
  gets its language's capitals back (`Dictionary.casing`: English from the
  dictionary's cores, other languages from the employers' items in
  `casing.json`, `New project/build_casing.py`). A known core is also found
  in other capitals (`Dictionary._folded`). Why: `New project/invariance.py`
  on 1,070 dev items — the whole item in lower case changed the output of
  41.9% of items (English 37.7%), a bullet and a full stop 6.7% (other
  languages 17.7%). Measured after: lower case 6.2% (English 2.7%, other
  languages 12.6%: still above the 5% fixed beforehand, through the
  translator); bullet, full stop, spaces, order 0.0%; titles 0.0%. Parity
  with the batch 99.4% of 1,533 items (was 100%): the 9 differences are
  Swedish items losing their full stop before translation and all-lower-case
  French items getting a first capital, as intended.
- **0.3.0** · 2026-11-10 · from the first real trial (Chiara, 2026-11-09, 10
  adverts read row by row) and the duplicates the site's explorer showed.
  *Grouping* (the user's calls of 2026-11-10): a requirement is grouped on its
  object alone — `Experience with Python`, `Knowledge of Python`, `Python
  skills` are one group, `python`; how it was asked stays in `head_group`.
  Languages and degrees keep a space of their own (`space`): a new head group
  `education`, `MSc / PhD / Degree in Physics` -> `education: Physics` with the
  level in a new column `degree`. *Splitting*: two frames over one object are
  one (`Solid knowledge and use of SQL`); the category before a list of names
  is not a requirement of its own (`frameworks like Spark, ...`, also in
  brackets); a bracket describing an ecosystem is dropped; languages after
  `in combination with` and full language clauses split; `both Windows and
  Linux` splits; bare traits split (`Reliable, proactive, and self-motivated`);
  roles in alternative after `experience as` and purposes after `<name> for`
  stay one; `their` pointing back keeps an item whole; `to` + verb is not the
  head (`Willingness to acquire knowledge in Angular`); `ideally Excel, Qlik`
  is kept and marked optional, so not counted beside what it qualifies.
  *Normalisation*: `Multi-year`, `related`, `overall`, `ideally` are not the
  object; a name after the preposition is (`programming knowledge in Python`
  -> Python); `proficient`, `familiar`, `use of`, `abilities` are frames; one
  key per language whatever surrounds it (`English (B2)`, `level of English`,
  `communication in English`, `German is a plus`), CEFR level to `level_words`;
  a closed list of product spellings (`ALIASES`: Golang, PowerBI, MS Office,
  Microsoft Azure, ...); a bracketed example goes to `extra`; debris (`of`,
  `You have`, `Senior-level`) is empty. Groups whose cores differ only by case,
  hyphen, plural or British spelling are joined in the batch
  (`normalise_req.canon`) and found by lookup. New output `req_name`, the
  readable name. Measured: pattern cases 138/138 (9 key cases rewritten to the
  new keys); `ideally` + names is optional and not counted, `ideally` + a
  language counts (`Fluent English, ideally German` = 2, the user's call of
  2026-11-11); blind count exact 78.0%, unchanged; parity with the
  batch 99.4% of 1,533 items; the explorer's duplicate entries 49 -> 7 (835 ->
  804 requirements; `English` 3,562 -> 5,777 adverts); Chiara's run re-done:
  19 of 83 items split differently, known requirements 110 -> 123. ⚠️ Wrong merges are now barely measured: the
  labelled pairs were drawn inside one head group, and only 1 requirement
  merge pair still occurs in the output (was 14). Needs a new labelled draw.
  Then (2026-11-11, same version, unreleased): the **curator agent**
  (`curator.py`). At the end of every run it proposes, for each requirement the
  run could not place, a known requirement it is a spelling of (a vendor in
  front, a version or a lower-case generic word after, an acronym in
  brackets); the check's judge decides; resolved joins are read by the API
  within five minutes, marked `match_by = curator`, and the dictionary version
  reads `0.2.0+a<n>`. It only joins a spelling to an existing group, never
  makes or merges groups; a person can overrule (`python -m
  karimi_normalise.curator --reject`). Measured on the dictionary's own
  cores: the first detectors proposed 1,257 joins with obvious errors
  (`Information Technology` -> `Information`, `ISO 27001` -> `ISO`); tightened
  to 385. Two samples of 40 put to the real judge: it agreed with 38 and 39,
  and reading them 3 and then 1 were wrong (`Oracle RDBMS` -> `RDBMS`, since
  excluded). The judge passes nearly everything here, so precision rests on
  the detectors.
- **0.3.1** · 2026-11-11 · degrees in alternative with ONE field share it:
  `MSc or PhD in Physics` -> `MSc in Physics`, `PhD in Physics` (was `MSc`
  and `PhD in Physics`, since 0.2.0; with a list of fields the cross product
  was already right). Found in the first test call of the deployed 0.3.0.
  Same dictionary (0.2.0): the cores it now makes were already known.
- **0.4.0** · 2026-11-11 · each degree is its own requirement, the user's
  call reversing 0.3.0: `Master in Business` and `Bachelor in Business` are
  two groups, `education: Master in Business`, and every spelling of one
  degree is that degree (`MSc`, `M.Sc.`, `Master's` -> Master; `Doctorate` ->
  PhD; a degree with no level stays `Degree in ...`). The level is still in
  `degree`. Needs dictionary 0.3.0. Measured: pattern cases 138/138, blind
  count 78.0%, parity with the batch 99.4%.
  Then (2026-11-13): a run under the smallest reference size (10 postings)
  gets grey signals, which no longer colour it — the one-posting test of
  11/11 was red for one one-word requirement in nine. The site reads older
  history lines the same way (`dashboard._too_small`). Outputs unchanged.
- **0.4.1** · 2026-11-13 · degrees read right. Found reading the API test
  of that day by hand, then counted on the batch with the new inspector
  agent (`errors.degree_flag`): 1,782 atoms flagged under 0.4.0, 362 under
  0.4.1 on the same items. Fixed: `A Bachelor's or Master's degree in X, Y`
  (the article cost the Bachelor its noun: `A Bachelor's X`, not a degree);
  three or more degrees (`Bachelor's, Master's or PhD in X, Y`); the Dutch
  `Bachelor of Master` and `of gelijkwaardig`; `Bachelor of Science in X` is
  `Bachelor in X`; a degree inside the field (`Degree of Master of
  Science`); `or equivalent qualification` after a degree is not a second
  requirement (equivalent alternatives = 1, the user's 2026-10-30
  convention; an equivalent EXPERIENCE still is one); a degree `with` or `+`
  an experience is two; the French `Bac+N` is a degree (3 = Bachelor, 4–5 =
  Master, 8 = PhD, a range at its lowest step; also the translator's
  `Bachelor's degree+5`); `Master's degree X` with no `in`; `Master's
  student`; a bracket naming only kinds of school is dropped; `Maîtrise de
  X`, which the translator wrote `Master's degree in X`, is command of X
  (`atomise.repair_translation`, called by both batch and library). Needs
  dictionary 0.3.1.
  Then (2026-11-15, rules unchanged): the **publisher** (`explore.py`). The
  site's explorer was built once from the August export and committed by
  hand; now every run whose check passes adds its adverts, and the check job
  rebuilds it, served open at `/v1/explore`. A run passes when its judge is
  trusted and within its reference and no splitting signal is out of range;
  coverage signals do not block (new adverts are what should come in).
  Inside a run, optional requirements, broken splits, requirements with no
  topic, degrees the inspector flags and generic words are left out, and the
  export's adverts are counted by the same rule. An advert sent twice counts
  once (a hash of its id). Stored: hashes and counts, no text. Measured on the
  export alone against the published explorer: 15,655 adverts (was 15,656),
  809 requirements shown (was 813): out are `Bachelor's degree` and
  `Master's degree` with no field, read as no degree, and `Additional
  languages are a plus`; `German` 1,335 -> 1,145 adverts, `French` 763 ->
  600, since `German is a plus` is optional (the 2026-10-30 convention).
  Leaving out every item kept whole was tried and dropped: it took
  `Written and verbal communication skills` (359 adverts) and 62 more off.
- **0.4.2** · 2026-11-15 · from the first batch of new postings (1,000
  adverts sent through the API as an outside caller, 2026-11-15). Cases taken
  from batch 1 only; batch 2, unseen, measures. *Degrees*: names the rules did
  not know (`BS`, `MS`, `BA/BS`, `B.E.`, `B.Tech`, `M.Tech`, `MCA`, `BBA`,
  `associate's degree`, the Dutch `HBO` and `WO`; `BS`, `MS`, `WO` in
  capitals only, so `MS Office` stays a product); words in front of degrees in
  alternative (`Relevant bachelor's or master's degree in X` was `Relevant
  bachelor's X`); `or relevant/related experience` and `or experience` after a
  degree are a second route, as `or equivalent experience` was (it was glued
  into the field: `Bachelor in or relevant experience`); `or other relevant
  advanced degree` counts once; `, Master's preferred` closing a degree item
  is its own atom; a degree with its fields in a bracket (`Bachelor's degree
  preferred (Engineering, CS)`) is crossed with them; a degree `and` or right
  before years of experience is two (`Master's degree 2–3 years of ...`);
  `Bachelor's degree required in X`, `, or equivalent in X`, `, preferably in
  X`, `with specialisation in X`; `HBO work and thinking level`, the
  translator's `HBO werk- en denkniveau`, is one degree; `Bac+4/5` student;
  two spellings of one degree are one (`Bachelor's / Undergraduate`).
  *How much it is wanted* is not the requirement: `is a plus`, `preferred`,
  `desirable`, `would be an advantage` closing an atom are taken off before it
  is read (`normalise_req.strip_optional`); 100 cores in batch 1 still carried
  them (`Python is a plus`, `German is strongly preferred` not read as German).
  An atom closing on a bare `preferred` or `a plus` is optional
  (`atomise.nice_to_have`), except inside a bracket that names something
  (`cloud infrastructure (AWS preferred)` stays required).
  *Two dead patterns*: the 0.4.1 patches went through a shell heredoc, which
  turned `\b` into a backspace in two places, so `Master's student` was never
  a student and the guard on `Master's degree X` never stopped anything
  (`Master in and relevant experience`). `tests/test_rules_042.py` now fails on
  any control character in a rule source.
  *Languages the batch never met*: Chinese goes to opus-mt-zh-en, Japanese and
  Polish, Czech, Lithuanian, Romanian, Hungarian, Slovene, Croatian and the
  rest to opus-mt-mul-en, chosen by their letters (`translate.script_code`)
  and, for an item with none, by its posting's. Batch 1 left 134 Chinese and
  Japanese and ~60 such items untranslated, nearly all `nuovo`. Read on those
  193 items: zh-en clearly better than mul-en on Chinese; ja-en invents
  sentences, so Japanese goes to mul-en; mul-en right on about three in four of
  the others, with errors a reader catches (`niezawodność`, reliability, as
  `inefficiency`). Not measured against labels.
  Measured on batch 1, split and decomposition only: inspector flags 69 -> 8
  (the detector itself extended to the new names, `errors._DEGREE_OPENS_RE`),
  optional words left in a core 100 -> 6, 2.0% of items change; every change
  read. Pattern cases 138/138.
  *The curator* (not a rule source, same day): it joined `IT platforms` ->
  `IT`, `SAP EAM` -> `EAM` and `AWS MLOps engineering` -> `MLOps
  engineering`, by taking a vendor or a generic word off in front of a
  category. Now a closed list of categories (`EAM`, `MLOps`, `CRM`, ...) is
  never shortened and a vendor must be a whole name; of the 10 joins made so
  far only those 3 are no longer proposed. They are annulled with `curator
  --reject`.
  *The batch's own language choice* (found by parity, same day):
  `translate_must_have.py` kept a copy of which language and which model, so
  when the library learnt the letters above the batch did not — 866 of 93,068
  items (0.9%) the API translates were kept as written, 105 Polish ones went
  through the Romance model, and parity fell 99.4% -> 98.9%. The batch now
  calls `translate.item_code` and `translate.model_for`; a test compares the
  decision, not only the tables (`test_batch_decides_the_language_as_the_library_does`).
  Then (2026-11-16, rules unchanged): the **archivist** (`archivist.py`) and a
  wider **inspector**. Batch 1's optional tails and untranslated items were
  found by hand: no agent looked for them. The inspector now also flags
  `optional_tail`, `optional_head` (`Desirable experience in design` read as
  `Desirable`, still open), `untranslated` and `translation_failed`, read off
  the output so it does not share the translator's blind spots. The archivist
  keeps every kind found so far in `error_catalogue.json` (cause, fix, guard,
  the residual a fix left) and reads each run's counts against it: fixed in a
  later version, residual, back above 3x the residual (yellow), or open, for
  which it drafts the failing test; a person approves. Batch 1: under 0.4.1
  232 untranslated, 111 tails, 69 degrees, 13 failed translations; under 0.4.2
  12, 0, 8 and 2, recorded as the residuals.
  Then the **explorer** (`explorer.py`), the user's call after measuring two
  models (`New project/score_explorer.py`, prompt x1): on batch 1 Gemini 3.5
  Flash and Qwen3-14B both found 40 of 40 known errors (named with the
  catalogue's id 97.5% and 90%); against the hand counts both were right on
  33% of their split flags, under the 60% bar, so the blind half was not run
  and the explorer never counts. Gemini's flags on items no detector flagged
  read about two in three real. With `KARIMI_EXPLORER=vertex` the check sends
  30 items the inspector found nothing in to Gemini on Vertex AI's EU
  multi-region (the only place this project reaches a Gemini model), groups
  the problems into kinds, and reports known ones by catalogue id and new ones
  as candidates; a kind's title is withheld from the site when it repeats
  three words of an item. Never a light. From its first readings, five kinds
  entered the catalogue as open with a detector (`optional_marker_unknown`,
  `required_left`, `or_similar_left`, `level_left`,
  `degree_higher_education`) and two without (`broken_fragment`,
  `list_not_split`). Prompt x2 adds one line (judge the key, not the
  employer's words), after x1 flagged `is a plus` kept in an atom whose key
  was clean.
  Then the explorer's new kinds are **decided on the Metrics page** by the
  project lead (the user's call): a Google sign-in, which the API checks
  (`/v1/admin`: Google's signature, our OAuth client, a verified email in
  `KARIMI_ADMIN_EMAILS`); only there are the cases, the adverts' text, shown.
  A decision goes to `archivist/decisions.jsonl` (append-only): a confirmed
  kind joins the catalogue as open with no detector until one is written and
  measured (`archivist.catalogue_with`); a turned-down kind is offered back to
  the model as known, so it is named, not proposed again. Who decided never
  reaches the public page.
  Then **the colour follows errors** (the user's call, after batch 2 came out
  red on dictionary coverage alone while its judge was green). A run's colour
  is the check's `error_estimate`: the inspector's flags plus, for the
  decisions taken by similarity, the judge's share rejected times the share
  placed that way, over the requirements; green under 3%, yellow to 6%, red
  above, fixed before any run was read with them. The novelty signals
  (coverage, translation) carry no colour (`info`, with `unusual` and its
  side) and go to `novelty`; the split's shape signals are yellow at most;
  the judge's test against its reference stays in the detail. Older history
  lines are read again by the same rule (`dashboard._colour_rule`). The
  publisher lets a run in unless its estimate is red (a shape no longer
  blocks: batch 2 was kept out at 2.0264 requirements per item against
  2.0253). Batch 2 under the new rule: about 4.4% estimated wrong, yellow.
  Then **a person's review** (`review.py`, 2026-11-17): the error estimate
  leaves out splitting errors and unnamed kinds, so no run could say "X
  errors". The project lead, signed in, reads 100 items drawn at random from a
  run (seeded by the job, kept), without the agents' verdicts, and marks each
  correct or incorrect with a note; from 50 on it can be sent, and sent again
  with more. The site shows the share wrong with its Wilson interval, whether
  the items were taken in order, and the inspector against it (precision,
  recall) beside the check's estimate. Items and notes stay in the store.
  And **the curator never takes a vendor off** (the user's call, 2026-11-16):
  `vendor_prefix` is gone after `Google Studio` -> `Studio` and `AWS
  GuardDuty` -> `GuardDuty`, both passed by the judge; `curator --reject-detector
  vendor_prefix` overrules every join it made. A join also needs the known core
  to be the form itself or its plural, and an acronym has none: `SAP IDM` had
  reached `IDMS` through the lookup's plural fold (the fold itself, in
  `canon`, is an open rule for 0.4.3).
- **0.4.3** · 2026-11-17 · every error the agents found in batch 2 of the new
  postings, under the user's process of that day: each batch's errors are all
  fixed, and taught to the agents, before the next batch measures. Batch 2 is
  now development; batch 3 measures. *How much it is wanted*: the translator's
  `appreciated`, `valued`, `welcome`, `desired`, `of advantage` and a bare
  `Advantage` (`SAP Advantage`, from `von Vorteil`), `an express/added plus`,
  `, but not required`, a marker before a bracket of examples, and a marker
  opening the atom (`Desirable experience in design` was `Desirable`; also
  `Desired`, `Bonus points for`), which also makes it optional. *How it is
  asked*: a closing `required`, `mandatory`, `a must` is taken off and the
  requirement still counts; not after `if`, `when`, `as`, `where`. *Words that
  add nothing*: `or similar (role)`, `or equivalent (tools)` closing a
  requirement; on a list the `or` becomes the comma it replaced (`Ansible,
  Terraform or similar` = 2). A level after a name goes to the level column
  (`Python Advanced`, not `Visual Basic`). *Degrees*: `L3`, `Master 2`,
  `BSE`, `Baccalaureate`, `triennial degree`, `MBO`; `Bac + 3`; `course`;
  `strongly preferred`, `minimum`, `towards` before the field; a bracket after
  a bare degree; `HBO X` with no preposition; `or equivalent`, `or engineering
  school`, `or higher`, `from an accredited institution` after a degree add
  nothing; two degrees of different levels joined by `/` are alternatives;
  `X required, Y preferred, in F` (both in F), `X required; Y preferred in F`
  (only Y); `PhD or equivalent research experience in F`; `degree with ...
  knowledge`; `preferably with X background`; `with X direction`; `or 8+ years
  of directly related experience`, `or a suitable combination of education,
  experience and training` are the second route. *The explorer's kinds*
  (confirmed by the process): activities before one object stay one
  (`design, deployment and support of network solutions`); `knowledge about`,
  `Qualifications/experience/knowledge of`, `X-Knowledge`, years written out
  (`five years`, `Seven (7) years`) and `progressively responsible`; a
  language written as `I hear English is very fluent`. *Translation*: Danish,
  Finnish and Czech are recognised by their words and go to opus-mt-da-en,
  -fi-en, -cs-en (Danish had gone through the Swedish model); a few French
  words the lists missed (`Confirmé`, `Rigueur`); `Maîtrise Pack office` is
  command of Microsoft Office and `maîtrise d'œuvre` is construction project
  management, not degrees. *Acronyms*: `canon` keeps the S of `IDMS`, `HRIS`.
  Measured on split and decomposition alone: batch 2's degree flags 56 -> 10,
  optional tails 2 -> 0, 2.3% of items changed; batch 1 69 -> 7, 3.7%; every
  change read, two that went worse fixed before release. Left, written in the
  catalogue as open: broken fragments and long lists (no reliable detector,
  watched by the explorer).
- **0.4.4** · 2026-11-17 · every error the agents found in batch 3, and the
  user's first human review (batch 2, 100 items: 25 wrong, CI 17.6–34.3%; the
  inspector had caught none of the 25). Batch 3 is now development; batch 4
  measures. *Conventions the user settled after the review*: a named
  technology wins and the words around it go to `extra` (`Cloud engineering
  experience on Azure` -> Azure, `SAP as a technical consultant` -> SAP),
  except a common noun that completes the name into a term (`IR drop
  analysis`, `AI use`), a category name after its modifier (`conversational
  AI`), a licence class, `Interest in`; NAMED examples are the requirements and
  the category goes (`ERP systems such as SAP or Oracle` = 2, `databases
  (SQL/NoSQL)`, `(AWS or Azure)`, `(Ruby on Rails / React)`); common-noun
  examples and what `including` adds stay with the category (`digital
  components such as Ethernet switch, memories` = 1). *Splitting*: a list cut
  before its comma (`, and cybersecurity frameworks`); `X with the ability to
  Y` = 2; trait lists with `eager to learn`; `3 years or more`, `C1 level or
  above`; `is given priority, and ... is better` = 2; one ask once per item
  (`Systems thinking` x3; contexts of one key that name nothing, `communication
  skills with clients, teams`). *Normalisation*: `technical`, `work`,
  `coding` before a frame noun say what kind (`Deep technical mastery of X` ->
  X); `Be/I'm familiar with`; `the field of`, `at least one of`, `from`, `with`
  opening the core; `Ample`, `Vast`, `Highly`, `Multi-annual`; `foundations
  in`; `build and manage a sales pipeline` -> sales pipeline; `Soft skills`.
  *Degrees* (batch 3): HBO/higher professional education, `WO programme`,
  `Bac+5 ... or university master's`, `or the like`, qualifiers before the
  field. *Translation*: Spanish, Dutch, Croatian markers; Chinese `优先`/`更好`
  read as optional. *The inspector learns the review's error shapes*:
  `lead_punctuation`, `comma_in_key` (names only: verb and adjective runs are
  one ask by convention, and flagging them made 3 flags in 4 wrong),
  `edge_preposition`, `duplicate_key` (two parts of one item with one key: a
  name lost). *The explorer*: JSON mode and a retry — on batch 3 its kinds came
  back empty. Measured on split and decomposition alone: inspector flags on
  batch 3 ~630 -> ~130 (with the new detectors applied to both), batch 2 ~700
  -> ~140; on the 100 reviewed items, 20 of 25 wrong ones change and 19 of 75
  right ones change, every one read — all follow the user's notes. Old
  convention tests changed with a comment where the user's call reversed them.

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
- **0.2.0** · 2026-11-10 · batch regenerated with rules 0.3.0: grouped by
  space and object (`experience` and `competence` together, `education` and
  `language` apart), cores one spelling apart joined. 97,628 cores, 74,033
  groups (was 87,703), 49,120 topics (was 62,822). On postings the dictionary
  did not see: 65.6% known (was 59.7%), 8.8% group by similarity, 11.3% topic
  only, 13.2% `nuovo` (was 18.1%); titles unchanged. Lookup agrees with the
  batch group 72.5% when it places by similarity (was 77.2%): the groups are
  larger, so the nearest core and the batch's most frequent one differ more
  often. Built and read with rules 0.3.0 only: older rules look it up with
  keys it no longer holds. Judge's reference (`check --reference 0.2.0`): it calls
  13 of 150 group decisions wrong, 8.7% (was 7, 4.7%; p ~ 0.25, not
  significant), topics 10% (was 11%). Read: ~5 real errors (`Expresso` ~
  `Express`, `Innate` ~ `Endevor`), the rest narrower/broader. Likely cost of
  the one space: experience, competence and ability are now searched
  together, so more cores sit above 0.90 by chance.
- **0.3.0** · 2026-11-11 · batch regenerated with rules 0.4.0 (one group per
  degree). 98,396 cores, 74,470 groups, 49,543 topics. On postings the
  dictionary did not see: 65.5% known, 8.9% group by similarity, 11.2% topic
  only, 13.2% `nuovo`. Judge's reference: 11 of 150 group decisions called
  wrong (7.3%), topics 9%.
- **0.3.1** · 2026-11-13 · batch regenerated with rules 0.4.1 (degrees read
  right). 97,749 cores, 73,968 groups, 49,161 topics. Parity with the batch
  99.4% of 1,533 items; blind count 78.0% exact (unchanged); release gates
  pass. Lookup on held-out postings agrees with the batch group 99.6% when
  known, 72.5% when placed by similarity. Judge's reference: 8 of 150 group
  decisions called wrong (5.3%, was 7.3%), topics 12% (was 9%; 150 pairs,
  within noise). Explore: Bachelor in Computer Science 873 adverts (was
  747), Master in Computer Science 811 (was 622).
- **0.3.2** · 2026-11-15 · batch regenerated with rules 0.4.2, the 866 items
  in other languages translated first. 96,966 cores, 73,274 groups, 48,821
  topics. Parity with the batch 99.4% of 1,533 items (the same 9 Swedish
  differences as 0.3.1); lookup agrees with the batch group 99.6% when known,
  72.5% when placed by similarity; blind count 79.7% exact on the blind half
  (was 78.0%), 80.9% on all. Judge's reference: 14 of 150 group decisions
  called wrong (9.3%, was 5.3%; p ~ 0.2, not significant), topics 11% (was
  12%). Read: all 14 are narrower/broader or a frame over one object
  (`leading AI adoption` ~ `AI adoption`, `application lifecycle` ~
  `application lifecycle management`), none a different thing; 0.3.1's 8
  held two (`Living` ~ `Vivado`, `database access management` ~ `Access
  database`). Explore: 815 requirements
  (was 813); `HBO work` and `Completed HBO` are Bachelor; Bachelor (any
  field) 365 adverts (was 256), Bachelor in Computer Science 903 (873),
  Master in Computer Science 830 (811); Lithuanian enters. A first 0.3.2 was
  built the same day without the 866 translations, never published, and
  discarded.
- **0.3.3** · 2026-11-17 · batch regenerated with rules 0.4.3, the items now
  read as Danish, Finnish, Czech or French translated first (139 per new
  model). 96,296 cores, 72,744 groups, 48,484 topics. Parity with the batch
  99.4% of 1,533 items; lookup agrees with the batch group 99.6% when known,
  72.4% when placed by similarity; blind count 79.7% exact on the blind half,
  unchanged; pattern cases 138/138. Judge's reference: 12 of 150 group
  decisions called wrong (8.0%), topics 10%. Explore: 816 requirements. The
  whole chain took 57 minutes on a machine with nothing else running.
- **0.3.4** · 2026-11-17 · batch regenerated with rules 0.4.4 (the user's
  review conventions: a name wins, named examples are the requirements). 79,570
  cores (was 96,296: -17%, the same technology no longer split across its
  contexts), 60,207 groups, 40,447 topics. Parity with the batch 99.4% of 1,533
  items (casing and one `and industry` split); lookup agrees with the batch
  group 99.6% when known, 71.9% when placed by similarity; blind count
  unchanged on the blind half, found/human 1.128 -> 1.117. Judge's reference:
  11 of 150 group decisions called wrong (7.3%, was 8.0%), topics 17 of 100
  (was 10: within the noise of 100 pairs, ±7 points, and read — mostly coarse
  topic merges such as `Technical autonomy` / `Operational autonomy`, not the
  new rules). Two rule artefacts seen there, left for 0.4.5: `Interest and
  experience in X` keyed `Interest and`, `experience minimum in X`. Explore:
  806 requirements. Chain 48 minutes.
