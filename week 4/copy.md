# Page copy

Every word a reader sees on the published page. Nothing here is computed, and
nothing outside here is text: if you want to change what the page says, this is
the only file to open.

You do not run this file. You write it, then rebuild:

    python "week 4/build_chart_data.py"      # if you edited any chart title, note, label or bullet
    python "week 4/build_public.py"          # always — this writes docs/index.html

Each `## key` below is a slot the page fills. Keep the keys, change the words.
An empty slot disappears from the page rather than printing blank, so deleting a
paragraph is a way of removing it.

Three slot shapes:

* **plain** — one paragraph. `**bold**`, `` `code` ``, and `[label](https://url)` work.
* **steps** — a list of `- **lead** trailing text`, used by the method strip.
* **points** — a list of `` - `figure` text``, used under each chart. The figure
  is shown in a chip, the text beside it. The figure comes first on purpose: a
  reader scanning the page should be able to take the numbers alone and still
  follow the argument.

Figures typed here are checked at build time against the data wherever they can
be re-derived. A mismatch prints a warning naming the bullet — when that happens
the sentence beside the number usually needs rereading too, not just the number.

---

## masthead.kicker
Giacomo Collesei & Karimi.AI · published September 2026 · 25,800 European job adverts posted May–August 2026

## masthead.title
What different employers ask, when hiring for the same job

## masthead.dek
Which requirements follow the job, and which follow the industry? An analysis of software and sales roles, each posted across eleven industries.

## method.title
How the methodology works

## method.steps
- **Requirement text → 349,061 single requirements.** I split the requirements into single strings, at times splitting one sentence into multiple in order to be as specific as possible.
- **Each requirement → 384 numbers.** I represented semantically the single requirements: `Kenntnisse in SQL` and `SQL knowledge` have similar values.
- **Numbers → 594 groups.** Semantic representations are here grouped into clusters.
- **Groups → core and shell.** I compared a group's share in one cell against the job family's own baseline.

# The corpus

## corpus.title
An intro to the job postings

