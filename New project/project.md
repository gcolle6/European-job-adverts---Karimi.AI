# New project — the normalised requirement vocabulary, and what it makes possible

*One document. Written piece by piece as the project is decided. Nothing here is
a plan for its own sake: each section is added when the thing it describes has
been settled or measured.*

---

## Why this is the first thing and not the second

## What we are building — decided, with a working prototype

**One sentence: *which of your requirements travel, and where they travel to.***

Nesta Career Causeways answers *"what other job could I do?"* This answers a
question it structurally cannot: ***"what does my own job ask for somewhere
else?"*** — because the unit here is the advert, not an occupation record, so the
same role can be read separately in every sector it appears in. Most people are
not trying to change profession; they want to know whether a sector move is
viable and what it would cost. That is the gap, and it is the project's own
core/shell thesis pointed at a user: **the core is the portable asset, the shell
is what the move would cost.**

### 0.1 It is built, small, and it works

*Code:* `New project/prototype_map.py`, on the 25,800-posting base already in
hand. **28 roles** clear 50 adverts and 15 distinct employers (14.7% of postings;
the employer floor is there because 50 adverts from 2 companies is a template).

**Nearest roles, by overlap distance** — every one is right, with no supervision
and no labels:

| role | nearest, with distance |
|---|---|
| software engineer | backend engineer **0.36**, software developer 0.38 |
| account manager | key account manager **0.28**, business development manager 0.35 |
| devops engineer | platform engineer **0.36**, software engineer 0.50 |
| data scientist | machine learning engineer **0.43**, data analyst 0.43 |
| sales development rep | business development rep **0.31**, account executive 0.39 |
| product manager | product owner **0.39**, account manager 0.48 |

🔵 **It also caught a data error nobody was looking for.** `business developer` is
labelled `SOFTWARE_DATA`, and its three nearest roles are *account manager*, *key
account manager*, *business development manager* — all sales. The map audits the
field it was built from, which is a second product in itself.

**Core and shell per role** falls out of the same vector. `account executive`:
core = *Sales experience* 34%, *Communication skills* 30%, *Negotiation* 19% —
what travels. Shell = *Sales cycle management* 25% at **3.8×**, *Leadership* at
5.2× — what belongs to that role in that context.

### 0.2 ⚠️ The headline did not survive its control, and the correction is the finding

The prototype first showed a role's industry versions sitting at **0.52** apart
against **0.36** to a neighbouring role — *changing sector costs more than
changing job*. A striking claim, so it was tested rather than published.

**Split-half control**: take one role in one industry, split its adverts at
random, measure the distance between halves. Nothing differs but the draw, so
that is pure noise at that sample size. *Code:* `New project/distance_floor.py`.

| | mean |
|---|---|
| noise floor (same role, same industry, random halves) | **0.43** |
| between industries | 0.50 |
| 🔵 **real excess** | **+0.07** |

**Most of the gap was sparsity**, exactly the trap this project already paid for
when 15-advert companies all piled against one edge. The effect is real — it
clears its own floor in **12 of 14 roles** — but it is modest, and it is *not*
bigger than a role change, because the role numbers sit on larger samples with a
lower floor.

🔵 **And where the excess sits is the actual result: sales +0.116, software
+0.033 — a 3.5× ratio.** That is **H1 reproduced by a third independent method**:

| method | sales / software |
|---|---|
| variance index (overlap between cells) | 1.24 |
| supervised classifier (macro-F1) | 1.4–1.6 |
| per-role industry excess over floor | 3.5 |

⚠️ The magnitudes disagree by a factor of three, so **quote the direction, never a
pooled number**. Three methods sharing no machinery agreeing on direction is the
claim; the size is method-dependent and must be reported as a range across
methods.

### 0.3 What the user sees — four panels, one representation

| panel | question it answers | status |
|---|---|---|
| **Your core** | what this role asks for everywhere — your portable asset | ✅ working |
| **Your shell** | what is asked only here — what you would have to acquire | ✅ working |
| **Nearby roles** | ranked by distance, each with the **gap set**: what they ask that you do not | ✅ working |
| **Same role, other sectors** | what changes if you keep the job and move industry | ⚠️ real but thin — needs the export |

🔵 **The gap set is the product, not the distance.** *"68% similar to Data
Analyst"* ranks a list; *"here are the six things they ask that you do not, and
the four you already have"* is actionable, and it is the same vector read as a set
difference over groups that have names.

### 0.4 Why Karimi should care, beyond the public page

1. 🔵 **The normalisation layer is infrastructure they would otherwise buy** —
   named multilingual requirement groups usable for matching, dedup and search
   across 500k adverts. The least visible deliverable and probably the most
   valuable;
2. **the novelty detector** — requirements fitting no group, which names what is
   emerging before the market has a word for it;
3. **auto-tagging and auditing**, demonstrated above on `business developer`;
4. **an employer view for free**: the same role profile benchmarks a single advert
   against its market — *"you ask for 3 things nobody else asks for, and miss 5
   that 60% of competitors require."* One build, two audiences;
5. a public tool that gets cited, as Nesta's is.

### 0.5 What we do not promise

* **salary** — 28.7% filled in the sample and **absent from the export we hold**.
  Nesta's "desirable" filter rests on earnings; ours cannot without the field;
* **change over time** — four uneven months moving 0.30% is noise. Needs the
  historical depth the overview will reveal;
* **"predicts your next job"** — macro-F1 0.18–0.30. The licensed claim is
  *requirements carry industry information*, never a prediction;
* **a safe/desirable transition filter** — needs job-quality and earnings data
  this corpus does not carry.

### 0.6 The sequence

| stage | what | blocked on |
|---|---|---|
| **0** | ✅ **the prototype above — done** | — |
| **1** | granularity + casing + role normalisation | decisions 3/4/5, and nothing else |
| **2** | the export, scoped by **adjacent** role families | Karimi, with the prototype as the ask |
| **3** | the public artefact | 1 and 2 |

⚠️ **One defect already visible in the prototype's own output** and due in stage
1: the core list prints *English proficiency* twice and *Sales experience* twice.
That is the known duplicate-label problem — 27 cluster pairs, 18 of them
same-language wording variants. Harmless internally, **unpublishable** on a page a
student reads. Fold before stage 3.

