# Page copy

Every word a reader sees on the published page. Nothing here is computed, and
nothing outside here is text: if you want to change what the page says, this is
the only file to open.

You do not run this file. You write it, then rebuild:

    python "week 4/build_chart_data.py"      # only if you edited a bullet figure
    python "week 4/build_public.py"          # always — this writes docs/index.html

Each `## key` below is a slot the page fills. Keep the keys, change the words.
An empty slot disappears from the page rather than printing blank, so deleting a
paragraph is a way of removing it.

Three slot shapes:

* **plain** — one paragraph. `**bold**` and `` `code` `` work; nothing else does.
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
Software piles into one industry. Sales does not.

## corpus.note
Each circle is one industry. The area is the number of postings among the 28,487 adverts as delivered, and the count is written beside the circle. Hover a circle for how many companies posted them. The last row has no industry.

## corpus.points
- `5,663` Software postings in AI, Data & Software, the largest cell. Sales in that industry is 1,535, less than a third as many.
- `1,854 vs 477` Commerce & Retail runs the other way. Sales postings there outnumber software ones by about four to one.
- `554` Postings with no industry: 359 software and 195 sales. They are drawn last, and they are not one of the eleven industries compared below.

## section.01
Industry, country, seniority — which one really changes the job?

## section.02
What travels with you between industries, and what stays behind?

## section.03
Europe keeps an official list of workplace skills. Is what employers ask for on it?

## section.04
Which employers repeat themselves?

## cta.01
Read the article: why the raw table said country, and why it was wrong →

## cta.02
Read the article: the seven things that travel, and the twenty-times demands →

## cta.03
Read the article: what the European skills catalogue misses, and why →

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
Every factor is tested the same way: hold the job fixed, change only that one thing, and measure how much the list of requirements moves. Further right means it moves more. The pale dot is the first measurement. The solid dot is the same measurement after removing the effect of the language the advert happens to be written in — adverts from one country tend to share a language, so an untreated country comparison is partly just a comparison of languages. Only country moves when that is taken out, which is how you can tell it was the confounded one.

## chart1.x_label
how much the list of requirements changes when this factor changes  →

## chart1.dot_a
what we first measured

## chart1.dot_b
after removing the language effect

## chart1.points
- `0.422 → 0.342` Country was the largest factor before the language control and the fourth after it. Adverts from one country tend to share a language, so part of what looked like a country difference was a difference in the words themselves.
- `−18.9% vs −2.6%` Country lost nearly a fifth of its distance under the control. No other factor moved by more than 2.6%, and company size moved upwards by 1.2% — movement in the wrong direction is what noise looks like, and it sets the scale for reading the others.
- `0.373 vs 0.372` Seniority and industry finish level once language is removed. The gap between them is smaller than either confidence interval, so the honest reading is a tie rather than a winner.
- `3 levels each` Every factor is compared across three of its levels, chosen for having enough adverts on each side in both job families and in the English subset. A factor with more levels could rank differently across all of them.

---

# Chart 2 — core and shell

## chart2.title
Most of what you know travels. A few things belong to one industry.

## chart2.note
Every dot is one requirement group, placed where employers ask for it most. Across: how much more often it is asked there than in the same job elsewhere — 1× means no more often anywhere, 20× means twenty times more. Up: how many of that cell's adverts ask for it at all. Both matter, because a requirement that is distinctive but almost never asked for is not a finding. The two tinted regions are the rules: blue for core, orange for shell. Grey dots fell inside neither, and they are the majority. Hover any dot.

## chart2.x_label
asked for how much more often here than in the same job elsewhere  →

## chart2.y_label
↑  share of that cell's adverts asking for it

## chart2.points
- `91 of 580` Requirement groups sit close to 1×: asked at roughly the same rate whichever industry the job is in. This is the core — what you can take with you.
- `149 of 580` Groups are concentrated in a single industry cell and asked for often enough there to count. This is the shell, and it is about a quarter of the groups rather than the bulk of them.
- `340 of 580 grey` Most groups clear neither bar. 263 are not distinctive enough to be shell, and 77 are distinctive but too rare — `MacOS and Apple devices` peaks at 9.2× and still appears in only 2.6% of that cell's adverts. Grey is not a leftover category; it is the ordinary case.
- `20.3×` Food industry knowledge, in software roles in Agriculture & Food. It is spread across 27 different employers, so it is a property of the industry rather than one company's house style.
- `1.22×, in 10.1%` Python proficiency is asked for in a tenth of all adverts and barely varies by industry. The most common technical requirement is also one of the most portable.

---

# Chart 3 — the catalogue residual

## chart3.title
About a quarter is not — and the two jobs fall off the list for different reasons

## chart3.note
ESCO is the European Union's official classification of skills and occupations: the reference list used to compare jobs across countries. Each bar is one job family's requirements that match no concept in it, split by why they do not. Software falls off through novelty — it names things the list has not caught up with. Sales falls off through vagueness — it names nothing specific enough to match. 'No reason assigned' is the largest piece of both, and part of it is our own grouping rather than a gap in the catalogue.

## chart3.points
- `27.5% and 24.0%` Share of each job family's requirements that match no concept in ESCO, the European Union's official list of skills and occupations. The two families are close in size, and different in reason.
- `5.8% vs 3.1%` Software falls off the list through novelty nearly twice as often as sales: it names tools and practices the catalogue has not caught up with.
- `6.1% vs 3.9%` Sales falls off through vagueness more than software: the requirement names nothing specific enough for any concept to match it.
- `12.7%` The largest single piece of software's residual has no reason assigned at all. Some of that is the catalogue and some is our own grouping, and this chart cannot separate the two.

---

# Chart 4 — employers and repetition

## chart4.title
Posting a lot is not the same as posting the same thing

## chart4.note
Each dot is one employer that posted 20 adverts or more. Higher up means that employer keeps re-posting the same advert: 1.0 would mean every one of its adverts asks for exactly the same things. The dashed line is how alike two adverts from DIFFERENT employers usually are — so anything near it is writing genuinely different adverts.

## chart4.x_label
how many adverts this employer posted  →

## chart4.y_label
how alike its own adverts are to each other  ↑

## chart4.points
- `311 employers` Every employer that posted 20 adverts or more. Below that the self-similarity measure is too unstable to read.
- `975 adverts, 1.5×` The largest poster in the corpus writes adverts barely more alike than two adverts from different companies. Posting a great deal is not, by itself, evidence of a template.
- `86 adverts, 54×` A much smaller poster repeats itself almost exactly. This is the case the counting rule has to handle, and it is not the one volume would have pointed at.
- `33 of 311` Employers sit above ten times the control line. Heavy repetition is a minority behaviour, which is why collapsing repeats changes the corpus size by 17% and not by half.
