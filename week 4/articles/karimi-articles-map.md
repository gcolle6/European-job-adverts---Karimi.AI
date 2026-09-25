# Two articles: the map

## The dividing line

## The distinction between article 1 and 2

Article 1 measures how far a job family's
requirements move when something around it changes, and then spends most of its
length removing the reasons that measurement could be wrong. Its unit is mainly
**factor**: industry, country, seniority, company type, company size, work type.

Article 2 says which requirements belong to the industry you happen to be in and which requirements are core to the job family. Then shows
whether Europe's official list of skills even names them. Its unit is a
**requirement group**: Python, food industry knowledge, SQL skills.


## The test that keeps the development of the two articles separated: twelve sentences, assigned

The test is only useful if it is applied to real sentences. These are the kinds
of thing that will come up.

| sentence | goes to | why |
|---|---|---|
| "Country looked like the strongest factor." | **1** | a factor, a magnitude |
| "Adverts from one country tend to share a language." | **1** | a confound on a magnitude |
| "Food industry knowledge is asked 20× more in Agriculture & Food." | **2** | needs the name |
| "Industry and seniority finish level." | **1** | ranking factors |
| "Python is the most common technical requirement and one of the most portable." | **2** | needs the name |
| "One employer posted the same advert 474 times." | **1** | a confound on a magnitude |
| "Each lift is reported with how many employers asked for it." | **2** | a qualifier on a named group |
| "Sales requirements shift 1.18× more than software's between industries." | **2** | the core/shell claim, the article's thesis |
| "The industry step gets larger once you hold country fixed." | **1** | a magnitude, corrected |
| "A quarter of requirements match no ESCO concept." | **2** | about what requirements are |
| "Groups are multilingual, so the clusters are not an artefact of translation." | **2**, one line | an assurance, not an argument |

Doubts on one of them, but it doesn't mean they cannot appear in both:

**"One employer posted the same advert 474 times"** seems to belong to article 1, company size is a factor and has an impact on how requirements asked change. On the other hand, the
employer counting affects article 2's numbers too. It is a *confound*.

---

# 2. Where charts 3 and 4 have been moved

**Chart 4 — employers and repetition → article 1.**
Even if it is a confound, it remains fundamental for the analysis in article 1, focusing on one of the factors, which is the size of the company.

**Chart 3 — the ESCO residual → article 2.**
It is an interesting part of the method followed to arrive at the conclusion of the analysis. Not all requirements are mapped by ESCO, why? Which of these are core and which shell? 

---

# 3. Article 1 — What changes the job

**Target reader:** Everyone, and more specifically someone who wants
to know whether where they work changes what is asked of them, what seniority really brings to the table and how much weight it has on the role here vs there.

**Opening move.** Same job title, different company. Six things vary around it.
Which of them actually changes what you are asked for? Set up the measurement in
two sentences: take three levels of a factor, hold the job family fixed, see how
far apart the requirement profiles land.

1. **The naive ranking.** Country first, seniority and industry behind, company
   size last. Seems to be the answer, but then we refuse it.
2. **The first confound: language.** A country is also a language, and the
   requirement text is what was read and grouped. The United Kingdom is 99.8%
   English, France 56.7% French, Germany 59.0% German — and those are exactly the
   three countries the comparison ran on, which is the worst case, not a
   convenient one.
3. **The correction.** Rerun on English-only adverts. Country loses 18.9% of its
   distance. Nothing else moves more than 2.6%, and company size moves *up* by
   1.2% — movement in the wrong direction, which is what noise looks like and
   which sets the scale for reading everything else.
4. **The second confound: geography.** Industries are not spread evenly across
   countries, so is an industry step partly a country step? Block on country and
   measure again.
5. **The correction, which goes the other way.** The industry step gets
   **larger**, not smaller — the opposite of the worry. The control move,
   climbing a seniority level, barely shifts, which is what makes it a control.
6. **The third confound: who is talking.** One employer posted the same advert
   474 times. Templates inflate whatever they repeat. Volume is not the tell: the
   largest poster writes 975 genuinely different adverts, while a much smaller
   poster writes 86 near-identical ones.
7. **The correction.** Count each employer once. Every distance shrinks, no
   factor overtakes another. A correction that moves everything by about the same
   amount changes the size of the answer, not the answer.


