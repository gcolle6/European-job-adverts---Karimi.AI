"""THE TEXT UNDER EACH CHART. This file is prose, not analysis.

Every bullet that appears beneath a chart on the published page lives here, and
nothing here is computed. Rewrite freely: change wording, reorder, add or delete
bullets, and rebuild with

    python "week 4/build_chart_data.py"
    python "week 4/build_public.py"

Each bullet is a pair. ``stat`` is a figure, shown in a monospace chip, and it
should be short enough to read at a glance — a number, a ratio, a count, an
arrow between two numbers. ``text`` says what that figure means, in one or two
sentences. The figure comes first because a reader scanning the page should be
able to take the numbers alone and still get the argument.

The figures in ``stat`` are typed by hand rather than computed, so that this
file stays readable as text. ``build_chart_data.py`` re-derives the ones it can
and prints a warning if any of them has drifted from the data — if you see that
warning, the chart moved and the sentence beside it needs rereading, not just
the number.

These are drafts. They state what the data shows, plainly, and they are meant to
be replaced with your own wording rather than kept.
"""

POINTS = {
    # ---------------------------------------------------------------- 01 ---
    "chart1_drivers": [
        {"stat": "0.422 → 0.342",
         "text": "Country was the largest factor before the language control and the "
                 "fourth after it. Adverts from one country tend to share a language, so "
                 "part of what looked like a country difference was a difference in the "
                 "words themselves."},
        {"stat": "−18.9% vs −2.6%",
         "text": "Country lost nearly a fifth of its distance under the control. No other "
                 "factor moved by more than 2.6%, and company size moved upwards by 1.2% "
                 "— movement in the wrong direction is what noise looks like, and it "
                 "sets the scale for reading the others."},
        {"stat": "0.373 vs 0.372",
         "text": "Seniority and industry finish level once language is removed. The gap "
                 "between them is smaller than either confidence interval, so the honest "
                 "reading is a tie rather than a winner."},
        {"stat": "3 levels each",
         "text": "Every factor is compared across three of its levels, chosen for having "
                 "enough adverts on each side in both job families and in the English "
                 "subset. A factor with more levels could rank differently across all of "
                 "them."},
    ],

    # ---------------------------------------------------------------- 02 ---
    "chart2_core_shell": [
        {"stat": "91 of 580",
         "text": "Requirement groups sit close to 1×: asked at roughly the same rate "
                 "whichever industry the job is in. This is the core — what you can "
                 "take with you."},
        {"stat": "149 of 580",
         "text": "Groups are concentrated in a single industry cell. This is the shell, "
                 "and it is about a quarter of the groups rather than the bulk of them."},
        {"stat": "20.3×",
         "text": "Food industry knowledge, in software roles in Agriculture & Food. It is "
                 "spread across 27 different employers, so it is a property of the "
                 "industry rather than one company's house style."},
        {"stat": "1.22×, in 10.1%",
         "text": "Python proficiency is asked for in a tenth of all adverts and barely "
                 "varies by industry. The most common technical requirement is also one "
                 "of the most portable."},
    ],

    # ---------------------------------------------------------------- 03 ---
    "chart3_residual": [
        {"stat": "27.5% and 24.0%",
         "text": "Share of each job family's requirements that match no concept in ESCO, "
                 "the European Union's official list of skills and occupations. The two "
                 "families are close in size, and different in reason."},
        {"stat": "5.8% vs 3.1%",
         "text": "Software falls off the list through novelty nearly twice as often as "
                 "sales: it names tools and practices the catalogue has not caught up "
                 "with."},
        {"stat": "6.1% vs 3.9%",
         "text": "Sales falls off through vagueness more than software: the requirement "
                 "names nothing specific enough for any concept to match it."},
        {"stat": "12.7%",
         "text": "The largest single piece of software's residual has no reason assigned "
                 "at all. Some of that is the catalogue and some is our own grouping, and "
                 "this chart cannot separate the two."},
    ],

    # ---------------------------------------------------------------- 04 ---
    "chart4_employers": [
        {"stat": "311 employers",
         "text": "Every employer that posted 20 adverts or more. Below that the "
                 "self-similarity measure is too unstable to read."},
        {"stat": "975 adverts, 1.5×",
         "text": "The largest poster in the corpus writes adverts barely more alike than "
                 "two adverts from different companies. Posting a great deal is not, by "
                 "itself, evidence of a template."},
        {"stat": "86 adverts, 54×",
         "text": "A much smaller poster repeats itself almost exactly. This is the case "
                 "the counting rule has to handle, and it is not the one volume would "
                 "have pointed at."},
        {"stat": "33 of 311",
         "text": "Employers sit above ten times the control line. Heavy repetition is a "
                 "minority behaviour, which is why collapsing repeats changes the corpus "
                 "size by 17% and not by half."},
    ],
}

# Figures that can be re-derived from the built datasets, so a chart that moves
# does not leave a stale number sitting under it. Each entry names the chart, the
# bullet's position, and a function from that chart's data to the string that
# should appear. Only the mechanical ones are listed — a sentence still has to be
# read by a person.
def _c1(d):
    r = {x["factor"]: x for x in d["rows"]}
    c = r["Which country"]
    return f"{c['raw']:.3f} → {c['controlled']:.3f}"


def _c2_core(d):
    return f"{sum(1 for g in d['groups'] if g['kind'] == 'core')} of {len(d['groups'])}"


def _c2_shell(d):
    return f"{sum(1 for g in d['groups'] if g['kind'] == 'shell')} of {len(d['groups'])}"


def _c3_shares(d):
    a, b = [f["residual_share"] for f in d["families"]]
    return f"{a*100:.1f}% and {b*100:.1f}%"


def _c4_count(d):
    return f"{len(d['employers'])} employers"


CHECKS = {
    "chart1_drivers": {0: _c1},
    "chart2_core_shell": {0: _c2_core, 1: _c2_shell},
    "chart3_residual": {0: _c3_shares},
    "chart4_employers": {0: _c4_count},
}
