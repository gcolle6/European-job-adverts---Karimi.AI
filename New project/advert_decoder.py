"""The advert decoder: the normalisation layer turned into something a user holds.

A candidate reading a job advert cannot tell which requirements are the job and
which are this employer's wish list. Every line looks equally mandatory. The
normalisation layer can answer that, because once a requirement is mapped to a
group, it can be looked up against every other advert for the same role:

    "Kubernetes"            -> asked in 41% of software engineer adverts: STANDARD
    "Experience with Kafka" -> asked in 4%: UNUSUAL - this employer's specific ask
    "Fluent Dutch"          -> no group at all: NO GROUP

and the reverse, which no advert shows: what comparable adverts usually ask for
that this one does not mention.

It runs on the existing pipeline unchanged - `atomise.segments` and `atomise`,
`atomise.normalise`, the local MiniLM model, the 617 centroids and the 0.55
assignment threshold fitted in Week 2 - so the decoding path is exactly the
"future requirements standardised automatically" path the project needs anyway.

Guards:

* **leave-one-out.** The decoded advert is removed from its own role's profile.
  Otherwise every requirement it asks for is partly compared with itself - the
  same trap as an industry benchmarked against an average that contains it;
* **MIXED groups are not groups.** Clusters 615, 396 and the other MIXED ones
  hold unrelated things, so an atom landing there is reported as NO GROUP rather
  than given a share it does not deserve;
* thresholds are fixed here, before any advert is decoded.

Run: python advert_decoder.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from karimi import atomise as atom, data, embed  # noqa: E402
from title_cleanup import GENDER, BRACKETS, SENIORITY, TAIL, tidy  # noqa: E402

OUT = HERE.parent / "week 2" / "output"
REQS = HERE.parent / "week 1" / "output" / "requirements.parquet"

# Fixed before decoding anything.
MIN_ADVERTS, MIN_EMPLOYERS = 50, 15
MIN_ASSIGN_COSINE = 0.55        # Week 2's own assignment threshold
STANDARD, UNUSUAL = 0.30, 0.10  # share of comparable adverts asking for it
EXPECTED = 0.35                 # unstated-but-expected: asked by >= this share
SEED = 20261020


def clean_title(s: str) -> str:
    for rx in (GENDER, BRACKETS, SENIORITY):
        s = tidy(rx.sub(" ", s))
    head = tidy(TAIL.sub("", s))
    return head if len(head.split()) >= 2 else s


def verdict(share: float | None) -> str:
    if share is None:
        return "NO GROUP"
    if share >= STANDARD:
        return "STANDARD"
    if share >= UNUSUAL:
        return "COMMON"
    return "UNUSUAL"


class Decoder:
    def __init__(self) -> None:
        b = data.build_analysis_base().df
        b["role"] = b["job_title"].fillna("").str.lower().map(clean_title)
        g = b.groupby("role").agg(a=("vacancy_id", "nunique"),
                                  e=("company", "nunique"))
        self.roles = set(g[(g.a >= MIN_ADVERTS) & (g.e >= MIN_EMPLOYERS)].index)
        self.base = b[b["role"].isin(self.roles)].set_index("vacancy_id")

        d = pd.read_csv(OUT / "cluster_dictionary_named.csv")
        self.label = dict(zip(d["cluster"], d["label"]))
        self.mixed = set(d.loc[d["label"].eq("MIXED"), "cluster"])

        z = np.load(OUT / "cluster_centroids.npz")
        self.cids, self.C = z["cluster_ids"], z["centroids"]
        self.model = embed.load_model()

        # Role profiles from the stored corpus assignments: per role, how many
        # adverts ask for each group. Kept as counts so one advert can be
        # subtracted for leave-one-out.
        r = pd.read_parquet(REQS)
        clu = pd.read_parquet(OUT / "phrase_clusters.parquet")[["phrase_norm", "cluster"]]
        r = r.merge(clu.drop_duplicates("phrase_norm"), on="phrase_norm", how="left")
        r = r[r["vacancy_id"].isin(self.base.index) & r["cluster"].notna()]
        r["cluster"] = r["cluster"].astype(int)
        r = r[(r["cluster"] >= 0) & ~r["cluster"].isin(self.mixed)]
        r["role"] = r["vacancy_id"].map(self.base["role"])
        self.asks = r.drop_duplicates(["vacancy_id", "cluster"])[["vacancy_id", "role", "cluster"]]
        self.counts = self.asks.groupby(["role", "cluster"]).size()
        self.n_role = self.base.groupby("role").size()

    def assign(self, phrases: list[str]) -> list[tuple[int | None, float]]:
        if not phrases:
            return []
        E = embed.encode(self.model, [atom.normalise(p) for p in phrases])
        S = E @ self.C.T
        out = []
        for row in S:
            j = int(np.argmax(row))
            cid, cos = int(self.cids[j]), float(row[j])
            ok = cos >= MIN_ASSIGN_COSINE and cid not in self.mixed
            out.append((cid if ok else None, cos))
        return out

    def share(self, role: str, cid: int, own: set[int]) -> float:
        """Share of the role's OTHER adverts asking for this group."""
        c = int(self.counts.get((role, cid), 0)) - (1 if cid in own else 0)
        return c / (int(self.n_role[role]) - 1)

    def decode(self, vacancy_id: str) -> dict:
        row = self.base.loc[vacancy_id]
        role = row["role"]
        phrases = atom.atomise_posting(row["must_have"])
        assigned = self.assign(phrases)
        own = set(self.asks.loc[self.asks["vacancy_id"] == vacancy_id, "cluster"])

        lines = []
        for p, (cid, cos) in zip(phrases, assigned):
            s = None if cid is None else self.share(role, cid, own)
            lines.append((p, cid, cos, s, verdict(s)))

        mentioned = {cid for _, cid, _, _, _ in lines if cid is not None}
        expected = []
        prof = self.counts.loc[role]
        for cid, _ in prof.items():
            s = self.share(role, int(cid), own)
            if s >= EXPECTED and int(cid) not in mentioned:
                expected.append((self.label.get(int(cid), str(cid)), s))
        expected.sort(key=lambda t: -t[1])
        return {"role": role, "title": row["job_title"], "company": row["company"],
                "industry": row["company_industry"], "lines": lines,
                "expected": expected}

    def show(self, vacancy_id: str) -> None:
        d = self.decode(vacancy_id)
        print(f"\n{'=' * 82}\n{d['title']}  —  {d['company']}  ({d['industry']})")
        print(f"read as role: {d['role'].upper()}, against "
              f"{int(self.n_role[d['role']]) - 1} other adverts for it\n{'=' * 82}")
        for p, cid, cos, s, v in d["lines"]:
            grp = self.label.get(cid, "") if cid is not None else f"(nearest cos {cos:.2f})"
            pct = f"{s:>4.0%}" if s is not None else "   —"
            print(f"  {v:<9} {pct}  {p[:46]:<46}  -> {grp[:30]}")
        if d["expected"]:
            print("\n  NOT MENTIONED, but asked by most comparable adverts:")
            for lab, s in d["expected"][:5]:
                print(f"            {s:>4.0%}  {lab}")

    # ------------------------------------------------------------------
    # The same reading over every advert, so the demo is not an anecdote.
    def market(self) -> None:
        a = self.asks.copy()
        a["n"] = a["role"].map(self.n_role)
        a["c"] = [int(self.counts[(r, c)]) for r, c in zip(a["role"], a["cluster"])]
        a["share"] = (a["c"] - 1) / (a["n"] - 1)   # leave-one-out
        a["v"] = a["share"].map(verdict)
        per = a.groupby("vacancy_id")["v"].value_counts().unstack(fill_value=0)
        tot = per.sum(axis=1)
        print(f"\n{'=' * 82}\nACROSS ALL {len(per):,} ADVERTS OF THE "
              f"{len(self.roles)} ROLES  (requirements that map to a group)\n{'=' * 82}")
        mix = a["v"].value_counts(normalize=True)
        for k in ("STANDARD", "COMMON", "UNUSUAL"):
            print(f"  {k:<9} {mix.get(k, 0):>6.1%} of requirements")
        has_unusual = (per.get("UNUSUAL", 0) > 0).mean()
        print(f"\n  adverts with at least one UNUSUAL requirement: {has_unusual:.1%}")
        print(f"  median UNUSUAL requirements per advert: "
              f"{per.get('UNUSUAL', pd.Series(0, index=per.index)).median():.0f}"
              f"  of a median {tot.median():.0f}")
        by_role = (a.assign(u=a["v"].eq("UNUSUAL"))
                   .groupby("role")["u"].mean().sort_values(ascending=False))
        print("\n  share of requirements that are UNUSUAL for the role:")
        for rl, v in by_role.items():
            print(f"    {rl:<36} {v:>6.1%}")


def main() -> None:
    dec = Decoder()
    rng = np.random.default_rng(SEED)
    picks = []
    for role, lang in (("software engineer", "English"),
                       ("account manager", None),
                       ("data scientist", "English")):
        pool = dec.base[dec.base["role"] == role]
        if lang:
            pool = pool[pool["language"] == lang]
        else:
            pool = pool[pool["language"] != "English"]
        n_atoms = pool["must_have"].map(lambda s: len(atom.atomise_posting(s)))
        pool = pool[(n_atoms >= 6) & (n_atoms <= 12)]
        picks.append(pool.index[rng.integers(len(pool))])
    for v in picks:
        dec.show(v)
    dec.market()


if __name__ == "__main__":
    main()