## Figures

TBD

## Not in this article

Core and shell. Any specific named requirement
group as a finding — one may appear as an illustration inside a clause, but the
moment a paragraph is *about* a skill it has crossed the line. ESCO. The
sales-versus-software difference as a claim: both families appear only to show
that the ranking is the same in each.

---

# 4. Article 2 — What travels with the job family, and what belongs to the industry

**Target reader:** Everyone and more specifically people curious to know whether moving from one industry to another implies a new set of industry-specific skills.

**Opening move.** Two people with the same job title, one in a bank and one in a
food company. How much of what is asked of them is the same? Introduce lift: how often a requirement is asked in one industry against how often
it is asked in the same job family everywhere.

1. **The measure, and why it has two axes.** 1× means it stays with the job family, 20× means it
   belongs to the industry specifically. But a requirement that is distinctive and almost never
   asked for is not a finding: `MacOS and Apple devices` peaks at 9.2× and
   appears in 2.6% of that cell's adverts. That is why the chart puts share on
   the vertical axis, and why most groups are grey.
2. **The core.** 91 of 580 groups sit near 1× and are asked often.
   Python at 1.22× in a tenth of all adverts is the headline: the most common
   technical requirement is also one of the most portable.
3. **The shell.** 149 of 580 concentrate in one cell. Food industry knowledge at
   20.3× in software roles in Agriculture & Food, across 27 different employers —
   which is what makes it a property of the industry rather than one firm's house
   style, and why the employer count is printed beside every lift.
4. **The majority is neither.** 340 of 580 clear neither bar: 263 not distinctive
   enough, 77 distinctive but too rare. Grey is the ordinary case, not a leftover
   category.
5. **The asymmetry — the article's central claim.** Sales carries a thicker shell
   than software. The variance index ratio is **1.182 [1.159, 1.205]**, P(>1) =
   1.000. This was committed before the data was seen.
6. **Why you can believe it.** See the block below. The direction is stable; the
   size is not, and both should be said.



## The variance index:

**What it says.** How far a job family's requirement profile moves when the industry
around it changes. One number per job family; the comparison between the two is
the hypothesis.

```
software 0.307      sales 0.381      ratio 1.182 [1.159, 1.205]   P(>1) = 1.000
```

**What a cell is, and what it is not.** A cell is one **job family** in one
industry — every software and data advert in Agriculture & Food, pooled. It is
not one job title. The corpus has 16,744 distinct titles across 25,800 adverts,
so `data engineer` and `backend developer` and `data analyst` all sit in the same
cell. The article must not say "the same job" when it means "the same family".

**The objection that follows, and its measured answer.** *Maybe industries
advertise different jobs rather than asking different things of the same one.*
This is the sharpest objection to the whole study, and it was tested rather than
argued.

Four titles have enough adverts in three or more industries: `account manager`
(5 industries), `business development manager` (4), `software engineer` (4),
`data engineer` (3). For each, the distance between industries was computed twice
— once holding the title fixed, once across the same industries and the same
family with any title — with **both subsampled to the same cell size**, because
small cells look further apart than large ones even when the true profiles match,
and the fixed-title cells hold only 10 or 11 adverts.

| title | family | industries | title fixed | any title | ratio |
|---|---|---|---|---|---|
| account manager | sales | 5 | 0.798 | 0.817 | 0.98 |
| business development manager | sales | 4 | 0.787 | 0.813 | 0.97 |
| software engineer | software | 4 | 0.837 | 0.856 | 0.98 |
| data engineer | software | 3 | 0.691 | 0.835 | **0.83** |
| | | | | | **mean 0.94** |

Fixing the title keeps **94%** of the distance. The index is therefore mostly
industries asking different things of the same job, not industries advertising
different jobs — which is what the article claims, now resting on a measurement
instead of an assumption.

Report it with its limits. Four titles, cells of ten, so the absolute numbers are
inflated by noise and **cannot** be read against the published 0.307 — only the
ratio means anything. `data engineer` at 0.83 is the one case where a sixth of
the distance did turn out to be role mix, and saying so is what makes the other
three believable.

*Code:* `week 4/articles/title_control.py`.

