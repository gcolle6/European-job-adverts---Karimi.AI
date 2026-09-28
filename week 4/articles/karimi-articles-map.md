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

**Both articles name requirements. They name them on different axes.** Article 1
names what changes with **seniority**; article 2 names what belongs to an
**industry**. No sentence in one is writable in the other, and where article 1
needs industry it stays general and points here.


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

**Title.** Country, industry, seniority: which one really changes your job?

**Deck.** Analysing all six things that vary around a fixed job title shows how
differently they affect what employers ask for.

**Target reader:** Everyone, and more specifically someone who wants
to know whether where they work changes what is asked of them, what seniority really brings to the table and how much weight it has on the role here vs there.

## The story, and what carries a reader through it

Short sentences, in order. The italic line between each pair is the thing that
pulls the reader forward. **If a section cannot be reached from the one before
it, that is the section to fix.**

**0 · Opening.** Two people. Same job title. Different employer. Six things are
different: the industry, the country, the seniority, the kind of company, its
size, whether the work is in an office. Which of them changes what you are asked
for?

*↓ a question needs a way to answer it*

**1 · The measure.** Take three versions of one thing and compare what employers
ask for in each. The answer is one number. 0 means they ask for the same things,
1 means nothing in common.

*↓ now the number can be read, so read it*

**2 · The first answer.** Six factors, ranked. What kind of company first at
**0.434**, country just behind at **0.417**. That looks like the answer.

*↓ but a number is only as good as what it is measured against*

**3 · The grey band.** Sort the same adverts into groups at random and compare
them. They are never identical: a little difference always shows up by luck
alone, and the band is how much. It is wider where the groups are smaller. *Look
again at the chart — the factor on top has an enormous band.*

*↓ so start with the one on top*

**4 · The first illusion is sample size.** Each kind of company does ask for
different things: corporates for Excel, startups for Python, the public sector
for a computer science degree. But the smallest kind is defined by **Dutch
fluency at 23.3%**, because **44%** of those adverts come from the Netherlands
and Belgium. It is also the smallest category, so every group in the comparison
shrinks to **172 adverts**, where luck alone gives 0.342. **It falls from first
to fifth.**

*↓ one down. Now the one that was just behind it*

**5 · The second illusion is language.** A country is also a language. The
United Kingdom is **99.8%** English, France **56.7%** French, Germany **59.0%**
German — and those are the three countries the comparison ran on. Read every
advert in one language and country loses **18.9%** where nothing else moves more
than 2.8%. **It falls from second to fourth.**

*↓ two illusions removed. Is there a third?*

**6 · One more check.** Industries are not spread evenly across countries, so is
changing industry partly changing country? If it were, the same move inside one
country would leave *less* to learn. It leaves more — software 31.5% → 39.2%,
sales 34.3% → 50.4% — while the control, getting promoted, barely shifts. **The
industry effect is real.**

*↓ so what is actually left*

**7 · A tie.** Seniority **+0.201** above its band, industry **+0.192**. On the
controlled distance industry leads; on the excess seniority does; the intervals
overlap. **The two orderings disagree, which is better proof that neither is
readable than either of them alone.**

*↓ a tie is not an ending. Take the one this article can follow*

**8 · Inside seniority.** Cloud platforms 4.1% → 22.1%. Architecture 2.7% →
14.7%. **Leadership 0.2% → 10.8%, a factor of forty-eight.** And what falls
away: willingness to learn 14.2% → 2.9%, a bachelor's degree, Excel. **A junior
advert asks what you have learned; a senior advert asks what you can run.**

*↓ true everywhere, or only on average?*

**9 · The same climb.** The same requirements, one column per industry. Every row
keeps its sign in every column: cloud rises between +10 and +24 in all nine,
willingness to learn falls in all nine. Three exceptions worth naming — Excel
survives only in finance, retail is the most relational climb, climate wants the
most cloud.

*↓ and what was all that worth*

**10 · Close.** The two factors that looked strongest were an artefact of how
many adverts there were and of what language they were in. What survived is the
least surprising thing on the list. **The finding is not the ranking; it is how
much of a ranking can be sampling and wording.** Industry ties with seniority,
and this piece does not open it.

### What the shape is doing

Three beats repeat — a number arrives, something is wrong with it, the thing is
removed — and sections 4, 5 and 6 are that shape three times. It is what makes
four corrections read as momentum rather than as an author who cannot settle.

Section 7 breaks it deliberately: nothing is removed and the reader is left with
a draw. **That is where the piece can lose them**, which is why section 8 has to
arrive immediately and be concrete.

Sections 8 and 9 are the only ones that name a skill. Everything before them is
about magnitudes, and a skill appearing earlier is a sentence in the wrong place.

## Figures

Built, from `week 4/articles/build_article1.py`:

| | shows | status |
|---|---|---|
| A | six factors, raw and controlled, over their noise bands | needs the band and the sixth factor |
| B | each country's mixture of languages | built |
| C | raw → English only, per factor | built |
| D | the industry step, pooled and inside one country | built |
| E | advert-weighted against employer-weighted | built |

To build:

| | shows | data |
|---|---|---|
| F | what moves between junior and senior, named | computed; needs drawing |
| G | the seniority effect inside each industry, against each one's floor | computed; needs drawing |

F is the article's payoff and should be the most carefully drawn thing in it.

## Not in this article

Core and shell. ESCO. **Requirements named on the industry axis** — which
industry asks for what is article 2's subject, and this piece points at it
rather than opening it. The sales-versus-software difference as a claim: both
families appear only to show that the ranking is the same in each.

**Requirements named on the seniority axis are this article's own**, and no
sentence about them is writable in article 2.

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