## corpus.intro
[Karimi](https://www.karimi.ai) builds a database of European companies and the jobs they advertise, taken from public listings on company pages. It holds more than 5,600 companies and hundreds of thousands of postings.

## corpus.more
This page uses one slice of that database. The adverts were posted from May to August 2026, for two kinds of role, software and data, and sales and business development, across eleven industries. The chart below shows the distirbution of five different factors at once.

## corpus.note
Each circle is one industry. 
**Averts**: the area is the number of postings, and the count is written beside the circle. Hover a circle for how many companies posted them.
**Senior**: the area is the number of postings looking for a senior role. 
**Hybrid or remote**: the area shows the number of postings as hybrid or remote.
**Companies**: the area represent the concentration of companies per industry.
Note that **Companies** is drawn on its own scale: the first three blocks all count adverts and share one, so a circle there and an equal circle under Companies do not stand for the same number.

## section.01
Industry, country, seniority — which one really changes the job?

## section.02
Which requirements follow the job, and which belong to one industry?



## cta.01
Read the article: why the raw table said country, and why it was wrong →

## cta.02
Read the article: what follows the job, and what is asked for twenty times more often →


## limits.title
What these numbers will not carry

## limits.items
- These are **advertised** requirements, not the labour market. Posted is not the same as existing, and large employers are over-represented by construction.
- Extraction finds about **80%** of requirements, and misses them unevenly. Every figure here is a **share of adverts**, never a count of requirements per advert.
- One requirement type — domain knowledge — is correctly identified **27%** of the time. Any claim resting on it carries that number.
- **A third of the uncatalogued demand has no reason assigned**, and part of it is our own grouping rather than a gap in the catalogue.
- Every magnitude is a **range**. The consistent shape of these results is a stable direction over an unstable size.

## foot
Every figure regenerates from the analysis scripts. Twenty-five known defects are tracked with their measured sizes; none of them moves a headline, which is the most persuasive thing this study can say.

## credits.author.label
Written by

## credits.author.name
Giacomo Collesei

## credits.author.text
Analysis, code and write-up. Every figure here regenerates from the scripts, and the known defects are published with their measured sizes rather than left for a reader to find.

## credits.author.link
Read the code → https://github.com/gcolle6/European-job-adverts---Karimi.AI

## credits.data.label
Data from

## credits.data.name
Karimi

## credits.data.text
The app to boost your career 🥕 Become the best at your job 🥕 Get great opportunities 🥕 Grow your network

## credits.data.link
karimi.ai → https://www.karimi.ai/

---

# Chart 1 — what changes the job

## chart1.title
Country looked like the strongest — until the advert's language was taken out

## chart1.note
Every factor is tested the same way: hold the job family fixed, change only that one thing, and measure how much the list of requirements moves. Further right means it moves more. The pale dot is the first measurement. The solid dot is the same measurement after removing the effect of the language the advert happens to be written in — adverts from one country tend to share a language, so an untreated country comparison is partly just a comparison of languages. Only country moves when that is taken out, which is how you can tell it was the confounded one.

## chart1.x_label
how much the list of requirements changes when this factor changes  →

## chart1.noise_label
difference you get by chance alone

## chart1.noise_explain
**What the grey band is.** Take these same adverts and sort them into groups at random, then compare what each group asks for. The band shows how much difference shows up. It is wider where the groups are smaller, because smaller groups differ more by luck. So a dot sitting inside its own band could be luck.

**Why one factor is inside its band.** Every group is cut down to the size of the smallest one being compared, so that no group looks distinctive just for being small. For what kind of company the smallest is small and medium businesses hiring in sales, in English: 172 adverts, where every other factor's smallest holds 604 to 847. At 172, luck alone gives 0.342 and the factor measured 0.329. So the chart is not saying the kind of company makes no difference, while it is saying that these adverts cannot tell.

## chart1.axis_min
0 = the groups ask for exactly the same things

## chart1.axis_max
1 = nothing in common

## chart1.dot_a
what we first measured

## chart1.dot_b
after removing the language effect

## chart1.points
- `0.422 → 0.342` Country was the largest factor before the language control and the third after it. Adverts from one country tend to share a language, so part of what looked like a country difference was a difference in the words themselves.
- `−18.9% vs −2.6%` Country lost nearly a fifth of its distance under the control. No other factor moved by more than 2.6%, and company size moved upwards by 1.2% — movement in the wrong direction is what noise looks like, and it sets the scale for reading the others.
- `0.373 vs 0.372` Seniority and industry finish level once language is removed. The gap between them is smaller than either confidence interval, so the honest reading is a tie rather than a winner.
- `172 adverts` The one thing this chart cannot answer. What kind of company is compared on groups of 172, against 604 to 847 for every other factor, and at that size luck alone already produces more difference than the factor did.

---

# Chart 2 — core and shell

## chart2.title
Most requirements are asked for at a similar rate everywhere. A few belong to one industry.

## chart2.note
Each dot is a group of requirements that mean the same thing, shown in the industry where employers ask for it most. Left to right: how much more often they ask for it there than in the same job in other industries. 1× means the same rate everywhere. 20× means twenty times more often in that one industry. Bottom to top: how many of that industry's adverts mention it. Both matter, because a requirement can be typical of one industry and still almost never asked for. Blue means a similar rate in every industry. Orange means common in one industry and uncommon in the others. Grey is neither, and grey is most of the chart. Hover a dot to see which requirement it is.

## chart2.x_label
how much more often it is asked for in this industry than in others  →

## chart2.y_label
how many of that industry's adverts ask for it

## chart2.points
- `91 of 580` Asked for at about the same rate whichever industry the job family is in. These follow the job family.
- `149 of 580` Common in one industry, much rarer in the others, and asked for often enough there to matter. About a quarter of the groups.
- `340 of 580 grey` Neither of those. 263 are not tied strongly enough to one industry. 77 are tied to one industry but rarely asked for: MacOS and Apple devices comes up 9.2 times more often in one place, and still in only 2.6% of those adverts. Grey is the usual case.
- `20.3×` Food-industry knowledge, for software roles in Agriculture & Food. 27 different employers ask for it, so it belongs to the industry rather than to one company.
- `1.22×, in 10.1%` Python is mentioned in about one advert in ten, at nearly the same rate in every industry.