🔵 **The strategic point about ordering.** Stage 0 exists so stage 2 is not a
request on a promise. Asking for 500,000 postings is a different conversation when
28 working role pages are already on the table.

---

Everything downstream — clustering, comparison between roles, comparison between
industries, seniority ladders, trends over time, prediction — is a count of
something. **Until two phrases that mean the same thing are the same thing, the
counts are counts of strings.**

> *"gute Python-Kenntnisse"* · *"Experience with Python"* · *"conoscenza di
> Python"* · *"Python knowledge"*
>
> One requirement. Four strings. Three languages.

With ~500,000 postings this stops being a nuisance and becomes the whole
problem: more data multiplies the strings without ever producing a skill. The
vocabulary is the flour. Nothing else gets baked without it.

**What a finished vocabulary is:** a fixed, versioned list of requirement
groups, each named and typed, in which any new advert — in any of the languages
the corpus holds — can be placed **without refitting anything**, and whose
coverage is published so that its decay is visible rather than silent.

---

## The product Karimi shares: the advert decoder

The role map is a destination: someone has to go and visit it. **The decoder sits
where Karimi's users already are — on a job advert.** It is the normalisation
layer turned into one question a candidate actually has: *which of these
requirements are the job, and which are this employer's wish list?* Every line of
an advert looks equally mandatory, and nothing on the page says otherwise.

Once a requirement is mapped to a group, it can be looked up against every other
advert for the same role. Each line gets a verdict:

| verdict | meaning | what the candidate does with it |
|---|---|---|
| **STANDARD** | asked by ≥30% of comparable adverts | the job itself — have it, or the move is not ready |
| **COMMON** | 10–30% | a real plus |
| **UNUSUAL** | <10% | this employer's specific ask — missing it is not disqualifying |
| **NO GROUP** | maps to nothing within threshold | genuinely specific, or new — feeds the novelty detector |

…plus the reverse, which no advert shows: **what comparable adverts usually ask
for that this one does not mention.**

### Why Karimi would want it, not just tolerate it

* it sits on **their** pages and keeps users there — the role map sends traffic
  out to a separate site, the decoder keeps it in;
* it is the **front end of the CV tailoring they already sell**: the decoder says
  which requirements to lead with (STANDARD ones you have) and which to address
  head-on (STANDARD ones you lack); UNUSUAL ones are where tailoring stops;
* the **same lookup serves employers**: *"you ask for 7 things fewer than 1 in 10
  comparable adverts ask for, and do not mention 2 that most do"* — an advert
  benchmark, from one build;
* and it is the natural consumer of everything in Step 1 — **it runs only on the
  automatic standardisation path**, so building it forces that path to exist.

### 0.7 Prototype: built on the existing data, unchanged pipeline

*Code:* `New project/advert_decoder.py`. Runs the Week 1–2 pipeline as is —
`atomise.segments` → `atomise` → `normalise` → local MiniLM → nearest of the 617
centroids above Week 2's 0.55 threshold — against the 28 roles of the prototype
map, **leave-one-out** (an advert is never compared with itself), and with MIXED
clusters reported as NO GROUP rather than given a share they do not deserve.

It works end to end, in any language the corpus holds. A Polish account-manager
advert at DS Smith decodes as: *Pasja do zdobywania nowych klientów* → Customer
orientation, **STANDARD 37%**; *Doświadczenie w sprzedaży* → Sales experience,
COMMON 21%; *Czynne prawo jazdy kat. B* → Driving licence, UNUSUAL 9% — and
flags *Account management experience* (36% of comparable adverts) as not
mentioned. A Lendable data-scientist advert: Python 54%, ML 52%, statistics 38%
— all STANDARD — with *Data experience* (48%) not mentioned.

### 0.8 ⚠️ Not shippable yet, and the reason is measured

Across all 3,799 adverts the prototype said **62.9% of requirements are UNUSUAL**,
98.3% of adverts carry at least one, and the median advert has 7 of 12. A
striking number, so the members were read before it was believed — and the demo
itself showed the problem. *English B2 level* scores **0%** for account managers
although English is among their commonest asks; *Microsoft Excel* scores 0%; and
*Problem-solving skills*, *Problem-solving mindset* and *Structured working style*
are one concept in three groups.

**The vocabulary splits single concepts across several groups**, so a requirement
can be universal while the exact group it lands in is rare. *Code:*
`New project/decoder_fragmentation.py` pools each group with its neighbours above
centroid cosine τ, against a control pooling the same number of groups at random:

| τ | mean neighbours | UNUSUAL | STANDARD | random pool: UNUSUAL / STANDARD |
|---|---|---|---|---|
| 1.00 | 1.0 | 62.9% | 8.9% | 62.9% / 8.9% |
| 0.85 | 1.3 | 55.8% | 14.0% | 58.8% / 10.1% |
| 0.80 | 1.9 | **46.5%** | **20.9%** | 54.0% / 12.1% |
| 0.75 | 3.1 | 36.2% | 29.0% | 44.6% / 16.0% |

Two readings, both needed:

1. 🔵 **Fragmentation is real.** Semantic pooling moves the verdicts ~8pp further
   than random pooling of the same size, and nearly doubles the STANDARD share
   against the control at τ = 0.80. The 62.9% is substantially the instrument;
2. ⚠️ **centroid geometry cannot fix it on its own.** *Microsoft Excel* has no
   neighbour above 0.85, nor does *Problem-solving mindset* — the obvious
   synonyms are not close as centroids. Same lesson as cluster 396: an
   embedding's errors are not visible in that embedding's own geometry. The fix
   is the granularity work in Decision 3 with human review of merges, not a τ.

τ is deliberately **not chosen** here — picking the one that gives a pleasant
number after seeing it is threshold-shopping.

🔵 **The error is asymmetric, which says what could ship first.** Fragmentation
can only make a requirement look *rarer* than it is, never more common. So:

| verdict | bias from fragmentation | usable now? |
|---|---|---|
| STANDARD | conservative — only understated | ✅ a STANDARD call is safe |
| UNUSUAL | **inflated** | ❌ would tell candidates to ignore things that matter |
| NOT MENTIONED | **false positives** — a synonym in another group reads as absent | ❌ |

