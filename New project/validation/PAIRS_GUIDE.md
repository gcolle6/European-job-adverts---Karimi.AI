# Same or different? Guide for `pairs_BLANK.csv`

60 pairs, about 15 minutes. For each row write in `same`:

* `y` — **the same thing**: an employer asking for `a` and one asking for `b` want the same;
* `n` — **different things**.

Judge `a` against `b`. The `_example` columns show one real posting each, only
for context. Do not open `pairs_KEY.csv` and do not look at the code.

Save the filled file as `pairs_LABELLED.csv`.

## Requirements (`kind = requirement`)

`context` is the frame already taken out (`experience`, `competence`,
`ability`). Judge only what is asked for.

| Ignore | because it already sits in its own column |
|---|---|
| years (`3+ years`, `Minimum 9 years`) | `req_years_*` |
| level (`Basic`, `Solid`, `Excellent`, `Fluency`) | `req_level` |
| spelling, plural, apostrophes, `visualisation` / `visualization` | not a different demand |

| `a` | `b` | `same` | why |
|---|---|---|---|
| `Git` | `Git version control` | y | the same tool |
| `SQL` | `PostgreSQL` | n | one is a specific product |
| `cloud platforms` | `Azure cloud platforms` | n | narrower: not every cloud experience is Azure |

## Roles (`kind = role`)

| Ignore | because it already sits in its own column |
|---|---|
| seniority (`Senior`, `Lead`, `Junior`) | `title_level` |
| location, team, technology in brackets or after a dash | `title_extra` |
| language of the example (`Systemutvecklare` = System Developer) | already translated |

Ask: **would a candidate for `a` also apply to `b`, and would the employer ask for
the same things?** `Backend Engineer` / `Frontend Engineer` → n.

## When unsure

Give your best answer and put `x` in `unsure`. A hard case marked `unsure` is
information; without the mark it looks like a mistake.
