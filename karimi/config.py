"""Project-wide constants.

Every threshold and exclusion used in the analysis is declared here rather than
inline, so that a reader can see the committed parameters in one place and a
sensitivity run can vary them without touching analysis code.
"""

from pathlib import Path

# --- paths -------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "wetransfer_karimi-jobs_2026-08-25_1346"

SOURCE_FILES = {
    "SOFTWARE_DATA": DATA_DIR / "europe_jobs_SOFTWARE_DATA.json",
    "SALES_BD": DATA_DIR / "europe_jobs_SALES_BD.json",
}

# --- analytical grid ---------------------------------------------------------

# Ten industries carried into the analysis. Committed before inspecting the data.
GRID_INDUSTRIES = [
    "AI, Data & Software",
    "Financial Services",
    "Industrial & Deep Tech",
    "Enterprise, Legal & Work",
    "Mobility & Transport",
    "Climate & Energy",
    "Consumer, Lifestyle & Hospitality",
    "Health & Life Sciences",
    "Commerce & Retail",
    "Agriculture & Food",
]

# Industries admitted after the pre-commitment, once it was clear that naming an
# industry for exclusion duplicated work `MIN_CELL_SIZE` already does. Think Tank
# & Research carries 459 software and 80 sales postings on the analysis base, so
# the threshold rule admits the software cell and rejects the sales one without
# anyone deciding it by hand. Kept separate from GRID_INDUSTRIES so the
# pre-committed grid stays legible as what was committed. Changed 2026-09-03.
ADDITIONAL_INDUSTRIES = ["Think Tank & Research"]

ALL_INDUSTRIES = GRID_INDUSTRIES + ADDITIONAL_INDUSTRIES

# No industry is excluded by name any more; MIN_CELL_SIZE decides.
EXCLUDED_INDUSTRIES: list[str] = []

FUNCTIONS = ["SOFTWARE_DATA", "SALES_BD"]

# Minimum postings for a (function, industry) cell to enter the primary analysis.
# Pre-committed. Applied after the exclusion chain, not before.
MIN_CELL_SIZE = 300

# Hypothesis 1 compares a variance index BETWEEN the two functions across
# industries. That comparison is only meaningful over industries where both
# functions clear MIN_CELL_SIZE, so paired estimates run on GRID_INDUSTRIES while
# descriptive and core/shell tables may use every cell that clears the threshold.
PAIRED_INDUSTRIES = GRID_INDUSTRIES

# Flag a cell when one employer supplies at least this share of it.
EMPLOYER_CONCENTRATION_FLAG = 0.10

# --- repeat postings ---------------------------------------------------------

# Fields that must ALL match for two rows to count as the same advertisement.
#
# `must_have` is part of the key deliberately. Keying on company/title/city
# alone collapsed 2,360 rows, but only 6.6% of those groups were identical on
# their content fields: the requirement text differed in 67% of them, seniority
# in 10%, work type in 16%. Two ads for the same title with different stated
# requirements are two observations, not one, and the requirement profile is the
# unit this study measures.
#
# `geo_country` is included because `geo_city` is empty for ~13% of postings,
# and an empty city collapses unrelated postings across different countries —
# seven EverAI security-engineer roles in seven countries became one.
#
# `role_summary` is deliberately NOT in the key: it is a generated summary that
# varies in wording between otherwise identical ads (it differs in 85% of
# candidate groups), so including it would prevent almost all collapsing.
REPEAT_POSTING_KEY = ["company", "title_norm", "geo_country", "geo_city", "must_have"]

# Whether rows identical on that key leave the analysis base at all.
#
# They no longer do. `job_id` is distinct in all 659 repeat groups, so these are
# separate source records rather than one advertisement ingested twice, and an
# employer advertising the same role several times is itself demand signal.
#
# But the rule is not free either way, so it is a parameter rather than a
# decision. Group sizes reach 41, 34 and 30 — the two heaviest repeat advertisers
# supply 124 and 80 rows — and 292 of 659 groups are same-day, which reads as
# one template posted many times rather than a role re-advertised. Since the unit
# measured is the requirement profile, leaving those in unweighted gives one
# template up to 41x weight inside its cell and deflates within-cell variance,
# which is the quantity Hypothesis 1 turns on.
#
# So the base keeps them and carries `repeat_group_size`: counting questions use
# the rows, requirement-profile questions weight by 1/repeat_group_size. Set this
# True to reproduce the Week 1 collapsed base. Changed 2026-09-03.
COLLAPSE_REPEAT_POSTINGS = False