**How, in four steps.**

1. **A cell profile.** A cell is one job family in one industry. For each
   requirement group: the share of that cell's adverts asking for it.
2. **The distance between two profiles.** Jensen–Shannon, bounded 0 to 1. For
   software in Agriculture & Food against software in Financial Services, over
   578 groups, it is **0.419**. The worked example to put on the page:

   | | Agriculture & Food | Financial Services |
   |---|---|---|
   | Financial services experience | 2.3% | 17.6% |
   | Food industry knowledge | 14.4% | 0.1% |
   | SAP experience | 11.5% | 0.9% |
   | SQL skills | 3.0% | 13.3% |
   | Python proficiency | 2.3% | 9.8% |

3. **The index is the mean over every pair.** Ten industries, 45 pairs per
   family. Software averages 0.307 over a range of 0.224–0.420; sales averages
   0.381 over 0.287–0.497. **Sales sits higher across the whole range, not
   because of one extreme pair** — worth saying, because a mean alone invites the
   suspicion that one outlier carries it.
4. **Bootstrap.** 1,000 resamples, fixed seed, for the interval.

**Three design choices, each a defence against a specific objection.**

- **Posting shares, never requirement counts.** Extraction misses ~19.5% of
  requirements and misses them unevenly — long-segment exposure is 4.4% of
  software segments against 2.4% of sales, which is precisely the comparison the
  hypothesis turns on. "What share of adverts asked for this" is invariant to
  under-counting inside an advert; "how many requirements did this advert have"
  is not.
- **L1-normalised before comparing.** Removes verbosity: a cell whose adverts
  simply list more would otherwise read as more distinctive when it is only
  wordier.
- **Jensen–Shannon rather than Kullback–Leibler.** Symmetric, and defined when a
  group is absent from one cell — which happens constantly. `Food industry
  knowledge` at 0.1% is the example.

**Why the bootstrap is not decoration.** Two cells of 300 adverts look further
apart than two of 3,000 even with identical true profiles: noise inflates
distance. Cells here run from ~300 to ~5,200, so the raw index partly measures
how small the cells are — and that bias **does not cancel between the two
families**. `equalise=n` resamples every cell to the same size and is the direct
test: a gap that disappears under equalising was a difference in cell size, not
in the labour market. It does not disappear.

**Why this replaced the first version, which is the strongest argument for
trusting it.** The original index *counted* groups above a shell threshold, so it
was threshold-dependent by construction: a group one point below the cut-off
contributed nothing, one point above contributed a whole unit. Across four
threshold settings that count moves between **1.341 and 1.670**. The continuous
index, over the same four, moves between **1.149 and 1.168**. Show both. The
point is not that the finding got better — it is that it was not measurable until
the measure stopped being arbitrary.

## Figures

TBD, plus one to add.

**The shell, named.** A horizontal bar chart per cell: macro-area as a heading,
the requirement groups under it, one bar each. The bar is lift, the count of
employers asking sits beside it. Two or three cells shown, one clearly software
and one clearly sales.

What it is for: chart 2 has 580 dots and you have to hover to learn anything,
so the article's most quotable finding is currently unreadable. This says
`Pharma industry experience, 18.6x` in words, and groups it under DOMAIN so the
reader sees the shell is not only tools.

Form borrowed from Revelio Labs; the magnitude is not. Theirs is a wage
premium and this corpus has no pay field at all.


## Not in this article

The driver ranking. Language, beyond one sentence confirming that groups are
multilingual so the comparison is not an artefact of translation. The employer
counting rule as an *argument* — every lift carries its employer count, and the
rule itself is cited to article 1 and not re-derived.

---

# 5. The three overlaps, and the rule for each

**Employers.** Article 1 establishes the counting rule and owns the evidence for
it. Article 2 uses it — each lift is reported with the number of employers asking
— and does not re-argue it. One sentence of citation is the whole permitted
overlap.

**Industry.** Article 1 treats it as one factor among six and asks how much it
moves things. Article 2 treats it as the axis and asks which things move. Neither
sentence should be writable in the other piece.

**Sales versus software.** Article 1 shows both families only to demonstrate that
the driver ranking is the same in each, and makes no claim about the difference.
Article 2 makes the difference its central claim.

---