UNUSUAL is exactly the verdict that changes a candidate's behaviour, so it is
the one that must not ship on the current vocabulary.

### 0.9 This gives Step 1 an acceptance test

Until now "the vocabulary is good enough" had no operational meaning. The decoder
supplies one:

> **The vocabulary is at the right granularity when pooling semantically
> neighbouring groups moves the decoder's verdicts no more than pooling random
> groups of the same size.**

At that point no near-synonym groups remain for pooling to merge, so a verdict
reflects the market, not the dictionary. Today semantic pooling beats random by
~8pp at τ = 0.80 — that gap is the work outstanding, and it can be re-measured
after every change to the vocabulary.

### One design point for the page

Show **the employer's own sentence** with the verdict beside it, never the atom.
The prototype's atoms carry visible extraction damage — *"Implemented privacy"*,
*"Proficient in comfortable navigating large cod…"* — harmless inside a profile,
embarrassing on a page a candidate reads. Atoms are machinery; the page shows the
advert.

---

## Step 1 — the vocabulary

### 1.1 What already exists, and how far it got

Built over four weeks on a 25,800-advert slice. The pipeline, in order:

```
  must_have text
    -> segments                      184,444
    -> atoms          (split compounds)        349,061
    -> normalised phrases (accents, case)      210,195 unique
    -> embeddings     (multilingual, 384-dim)
    -> clusters       (UMAP + HDBSCAN)
    -> named groups                            594
```

**What is validated and should be kept:**

* **cross-lingual alignment** — the thing that licenses comparing a German
  advert with an Italian one at all. Separation 0.420, **95.0% retrieval**,
  tested with negative controls, not just positive ones;
* **the clustering itself** — Gate 2 hand-checked 25 groups; the published map
  survived a cased refit that moved the headline ratio by 0.007;
* **the naming**, with three defect classes found and flagged by hand.

### 1.2 What is wrong with it, all measured

🔴 **It was never built to be a vocabulary.** It was built to answer two
hypotheses about industries. Everything below follows from that: decisions were
taken that were right for an article and are wrong for a reusable asset.

| | |
|---|---|
| **extraction never passed its gate** | atomisation **0.687 precision / 0.556 recall** held out, against a 0.90 / 0.75 threshold. Corpus-projected: ~86% precision, **80.5% recall** — we miss about a fifth of requirements |
| **83% of groups are too thin to use** | only **99 of 594** clear the 3%-of-adverts rule the published work used |
| **the embedding is fed lowercased text to a cased model** | 45.6% of phrases carry a mid-phrase capital; **~4.6% of the vocabulary is misassigned** by lowercasing alone. `Experience with Azure` lands in *Relevant experience*, not in *Cloud platforms* |
| **grab-bag groups** | 7 groups are frames, not requirements — *Relevant experience*, *Technical knowledge*, *General skills* |
| **MIXED groups** | 4 of 617 found, all by a human reading members. **Two automated detectors were built and both failed**; do not re-try them without a signal that does not run through the sentence embedding |
| **duplicate labels** | clusters sharing one name, folded 580 → 555 |
| **bare-head atoms** | 1,473 (0.42%) lost the complement that carried their meaning |

⚠️ **The casing decision has to be re-opened, and this is the clearest example of
"right for an article, wrong for an asset".** A cased refit was built and tested;
none of the three pre-committed rebuild triggers fired, so it was not adopted —
the published numbers barely moved. But *"it does not change the conclusion of
article 2"* is a different test from *"it is correct for a vocabulary that
everything will be built on"*. `Experience with Azure` **is** repaired by the
cased version. For a reusable layer, that is the test that matters.

### 1.3 The five decisions, with the evidence already in hand

Each of these was reached the hard way during the four weeks. They are recorded
here so the new build starts from them rather than rediscovering them.

---

#### Decision 1 — casing: **two inputs, not one choice**

⚠️ **The instinct is to lowercase everything, and it is backwards.** Lowercasing
is what caused the errors, not what prevented them.

| `Experience with Azure` | nearest group | cosine |
|---|---|---|
| raw text | **Cloud platforms [AWS, Azure]** — correct | 0.7433 |
| lowercased, which is what the pipeline embeds | **Relevant experience** — wrong | 0.8469 |

The two embeddings sit at cosine **0.5223** — further apart than most genuinely
different requirements are from each other. Measured at scale: **45.6% of the
corpus carries a mid-phrase capital**, and for those phrases the nearest group
changes **21.1%** of the time against an 11.0% control, so roughly **4.6% of the
vocabulary is misassigned by lowercasing alone**. The direction is systematic:
lowercasing moves phrases *out of* specific content groups and *into* generic
frame groups — `Cloud platforms` −25, `CRM systems experience` −9, while
`Technical knowledge` +29 and `Relevant experience` +28.

**But lowercasing is right for the other consumer.** The regex lexicon cannot
match without flattened accents and case — that is documented and correct. The
root cause was never a choice between them: **one normalised string was reused by
two consumers with opposite needs**, and nothing decided it.

🔵 **Decision: keep both.** `phrase_norm` (lowercased, accents stripped) for the
lexicon; `phrase` (raw, or a light clean that preserves case) for the embedding.
Costs one extra column and removes the defect.

⚠️ Not uniformly better, and worth knowing: `Deep familiarity with GDPR` goes to
*Economics degree* raw and to *GCP/GDPR knowledge* normalised. The fix is right
on balance, not everywhere.

---

#### Decision 2 — extraction: the 20% is lost **without** the LLM, not with it

⚠️ **Also easy to get backwards.** Rules alone are what lose the requirements.

| held out | precision | recall |
|---|---|---|
| rules only | 0.687 | **0.556** |
| rules + LLM on the routed residue | 0.692 | **0.617** |
| LLM on every segment | 0.632 | 0.520 — *worse than the rules* |

Corpus-projected, rules alone give ~86% precision and **80.5% recall**: we miss
about a fifth of all requirements. The third row matters as much as the second —
**a model applied to everything is worse than the regex**, so the cheap
deterministic layer is not merely cheaper, it is more accurate on what it
handles. Keep the rules; spend the model only on the residue they route to it.

