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
This page uses one slice of that database. The adverts were posted from May to August 2026, for two kinds of role, software and data, and sales and business development, across eleven industries. The chart below shows the distribution of five different factors at once.

## corpus.note
Each circle is one industry. 
**Adverts**: the area is the number of postings, and the count is written beside the circle. Hover a circle for how many companies posted them.
**Senior**: the area is the number of postings looking for a senior role. 
**Hybrid or remote**: the area shows the number of postings as hybrid or remote.
**Companies**: the area represents the concentration of companies per industry.
Note that **Companies** is drawn on its own scale: the first three blocks all count adverts and share one, so a circle there and an equal circle under Companies do not stand for the same number.

## section.01
Industry, country, seniority — which one really changes the job?

## section.02
Which requirements follow the job, and which belong to one industry?



## cta.01
Read the article: two factors looked strongest, for two different reasons →

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
Country looked like the second strongest. It was partly the language.

## chart1.note
Every factor is tested the same way: hold the job family fixed, change only that one thing, and measure how much the list of requirements moves. A longer bar means they move more. The solid part is what survives once every advert is read in the same language; the pale tail is what that takes away. Only country loses anything, which is how you can tell it was the confounded one.

## chart1.x_label
how much the list of requirements changes when this factor changes  →

## chart1.axis_min
0 = the groups ask for exactly the same things

## chart1.axis_max
1 = nothing in common

## chart1.dot_a
what the language was accounting for

## chart1.dot_b
what survives when every advert is read in one language

## chart1.points
- `0.417 → 0.338` Country falls from second to fourth once every advert is read in the same language. Adverts from one country tend to share a language, so part of what looked like a country difference was a difference in the words themselves.
- `−18.9% vs −2.8%` Country lost nearly a fifth of its distance under the control. No other factor moved by more than 2.8%, and company size moved upwards by 1.2% — movement in the wrong direction is what noise looks like, and it sets the scale for reading the others.
- `172 vs 847` What kind of company measures highest, and it is also the factor with the fewest adverts in each group — 172 against 526 to 847 for every other factor. The groups it compares are small enough that the number is the least reliable of the six.

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
- `94 of 555` Asked for at about the same rate whichever industry the job family is in. These follow the job family.
- `137 of 555` Common in one industry, much rarer in the others, and asked for often enough there to matter. About a quarter of the groups.
- `324 of 555 grey` Neither of those. 221 are not tied strongly enough to one industry. 103 are tied to one industry but rarely asked for: MacOS and Apple devices comes up 9.2 times more often in one place, and still in only 2.6% of those adverts. Grey is the usual case.
- `20.3×` Food-industry knowledge, for software roles in Agriculture & Food. 27 different employers ask for it, so it belongs to the industry rather than to one company.
- `1.22×, in 10.1%` Python is mentioned in about one advert in ten, at nearly the same rate in every industry.