# Whether a posting must carry `must_have` text to enter the base.
#
# Still True, and not for want of reconsidering it. `must_have` is exactly empty
# in all 1,934 dropped rows and the export carries no other requirement field, so
# these postings contribute zero atoms: keeping them would move the posting
# denominator and nothing else, and would change no cell's pass/fail status.
# They become recoverable only by mining `role_summary`, which is abstractive —
# requirements read out of it are the summariser's vocabulary, not the
# employer's, and that lands directly on the Hypothesis 2 residual. Revisit once
# the LLM extractor can be run on `role_summary` for both this group and the
# control, and compare yield.
REQUIRE_MUST_HAVE = True

# --- role-family scope -------------------------------------------------------

# Whether shop-floor retail roles are flagged on the analysis base.
#
# Karimi's decision, 2026-09-03: run the analysis BOTH ways and compare, rather
# than settle the scope question first. So nothing is excluded — the base
# carries `shop_floor` and `role_family` and every headline estimate is reported
# on all of SALES_BD and on B2B only, exactly as employer weighting is reported
# weighted and unweighted.
#
# This is not a neutral robustness check and should not be presented as one.
# Shop-floor work is 10.1% of SALES_BD but 53.0% of Commerce & Retail / SALES_BD,
# so it is concentrated in one cell rather than spread across the grid. A group
# that sits inside a single industry makes that industry look distinctive, which
# INFLATES a between-industry variance index — so including it pushes the sales
# result in the direction Hypothesis 1 predicts. If the two runs disagree, the
# B2B-only run is the conservative one and the difference is the finding.
FLAG_SHOP_FLOOR = True

# --- requirement processing --------------------------------------------------

REQUIREMENT_TYPES = [
    "technical",
    "soft",
    "domain",
    "credential",
    "language",
    "availability",
]

# A segment longer than this is unlikely to be a single requirement.
LONG_SEGMENT_CHARS = 120

# --- embedding classification ------------------------------------------------

# Abstention thresholds for the prototype classifier. A phrase whose nearest
# type centroid is this weak, or which sits this close to two centroids at once,
# is left unassigned and routed onward rather than guessed at. Tuned on the
# development half of the labelled sample; the gate is read off the held-out
# half, which these never saw.
EMBED_MIN_SIMILARITY = 0.20
EMBED_MIN_MARGIN = 0.02

# --- gate thresholds ---------------------------------------------------------

GATE_ATOM_PRECISION = 0.90
GATE_ATOM_RECALL = 0.75
GATE_CLASS_ACCURACY = 0.85

# Minimum share of items a classifier must actually answer for its accuracy to
# count. Added 2026-09-03 because the criterion above is gameable without it:
# `accuracy_on_assigned` rises whenever a classifier abstains more, and the
# lexicon cleared 0.85 while declining 53% of the sample. Accuracy on a tenth of
# the corpus says nothing about the corpus. Set at the level a usable classifier
# has to reach, not at what the current one happens to score.
GATE_CLASS_MIN_COVERAGE = 0.80

# Requirement types whose definition was NOT revised on 2026-09-03, and whose
# round 1 labels therefore remain valid. `domain` is excluded: the boundary moved
# (the object decides the type, and commercial practice became domain), so those
# 31 labels describe a superseded specification and scoring against them measures
# the change rather than the classifier. Checked, not assumed — 0 of 42
# `technical` labels are affected.
DEFINITION_STABLE_TYPES = ("technical", "soft", "credential", "language", "availability")

# Chunk-shape guards for the atomiser: a comma-separated run counts as a list
# only if its chunks look like terms rather than clauses.
MAX_ITEM_CHARS = 45
MAX_ITEM_WORDS = 5
MAX_ITEM_MEAN_CHARS = 38
MAX_HEAD_CHARS = 70

# How many chunks in a run may exceed the per-item caps before the run stops
# looking like a list. A real list often ends in a longer trailing item, and
# requiring every chunk to be short rejected the whole run for one such tail.
MAX_LONG_ITEMS = 1

# A head longer than this is not searched for alternatives. `Bachelor's or
# Master's Degree in` should expand to two heads; a long clause containing an
# incidental `or` should not.
MAX_HEAD_ALT_WORDS = 6

# In a bare coordinated run, trailing chunks no longer than this are read as
# terms sharing the first chunk's head (`... under KPIs and deadlines`). Above
# it they are read as independent clauses and left alone.
MAX_BARE_TAIL_WORDS = 3