**What stops the rules is structural, not tuning.** They cannot do generative
splitting: a labeller turns *"Experience applying AI to complex financial
domains, including credit"* into *"Experience with credit"*, and no pattern
produces a head that is absent from the source. Four other routes were tried and
all failed — recursion, suffix rules, dependency parsing, real POS tags.

🔵 **So the decision is not about accuracy. It is about sending requirement text
to a third-party API**, which needs Karimi's explicit agreement and has never had
it. The residue is isolated and priced: **31,510 segments, 2.46M characters,
~616k input tokens, no identifiers in the payload** — requirement text only, no
company, no geography.

---

#### Decision 3 — granularity

594 groups from 25,800 adverts, of which only **99 clear 3% of adverts**. At 500k
the same parameters give many more. How many is a choice, and it decides whether
`Python` and `Python 3` are one group or two, and whether `Communication skills`
stays one bucket or splits into written and spoken.

⚠️ **Finer is not automatically better.** The grab-bag groups show the failure in
one direction — *Relevant experience*, *Technical knowledge*, *General skills*
are frames that swallow anything. The duplicate-label problem shows it in the
other: clusters that mean the same thing under one name, folded 580 → 555.

---

#### Decision 4 — how a new advert attaches

Nearest centroid above a threshold, else `unassigned`. **That threshold is the
contract** between the vocabulary and everything built on it: too loose and
`unassigned` never fires, hiding drift; too tight and coverage collapses.

Reference points from the existing build: the hybrid classifier reaches **92.6%
corpus coverage** against the lexicon's 53.1%, at 0.754 accuracy on what it
assigns against the lexicon's 0.927 — a genuine trade, not an upgrade, and both
numbers must be published together.

---

#### Decision 5 — versioning, and the trigger

The vocabulary will decay as new requirements appear that no group fits. 🔵 **The
decision to make now is the trigger, not the schedule**: when the unassigned
share rises past a stated point, a new version is cut. Fixing that in advance is
what turns drift into a dated decision.

⚠️ And a version boundary must never be crossed silently mid-analysis. A
cautionary case from the build: `_cache_key` took a `prompt_version` argument and
ignored it, so renaming a constant orphaned 150 cached results and the pipeline
fell back to an earlier stage — a change that looked like it cost 7 points of
recovery actually gained 1.7. **A `str.replace` patch that does not match fails
silently; assert on the match, or use an editor that errors.**

---

### 1.4 What "done" looks like

Not "we have clusters". Five things, each checkable:

1. **fixed and versioned** — `v1`, with a date, a corpus size and a parameter set
   recorded, reproducible from raw text by one command;
2. **assignable** — a new advert in any of the eight languages maps on without
   refitting, and the rule for doing so is written down;
3. **measured coverage** — the share of atoms that land in a group, published and
   tracked, so decay is visible;
4. **named and typed** — every group has a human-readable name and a requirement
   type, with the known defect classes flagged on the group rather than in a
   footnote;
5. **audited** — a human has read a sample of groups and the agreement rate is
   published, whatever it is. Gate 2 did this for 25 groups; a vocabulary needs
   more.

### 1.5 Open questions for Karimi

* **Do they already normalise skills, or count raw strings?** If a normalised
  vocabulary exists on their side, this step changes shape entirely. This is the
  first thing to ask and the answer costs nothing.
* **How are repeats handled** when the corpus accumulates rather than being
  snapshotted? In four months we found one employer posting the same advert 41
  times. Over a year that compounds, and it inflates every count in the
  vocabulary without looking wrong.
* **Can we have the fuller export** — more job families than the two we hold,
  which were 24.5% of a database that has since grown roughly fivefold.

### 1.6 Traps already paid for

Every one of these cost time or produced a wrong number before it was caught.
They are listed so the new build inherits the lesson instead of the bill.

#### The ones that produce confident wrong answers

🔴 **When a number moves a long way for free, the instrument changed — not the
thing being measured.** Three times in one project:

* a semantic matcher took atomisation from 0.69/0.62 to **0.89/0.79** and nearly
  passed the gate. Reading the 76 newly-accepted pairs showed it was crediting
  truncated fragments: `Open Source` matched to *"Experience at an Open Source
  company"*. **A metric changed after seeing a failure must be audited before it
  is believed;**
* a cache bug silently orphaned 150 results, making a change look like it cost 7
  points when it gained 1.7;
* a "fragments emitted" category looked like 15% of lost mass; the members were
  mostly correct two-word requirements.

🔴 **When a category produces a striking number, read its members before
believing it.** A sweep said 6% of requirement mass was wrongly in the ESCO
residual; reading the hits cut it to **1.1%** — `Microsoft Azure` had come back
"found in ESCO" because a member phrase read *Microsoft Access*.

🔴 **Leave a unit out of its own benchmark.** Comparing an industry against an
average that includes it made the largest industry look unremarkable by
arithmetic: AI, Data & Software scored last at 1.2% because, with a third of all
software adverts, it *was* the average. Score correlated **−0.65 with cell size**.
Compared against the other nine, it moves to 18.2% and the correlation falls to
+0.13.

🔴 **Compare like with like, or sparsity decides the answer.** A company with 15
adverts is "unlike" a 14,700-advert aggregate by construction — it cannot mention
as many different things. Every company piled against one edge. Comparing
companies to *other companies* fixed it.

🔴 **A count is not a concentration.** The published chart carries an employer
count as its reliability signal. `Empathy` has six employers and **71 of its 79
adverts come from one of them**. `Swedish fluency` has fifteen and is 87% one
company; `Time management` has forty-one and is 69% one. Measured across the
chart: **one in five industry-specific groups is more than half a single
employer.** Any group-level statistic needs a concentration guard, not a count.

🔴 **You cannot detect an embedding's own error with that embedding's own
geometry.** Two detectors were built for the `Messaging systems` cluster — 55% of
which is the German soft skill *Kommunikationsstärke* — and both failed, because
the thing that made the cluster wrong is the same thing the detector measures. A
human reading members remains the only instrument that catches this class.

#### The ones about measurement discipline

* **Never tune against the rows that score it.** Dev was 0.791/0.627 against
  holdout 0.681/0.560 — an 11-point precision gap, which is exactly the
  self-congratulation a split exists to prevent;
