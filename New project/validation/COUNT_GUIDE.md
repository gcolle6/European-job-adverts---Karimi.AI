# Counting requirements: guide for `count_holdout_BLANK.csv`

Fill `n_requirements` for each row: **how many separate requirements this item
holds**. Read `item` (as the employer wrote it); `item_english` is only a help.
Do not look at what the splitter produced, and do not open the code.

Save the filled file as `count_holdout_LABELLED.csv`.

## The rules

| The item says | Count | Why |
|---|---|---|
| `Experience with AWS, Azure or GCP` | 3 | one per item in a list |
| `Analytical and problem-solving skills` | 2 | two skills share one noun |
| `Bachelor's or Master's in Computer Science or Mathematics` | 4 | alternatives multiply: 2 degrees × 2 fields |
| `Experience building and maintaining CI/CD pipelines` | 1 | verbs sharing one object are one demand |
| `Excellent written and verbal communication` | 1 | modes of one skill |
| `Fluent German and English` | 2 | one per language |
| `Scripting languages such as Python or Bash` | 2 | generic category, only the examples count |
| `ERP systems such as SAP or Oracle` | 3 | the category is a real concept, so it counts too |
| `Experience with Kubernetes, ideally on AWS` | 1 | `ideally`, `preferably`, `is a plus` qualify, they do not add |
| `Degree in Computer Science or a related field` | 1 | `or similar`, `or related field` add nothing |
| `Degree in Computer Science or equivalent experience` | 2 | equivalent experience is a real alternative route |
| `Strong communication skills and openness to feedback` | 2 | two complete requirements |

## When unsure

Write your best count and put `x` in `unsure`. Use it whenever you hesitate:
a hard case marked `unsure` is information; a hard case without it looks like a
mistake.

`note` is free text.