# How many times the splitter is applied to its own output.
#
# Set to 1: recursion was tried on 2026-09-03 and **measured worse**. Dev
# precision fell 0.840 -> 0.806 and holdout 0.687 -> 0.671, for +0.004 recall.
# The second pass shreds the first pass's output — `Experience designing and
# operating ETL pipelines using Airflow` becomes `Experience designing` plus
# `operating ETL pipelines using Airflow`, duplicated once per tool. Nesting is
# real, but a splitter with no notion of what it already consumed cannot exploit
# it. Kept as a parameter so the negative result is reproducible.
ATOMISE_MAX_PASSES = 1

# Whether a run of modifiers is split by copying the noun at its end onto each
# of them (`Eigenverantwortliches, engagiertes und kundenorientiertes Arbeiten`
# -> three requirements), or left whole.
#
# Karimi's suggestion 2026-09-03, and the reasoning is right: these chunks have
# no repeatable head but they do share a tail. Measured off: dev F1 moved 0.745
# -> 0.747 and holdout recall 0.556 -> 0.565, inside noise, while the output on
# the cases it fires on is visibly wrong (`structured goal-oriented`) and it
# never fires on the German case it was meant for.
#
# The blocker is not the mechanism, it is telling an adjective from a noun in
# six languages. `ADJECTIVAL_RE` uses English suffixes, so it misses German
# inflection (`Eigenverantwortliches`) and over-fires elsewhere.
#
# That was then tested properly. Taggers for all six languages were installed
# and `atomise_parse.atomise_pos` implements the rule with real POS tags — and
# it works on the cases it was built for: `Selbststaendige und strukturierte
# Arbeitsweise` becomes two complete requirements. But it moves **no gate
# metric at all** (dev and holdout precision/recall/F1 identical to three
# decimals), because the pattern is too rare in the labelled sample. On the
# corpus it cuts one-word orphans from 3.83% to 3.54% of atoms.
#
# Conclusion: correct, cheap, and immaterial. Left available rather than wired
# into the default path, since six model dependencies for 0.3pp of orphan rate
# is not a trade worth making by default. Enable it for output quality if the
# atoms are being read by a human, not to move the gate.
DISTRIBUTE_SHARED_TAIL = False

# Use `atomise_parse.atomise_pos` in place of the plain regex splitter. Requires
# the spaCy models listed in `atomise_parse.TAGGERS`. See the note above for why
# this is off: measured correct but with no effect on any gate figure.
USE_POS_MODIFIER_SPLIT = False

# An unsplit segment longer than this is routed to the LLM stage even with no
# other signal. Well below LONG_SEGMENT_CHARS on purpose: the routing decision
# is far cheaper to get wrong than the splitting decision, so it is tuned for
# recall. See the note in `atomise.needs_llm` for the four rules compared.
LLM_ROUTE_MIN_CHARS = 60

# Expand a bracket holding two or more comma-separated items into one
# requirement per item, distributing the head. A bracket holding ONE example
# stays attached, so `version control (such as Git)` is still one requirement.
#
# ON, and it is the only change that has moved long-segment extraction since
# the LLM pass. Parenthetical lists were the worst-recovering shape in the
# labelled long segments — 8% against 55% overall — because `PAREN_RE` masks
# brackets so their commas cannot drive a split. Switching this on lifts them
# to 28% and overall long-segment recovery from 55.4% to 57.1%, with no other
# shape degrading.
#
# ⚠️ It also exposes a conflict between the two label sets, and the number you
# get depends on which one you score against:
#
#   * round 1 (independent labeller, original guide): brackets stay attached.
#     Against those labels this costs ~2.4pp precision for ~0.9pp recall —
#     holdout 0.687/0.556 becomes 0.664/0.565.
#   * Karimi's 2026-09-04 re-label: multi-item brackets expand. Against those
#     it recovers 5 more requirements of 303.
#
# The rule implemented here reconciles them in principle — one example stays, a
# list expands — and `(Boomi, MuleSoft, Talend)` really does name three tools an
# employer will accept, each a separate demand signal, which is what this study
# measures. But the precision cost falls against the *independent* labels, and
# they are the ones that count for validation. **The parenthetical convention
# needs one line from the independent labeller**; it is worth 25 requirements
# of the sample.
#
# SETTLED by Karimi 2026-09-06: split the bracket and append every item to the
# head outside it, which is what this implements. Round 1's contrary reading is
# superseded; the precision cost against those labels is reported as such.
EXPAND_PAREN_LISTS = True