* **Watch metrics that reward abstention.** `accuracy_on_assigned` rises whenever
  a classifier answers less. The lexicon beats the hybrid on it (0.927 vs 0.754)
  while covering 53% against 93%. **Always publish coverage beside it;**
* **Every positive check needs a control.** Requirement-like language in role
  summaries looked like signal until the control showed the same rate in the
  other group;
* **Check that a field means what its name says.** `language` describes the
  advert, not the requirement text: **10.9% of postings carry `must_have` in a
  different language**. Validation had been stratified on the language of a
  document nobody was labelling;
* **Small test sets lie.** 60 phrases gives roughly ±5.5 points; do not rank
  models on smaller differences;
* **A fix that repairs its target and leaves the aggregate unchanged is the
  signature of a long tail** — the signal to stop hunting patterns.

#### The ones about the tooling

* `python3` on PATH is a Microsoft Store stub — use the full Python 3.11 path;
* **bash heredocs mangle backslashes**: `\\s` arrives as `\s` and Python reads a
  literal `s`. Write `.py` files with an editor, never via heredoc;
* console is cp1252 — set `PYTHONIOENCODING=utf-8` before printing non-ASCII;
* the folder is inside OneDrive: **files look stale in an open editor**, and a
  freshly written file may need the editor reloading before it is visible;
* `pathlib.write_text` truncates before encoding — a lone-surrogate string
  (`🔴` instead of `\U0001F534`) empties the file to 0 bytes. Encode
  first, write bytes, `os.replace`;
* **merge collisions**: `requirements.parquet` already carries `company` and
  `company_industry`; re-merging the base shadows them with `_x`/`_y`. This has
  produced a wrong number three times;
* `~` on an object column is bitwise negation, not boolean NOT. Cast, do not
  trust.

#### The ones about regex, which the lexicon layer will meet again

* **Anchor stems on a leading word boundary only.** Closing a pattern with `\b`
  means `communicat` can never match `communication` — this cost 13 points of
  coverage before it was found;
* **a hyphen is a word boundary**, so a bare `\b` matched the `on` inside
  `Hands-on` and took it as the governing preposition. `(?<![-\w])` fixes it and
  also protects `go-to-market`, `end-to-end`, `in-depth`;
* the lexicon runs on **normalised** text: write `esprit d ?equipe`, not
  `esprit d'équipe`. German compounds bind the marker to the word
  (`englischkenntnisse`), so no boundary precedes it;
* **morphology is a stranding signal only where the language's own convention is
  nominal.** German nominalises, French does not — a rule built on German endings
  flagged 21 correct French adjectives.

---

### 1.7 What to ask for first: an overview, not an export

The existing overview is `Country × Industry × Vacancies × Unique companies`. It
was enough to check that the grid had cells; it cannot answer the three questions
that decide this project.

🔵 **Ask for aggregates before asking for data.** Each table below is a
`GROUP BY`, carries no personal data and no advert text, and unblocks a decision
that would otherwise be guessed. The export request is then shaped by what they
show — which is also a better thing to put in front of a data owner than an
open-ended "send us everything".

| # | table | the decision it unblocks |
|---|---|---|
| **1** | **postings by language**, and separately by the language the `must_have` text is actually in | the vocabulary must cover the languages. We already know these two disagree: **10.9% of postings carry `must_have` in a language other than the recorded one.** If that has grown, stratification and the lexicon both change |
| **2** | **field coverage**: share of postings with `must_have` filled, the distribution of how many items it holds, and the same for `salary_range`, `work_type`, `seniority`, `deadline` | decides what is analysable at all. `salary_range` is 28.7% in the 998-row sample and **absent from the export we hold** — the whole "what does the step up pay" axis depends on this one number |
| **3** | **top 300 normalised job titles by volume**, with unique employers for each | 🔵 **the most valuable of the seven.** Everything after step 1 is "reproducible for every role", and that is only true if roles have depth. This says how many roles clear a usable threshold, and therefore whether the map is 20 roles or 200 |
| **4** | **postings by month**, from the earliest record to now | decides whether demand over time is possible. Our four months are uneven and move 0.30% — noise. This says how much history actually exists |
| **5** | **employer concentration**: postings per employer, as a distribution — top 20 by share, and how many employers account for 50% of all postings | the trap that breaks group-level statistics silently. Measured on our slice: **one in five industry-specific requirement groups is more than half a single employer**, and a high employer count gives no protection |
| **6** | **repeats**: how many postings are re-postings of the same role, by whatever rule they use — and whether they have such a rule | 🔴 in four months we found one employer posting the same advert **41 times**. In a corpus accumulated over a year this compounds and inflates every count in the vocabulary. If they have no dedup rule, that is itself the finding |
| **7** | **the grid**: postings and unique employers by `macro_function × industry × seniority`, for the countries that matter | tells us whether to slice by industry, by role family or by both — the question this request exists to answer |

⚠️ **Table 3 is the one to insist on if only one is possible.** Industry and
country we can already reason about from the old overview. Role depth we cannot,
and it is the load-bearing assumption of everything after step 1.

⚠️ **And one question that is not a table.** Do they already normalise skills, or
do they count the raw `must_have` strings? If a normalised vocabulary exists on
their side, step 1 changes shape entirely and we should know before building it.
The answer costs them one sentence.


### 1.8 How big the export has to be — measured, not estimated

The instinct is that a vocabulary needs as much text as possible, so the export
should be as large as Karimi will give. **Measured, that is wrong in a specific
and useful way.** *Code:* `New project/saturation.py`, `saturation2.py`
(2026-10-12, seed 20261012, last quarter of the posting shuffle held out).

#### Strings never settle; concepts settle almost at once

Held-out coverage — build the vocabulary on the first *N* postings, then measure
what share of requirement occurrences in postings it has **never seen** are
already in it:

| train postings | raw strings | concepts (617 groups) |
|---|---|---|
| 258 | 10.3% | **96.3%** |
| 1,290 | 19.8% | **100.0%** |
| 5,160 | 32.1% | 100.0% |
| 18,060 | **46.2%** | 100.0% |

On raw strings Heaps' law fits at **V = 35.9 · N^0.855** — nearly linear, so the
string list keeps growing with the corpus and never converges. At 18,060 postings
**more than half of every new advert's requirement strings have never been seen
before.**

