"""Role-family integrity: is every SALES_BD posting actually business development?

Not in the original procedure, and it needs to be, because it decides what
Hypothesis 1 is a test of. `SALES_BD` as delivered mixes two things that behave
very differently across industries:

* **B2B sales and business development** — account executives, partnerships,
  enterprise sales. What employers ask for here plausibly varies with the
  industry being sold into, which is the hypothesis.
* **Shop-floor retail** — counter staff, cashiers, shelf stackers, market
  traders. What employers ask for here is close to identical wherever it
  happens: availability, customer manner, sometimes a licence.

The second group cannot vary by industry much, because the work is the same work.
Leaving it in *deflates* the sales variance index, and it does so hardest in the
industries where it concentrates — which is exactly where Hypothesis 1 expects
to see a thick shell. So a flat or reversed sales result could be produced by
role-family contamination rather than by any property of sales work, and the two
readings have to be separable.

This module does not decide the question. It measures the group so the decision
can be made and reported, and so the headline estimate can be run both ways.
"""

from __future__ import annotations

import re

import pandas as pd

from . import config

# Titles that name shop-floor or counter work. Matched against `title_norm` and
# the English title, on a leading word boundary only — the trailing-boundary
# trap documented in `classify` applies here too, since these stems inflect and
# compound across seven languages.
SHOP_FLOOR_PATTERNS = {
    "counter_sales": r"\b(?:vendeur|vendeuse|verkaufer|verkauferin|verkoper|verkoopster|"
                     r"commesso|commessa|vendedor|vendedora|shop assistant|"
                     r"sales assistant|store assistant|retail assistant|"
                     r"sales associate|store associate|butiksbitrade)",
    "cashier": r"\b(?:cashier|caissier|caissiere|kassierer|kassiererin|kassa|"
               r"cassiere|cajero|cajera|kassamedewerker)",
    "shelf_stock": r"\b(?:shelf stack|shelf fill|stock clerk|regalauffuller|"
                   r"vakkenvuller|reponeur|reponisseur|mise en rayon|"
                   r"employe libre service|scaffalista|reponedor)",
    "store_manager": r"\b(?:store manager|shop manager|filialleiter|"
                     r"responsable de magasin|chef de rayon|store supervisor|"
                     r"winkelmanager|responsabile di negozio|jefe de tienda)",
    "market_trade": r"\b(?:marche|maree|fruits et legumes|boucher|boulanger|"
                    r"poissonnier|fromager|charcutier|primeur)",
    "telesales": r"\b(?:telesales|tele sales|call center|callcenter|centre d appel|"
                 r"teleconseiller|telefonverkauf)",
}

# Titles that name B2B or business development work, used as the positive
# control. A rule that flags shop-floor roles is only trustworthy if it leaves
# these alone, so both are reported together rather than the flag on its own.
B2B_PATTERNS = {
    "account_exec": r"\b(?:account executive|account manager|key account|"
                    r"kundenbetreuer|gestionnaire de comptes|account director)",
    "business_dev": r"\b(?:business development|bizdev|developpement commercial|"
                    r"geschaftsentwicklung|business developer)",
    "enterprise": r"\b(?:enterprise sales|solution sales|technical sales|"
                  r"pre sales|presales|sales engineer|inside sales)",
    "partnerships": r"\b(?:partnership|alliance|channel manager|reseller)",
    "sales_lead": r"\b(?:sales director|head of sales|vp sales|cro|"
                  r"vertriebsleiter|directeur commercial|sales manager)",
}

_SHOP_RE = {k: re.compile(v, re.I) for k, v in SHOP_FLOOR_PATTERNS.items()}
_B2B_RE = {k: re.compile(v, re.I) for k, v in B2B_PATTERNS.items()}


def _title_text(df: pd.DataFrame) -> pd.Series:
    """The title fields, normalised and concatenated for matching."""
    from . import atomise as atom

    parts = []
    for col in ("title_norm", "job_title_english", "job_title"):
        if col in df.columns:
            parts.append(df[col].fillna("").astype(str))
    if not parts:
        return pd.Series("", index=df.index)
    joined = parts[0]
    for p in parts[1:]:
        joined = joined + " | " + p
    return joined.map(atom.normalise)


def flag_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``shop_floor``, ``b2b`` and ``role_family`` columns.

    ``role_family`` is deliberately three-valued. A posting matching neither
    pattern set is ``unclassified`` rather than being forced into one, because
    the share that cannot be placed by title is itself part of the answer: if it
    is large, the title field cannot settle the scope question and the decision
    needs requirement text or Karimi's own definition.
    """
    out = df.copy()
    text = _title_text(out)

    shop_hits = pd.DataFrame({k: text.str.contains(r, na=False) for k, r in _SHOP_RE.items()})
    b2b_hits = pd.DataFrame({k: text.str.contains(r, na=False) for k, r in _B2B_RE.items()})

    out["shop_floor"] = shop_hits.any(axis=1)
    out["b2b"] = b2b_hits.any(axis=1)
    out["shop_floor_kind"] = shop_hits.idxmax(axis=1).where(out["shop_floor"], "")

    out["role_family"] = "unclassified"
    out.loc[out["b2b"], "role_family"] = "b2b_sales"
    # Shop-floor wins a tie: `store manager` matching both is retail management,
    # not business development, and the whole point is to isolate that group.
    out.loc[out["shop_floor"], "role_family"] = "shop_floor"
    return out


def scope_report(df: pd.DataFrame, function: str = "SALES_BD") -> dict:
    """Size the shop-floor group, overall and where it concentrates."""
    sub = flag_roles(df[df["macro_function"] == function])
    n = len(sub)

    by_industry = (
        sub.groupby("company_industry")["shop_floor"]
        .agg(postings="size", shop_floor="sum")
        .assign(pct=lambda d: (d["shop_floor"] / d["postings"] * 100).round(1))
        .sort_values("pct", ascending=False)
    )

    titles = (
        sub[sub["shop_floor"]]
        .groupby(["title_norm", "company"])
        .size()
        .sort_values(ascending=False)
        .head(10)
        .rename("postings")
        .reset_index()
    )

    # What the cell sizes become if the group is excluded — the practical cost
    # of the decision, since a cell dropping below MIN_CELL_SIZE changes the grid.
    remaining = (
        sub[~sub["shop_floor"]]
        .groupby("company_industry")
        .size()
        .rename("after_exclusion")
    )
    survival = (
        by_industry[["postings"]]
        .join(remaining)
        .fillna(0)
        .astype(int)
        .assign(still_passes=lambda d: d["after_exclusion"] >= config.MIN_CELL_SIZE)
    )

    return {
        "function": function,
        "n": n,
        "n_shop_floor": int(sub["shop_floor"].sum()),
        "pct_shop_floor": round(float(sub["shop_floor"].mean()) * 100, 1),
        "n_b2b": int(sub["b2b"].sum()),
        "pct_b2b": round(float(sub["b2b"].mean()) * 100, 1),
        "pct_unclassified": round(float((sub["role_family"] == "unclassified").mean()) * 100, 1),
        "kinds": sub.loc[sub["shop_floor"], "shop_floor_kind"].value_counts(),
        "by_industry": by_industry,
        "top_titles": titles,
        "cell_survival": survival,
        "detail": sub,
    }