🔵 **That gap is the whole argument for the vocabulary**, stated as a number: it
converts a 46%-coverage string problem into a ~100%-coverage concept problem.
Worth quoting in the write-up — it is the clearest single justification for the
step.

⚠️ **The 100% is partly circular and must not be quoted bare.** The 617 groups
were fitted on all 25,800 postings, so every concept exists in the full data by
construction. What the row honestly says is *how heavily concepts recur* — not
that a vocabulary fitted on 1,290 postings would have found 617 groups. It would
have found fewer: HDBSCAN needs minimum cluster sizes, and rare technologies
would not clear them. The defensible claim is **requirement concepts repeat where
requirement strings do not.**

#### What more data actually buys

Not vocabulary. At the current granularity the concept inventory is saturated
long before 25,800 postings. More postings buy two other things:

1. **resolution inside the concepts** — 617 groups is coarse, and a per-technology
   or per-role map needs finer ones. A finer vocabulary has smaller groups, and
   smaller groups need more data to clear a minimum size. **Granularity, not
   corpus size, is what sets the data requirement** — which makes Decision 3 the
   thing to settle before the export is sized, not after;
2. **roles** — more postings means more job titles clearing a usable threshold,
   which is the binding constraint on a transition map.

#### Software needs more data than sales for the same coverage

| | postings | distinct strings | held-out coverage at 70% train |
|---|---|---|---|
| `SALES_BD` | 10,594 | 62,947 | **52.6%** |
| `SOFTWARE_DATA` | 15,206 | 153,375 | **40.3%** |

Software produces **2.4× the distinct strings from 1.4× the postings**, and
covers less of a new advert at every point on the curve. Its requirement language
is genuinely more varied — consistent with Week 1's novelty finding, and arrived
at by a different route. ⚠️ Practical consequence: **a fixed posting count buys
less vocabulary in software than in sales**, so a balanced export is not a
balanced vocabulary.

#### So: scope the export by role family, not by a title list

Three reasons, in order of weight:

1. 🔵 **A title list freezes the vocabulary at the date it is drawn.** The roles
   that matter for a transition map are the rare, emerging and hybrid ones — in
   the tail by definition. A role family keeps the entire tail inside scope; a
   top-300 list cuts it off and makes any later role un-comparable;
2. **it is a field they already have and have already delivered on**, so there is
   nothing to negotiate and nothing to re-derive;
3. size — but this is the weakest of the three, now that the curve is measured.

**The top-300 title list stays on the ask as an overview, not as a scope.** It is
300 rows of `title, postings, employers` — it is not a dataset and nothing is
analysed on it. Its only job is to answer *how many roles have enough depth to be
nodes*, which nothing else can answer and which decides whether the map is
feasible at all. **Scope by family; count by title.**

#### ⚠️ One correction to the previous design, which matters more than the size

Week 1–4 picked two role families chosen to be maximally **unlike** —
`SOFTWARE_DATA` against `SALES_BD`. That was right for *"how much of what
employers ask for changes"*: contrast is the measurement.

**It is exactly wrong for a transition map.** A map's output is *"from here you
can go there"*, which is an **edge**, and two distant families give two islands
with nothing between them. Measured already: role-pair distance runs **23–77%**,
and the pairs near 23% are where transitions live — we currently have almost none
of them in scope.

🔵 **So: still role families, but an adjacent neighbourhood rather than a contrast
pair.** Three or four families that plausibly share requirements, so the map has
edges to draw. The old pair can stay in as the negative control — the distance
that should come out large if the measure works.

---

---

## Step 2 — the model, and what it is for

The vocabulary is the flour; this is the first thing baked with it. **It is not an
add-on to step 1 — it is the instrument that measures whether step 1 worked.** A
vocabulary nobody can learn on is a vocabulary that lost the signal.

### 2.1 The feasibility test, run before proposing anything

*Code:* `New project/signal_test.py` (2026-10-12, seed 20261012, 5 repeated
splits). The core/shell question stated as supervised learning: **holding the job
family fixed, can a model tell which industry an advert comes from, from its
requirements alone?**

Three guards, each paid for earlier in this project: the split is **by employer**,
never by posting — one employer posts the same advert 41 times, and
`company_industry` is a *company* attribute, so a posting-level split hands over
the answer; **two baselines**, because a score with nothing to beat means nothing;
and **a label-shuffle control**, which must collapse to chance or the split leaks.

macro-F1, mean of 5 employer-grouped splits, with the range across draws:

| | `SOFTWARE_DATA` (11 ind.) | `SALES_BD` (10 ind.) |
|---|---|---|
| always-largest-industry | 0.048 | 0.025 |
| 🔴 **shuffled-label control** | **0.067** [0.061–0.070] | **0.092** [0.087–0.096] |
| vocabulary profile, balanced | 0.182 [0.169–0.194] | **0.295** [0.263–0.324] |
| TF-IDF raw text, balanced | 0.214 [0.197–0.224] | 0.297 [0.268–0.353] |
| vocabulary profile, unweighted | **0.212** [0.203–0.218] | **0.299** [0.273–0.315] |
| TF-IDF raw text, unweighted | 0.163 [0.144–0.176] | 0.275 [0.249–0.300] |

**Four readings, in order of what they settle.**

1. 🔵 **The control is clean.** Shuffled labels land at uniform chance, so nothing
   leaks through the employer split and every row above it is real.
2. 🔵 **Requirements carry industry information, holding the role family fixed** —
   4× the baseline in software, 12× in sales. The shell is not a reading of a
   chart; it is a quantity a model recovers from unseen employers.
3. 🔵 **H1 reproduces by an independent route.** Sales is markedly more
   predictable than software — 0.295 against 0.182, and the draw ranges do not
   overlap in either weighting. The variance index put the sales/software ratio at
   1.240; this puts it at **1.4–1.6**. Two methods sharing no machinery, same
   direction. That is worth more than either number alone.
4. ⚠️ **The vocabulary does not beat TF-IDF on score — it beats it on stability
   and size.** TF-IDF swings with the weighting choice (software 0.214 → 0.163,
   a 24% collapse) while the vocabulary holds or improves (0.182 → 0.212), and
   TF-IDF's spread across draws is wider everywhere. The vocabulary matches it at
   **617 dimensions against 12,539** — 20× more compact, and every dimension has a
   name.

⚠️ **The honest limit, which must travel with these numbers.** macro-F1 of
0.18–0.30 is strong *evidence of signal* and a *weak classifier*. The claim this
licenses is **"requirements carry industry information"** — never "we can predict
the industry". Nothing in the product should be sold as the second.

🔵 **And that is exactly why the product is unsupervised.** Prediction was the
instrument, not the deliverable. What users get — distances, neighbours, maps —
needs no labels at all, so it is not limited by this score and works on roles the
model has never seen.

### 2.2 What is actually being built

A public tool for students and anyone using Karimi, in the shape the Nesta Career
Causeways map established — with one dimension Nesta does not have.

| the user sees | engine | needs labels? | status |
|---|---|---|---|
| **this role's skill map** — what it asks for, as named groups | vocabulary profile | no | 617 groups exist; too coarse (Decision 3) |
| **nearest roles, and how near** — "from here you can go there", with a number | cosine / overlap distance on profiles | no | measure exists, ranks identically to Jensen–Shannon |
| **what changes by industry** — the same role, ten contexts | lift per cell | no | ✅ **measured as real** by 2.1 |
| **what moves over time** | profile per month | no | 🔴 blocked — four uneven months move 0.30%, which is noise |
| **auto-tagging a new advert** | classifier on the profile | yes, and Karimi has them | feasible, weak — see the limit above |

🔵 **The industry row is the differentiator.** Nesta maps occupation → occupation
on skill overlap. It has no notion that the *same* occupation asks for different
things in different sectors. That is this project's whole finding, and §2.1 is the
evidence it is a real effect rather than an artefact of how adverts are written.

### 2.3 Ingestion: what comes out when a new advert arrives

One representation, three outputs, which is why this is one system and not three
bolted together:

1. **profile** — atomise, assign each requirement to its group, emit a vector;
2. **position** — nearest known roles with distances, which is the map entry.
   🔵 **Unsupervised, so a genuinely new role gets located rather than
   classified** — you cannot classify into a class that does not exist yet, but
   you can always say what it sits between. This is the answer to "what happens at
   ingestion of a role we have never seen";
3. **novelty** — requirements that fit no group within threshold. Per-advert this
   is a flag; aggregated it is Decision 5's drift trigger, and it is the thing
   that tells Karimi something new is appearing in the market before it has a
   name.

⚠️ **Granularity binds here, and §2.1 says where.** TF-IDF beats the vocabulary in
software precisely because software's industry signal lives in **named
technologies**, and 617 groups collapse them into frames like *Cloud platforms*.
Sales has no such problem — its signal is in practice language the groups capture.
So **Decision 3 is not a free parameter: software needs a finer vocabulary than
sales**, and the same cut will not serve both. Settle it before the export is
sized, not after. This is the same mechanism as the casing defect, arriving from a
third direction: named entities carry the specific signal, and anything that
blurs them costs exactly the information the map is for.

---

---

## Step 3 — the roles, which do not exist yet as a unit

The plan says "a map for every role". That assumes a role is something the data
already has. **It is not**, and this is the second vocabulary problem, not a
detail of the first. *Code:* `New project/role_depth.py`.

### 3.1 Titles behave exactly like requirement strings

**17,190 distinct `title_norm` across 25,800 postings — 1.5 postings each.**

| titles with at least | roles | share of postings |
|---|---|---|
| 10 postings | 156 | 17.6% |
| 25 postings | 55 | 11.9% |
| 50 postings | **26** | **8.1%** |
| 100 postings | 6 | 3.0% |
| 200 postings | **0** | — |

**Over 80% of postings sit in a title with fewer than ten adverts.** A node built
on one or two adverts is one employer's wording, not a role — so on the current
corpus the map has roughly 26 defensible nodes, and that is not a map.

🔵 **This is the same shape as §1.8's string finding, arriving on the other axis.**
Requirement strings are near-unique and do not saturate; so are titles. Both need
grouping into concepts before anything can be built on them. **The role axis needs
its own normalisation step, and the plan as stated skips it.**

Cheap normalisation does not rescue it. Stripping seniority words
(`senior`, `junior`, `lead`, `werkstudent`, `alternance`…) merges 6% of titles and
lifts the ≥50 coverage from 8.1% to 11.0%. ⚠️ Stripping employer names moved
essentially nothing (16,164 → 16,154) — and `fruit and vegetables seafood seller
grand frais` survives in the top 12, so that rule **missed its own target case**
rather than finding nothing to do. Do not read it as evidence that employer
branding in titles is rare; it is evidence the rule was too narrow.

The top titles after cleaning also show what the fragmentation is made of:
`software engineer` 218, `data engineer` 182, `account manager` 160 — but also
`commercial animator`, `business application manager`, and the Grand Frais shelf
roles. Real roles, company-specific roles and retail job descriptions sit at the
same level with no field distinguishing them.

### 3.2 This — not the vocabulary — is the reason to ask for the big corpus

§1.8 found the concept vocabulary saturates at ~1,300 postings, so volume buys
almost nothing there. **Nodes are where volume pays.** Projected to 500,000
postings, holding the title mix (crude, but it brackets the answer):

| titles with at least | roles at 500k | share of postings |
|---|---|---|
| 25 postings | ~2,550 | 47% |
| 50 postings | **~1,030** | **35%** |
| 100 postings | ~317 | 26% |

🔵 **So the deliverable is feasible at 500k and is not feasible at 25,800** — on
the order of **300–1,000 nodes**, against Nesta's ~1,600 occupations. That is the
honest sentence to put in the ask: *the corpus size is needed for the map's
nodes, not for its vocabulary.*

### 3.3 ⚠️ The circularity to avoid before it is built in

The elegant move is to group titles by their requirement profiles — two titles
asking for the same things are the same role. It avoids string matching across
eight languages and it reuses work already done.

**It also builds the answer into the question.** If roles are *defined* by profile
similarity and role distance is then *measured* by profile similarity, "these two
roles are close" is true by construction and measures nothing. This is the same
family as the semantic matcher that manufactured a pass, and as the cluster
detector that failed because it ran through the embedding it was auditing — the
third instance, so it should be caught this time rather than after publication.

🔵 **Keep the two axes independent.** Derive the role from the **title string** —
with an external anchor where one exists, since ESCO's *occupations* pillar is a
genuine taxonomy of roles and was never touched by Week 4, which searched only the
skills pillar. Then measure distance on **profiles**. A role set built from titles
and a distance built from requirements share no machinery, so the distance is a
finding rather than a definition.

⚠️ If profile-based grouping is used anyway — and it may be the only thing that
works across languages — then every distance claim must be reported with that
dependency stated, and validated against a role set derived some other way.

### 3.4 What the user actually gets, restated precisely

The distance ranks; **the difference set explains**. "You are 68% similar to Data
Analyst" ranks a list. "Here are the six requirements that role asks for and yours
does not, and the four you already have" is the thing a student can act on — and
it falls straight out of the same vector as a set difference over named groups.
Both come free; only the second is the product.

🔵 **And there are two kinds of move, not one.** Change role and keep the
industry; or keep the role and change the industry. **Nesta prices only the
first.** §2.1 measured that the second is a real effect — requirements carry
industry information at 4–12× baseline with the role family held fixed — so both
can be priced on the same measure, and the second is what this project has that
the reference tool does not.


### 3.5 Two grouping layers, and they are not symmetric

Both axes need the same treatment — many strings, one concept, across languages.
**But the two problems have different shapes, and the differences decide the
method.** Treating them as one job is the mistake to avoid.

| | requirements | roles |
|---|---|---|
| unit | phrase, 3–10 words | title, 2–5 words |
| external taxonomy | ESCO **skills** — tried, **27.5% residual** | ESCO **occupations** — ~3,000 concepts, official labels in every EU language, **never used by this project** |
| cross-lingual difficulty | genuine; earned by the embedding, validated at 95% retrieval | **smaller than assumed** — titles are largely English already, even in French and German adverts |
| cost of over-merging | low: `Python` with `Python 3` loses little | 🔴 **fatal**: `Data Analyst` with `Data Scientist` destroys the product's main comparison |
| escape hatch | HDBSCAN's noise class absorbs doubt | **none** — every advert must land on some node |

**Three consequences.**

1. 🔵 **Roles can lean on an external taxonomy; requirements cannot.** Week 4
   searched only ESCO's skills pillar and found it genuinely missing modern
   tooling. The **occupations** pillar is a different object — a real taxonomy of
   roles, far more stable than skills, with official multilingual labels. So the
   cross-lingual mapping comes from the taxonomy rather than being earned from an
   embedding, which is both cheaper and auditable.
2. 🔵 **It also resolves §3.3's circularity for free.** Roles anchored externally,
   distance measured on requirement profiles: two machineries sharing nothing, so
   "these roles are close" is a finding rather than a definition.
3. ⚠️ **Over-merging must be the thing the method is tuned against**, not
   under-merging. There is no noise class to hide in, and the failure is silent:
   a map where everything is close to everything looks finished.

### 3.6 Measure before modelling — the regex takes half the problem

*Code:* `New project/title_cleanup.py`. Four layers, each a convention actually
present in the data: gender markers (`(d/f/m)`, `- H/F`, `(all genders)`),
bracketed asides, seniority words, and a trailing qualifier after a spaced dash.

| | distinct titles | roles ≥50 adverts | share of postings |
|---|---|---|---|
| raw `job_title` | 18,594 | 13 | 4.7% |
| `title_norm` (current) | 17,190 | 26 | 8.1% |
| + gender, brackets, seniority | 16,013 | 29 | 12.1% |
| **+ spaced tail** | **13,261** | **39** | **18.9%** |

🔵 **A regex more than doubles the usable coverage before any model exists.**
What it leaves is the real problem: **10,734 titles are still singletons — 80.9%
of titles, 41.6% of postings.** So the grouping model has to handle under half the
corpus, not all of it, and that is worth knowing before specifying it.

What those singletons actually look like, which is what the model must solve:
compositional variation (`crm developer`, `data platform solution architect`,
`manager platform & data`), genuine cross-lingual cases (`ingénieur réseaux
sécurité support l2`, `développeur sig open source`), German compounds
(`kaufmännischer mitarbeiter schwerpunkt ausschreibungen`), and titles holding
**two roles at once** (`cybersecurity engineer, soc analyst`) — which is the
atomisation problem again, on the title axis.

⚠️ **The first version of that table said 20.3%, and it was wrong.** The tail rule
was `[-–—/|]` with optional spaces, and a hyphen is a word boundary — so it cut
*inside* words: `it-systemadministrator` → `it`, `hw/sw system engineer` → `hw`,
`ar/vr software engineer` → `ar`, `cto & co-founder` → `cto & co`. **513 postings
became 1–2 character stubs**, and because they collapse onto the same few stubs
they manufacture large fake roles — an `it` node of hundreds of adverts that is
not a role. That is where the extra 1.4pp came from.

🔴 **Fourth instance of "a dash is a word boundary" in this project**, after
`TRIGGER_RE`/`PREP_RE` matching the `on` inside `Hands-on`. The fix is the same
discipline — require spaces around the separator, and never trade a real title for
a stub (`MIN_HEAD_TOKENS = 2`).

### 3.7 How the role grouping gets validated

🔵 **Group on titles, validate on profiles.** The grouping never sees the
requirement profiles, so profile similarity is an **independent** test of it:

* two titles placed in the same role should have requirement profiles closer than
  two titles placed in different roles. That is a measurable separation, with the
  same shape as Week 1's cross-lingual alignment check;
* **the negative control is the one that matters**: a grouping that merges too
  hard will show merged-pair distances no smaller than between-role distances.
  Report both, never the positive alone — the rule this project has paid for four
  times;
* a held-out slice of titles, never used in tuning, as with `dev_holdout_split`.

⚠️ This test is only independent while roles come from titles. If profile-based
grouping is used instead — and it may be the only thing that works on the
singletons — the test collapses into self-agreement and a different validation is
needed: human review of merged pairs, as Gate 2 did for clusters.

---

*Next: the artefact itself — what the page shows and what it is built from.*
