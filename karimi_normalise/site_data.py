"""Export what the site shows, as flat tables: quality cards, versions, cosine, a run.

    python -m karimi_normalise.site_data --dict 0.0.dev2 --run example_report.json

Reads only generated files (`quality.py` cards, the dictionary's
`reference.json`, a `run_report` saved as JSON) and writes one JSON table per
section into `New project/output/site/`. Labels are in Italian: the site's
language. Aggregates only, except the run's "to check" lists, which hold
requirement phrases from that run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .freeze import STORE
from .quality import QUALITY

SITE = QUALITY.parent / "site"

SIGNAL_LABELS = {
    "requirements_per_item": "Requisiti per elemento",
    "share_items_llm": "Elementi lasciati interi (composti)",
    "share_items_damaged": "Elementi lasciati interi (split rotto)",
    "share_one_word": "Requisiti di una sola parola",
    "share_translated": "Requisiti tradotti",
    "share_known": "Già nel dizionario",
    "share_group_nearest": "Gruppo trovato per somiglianza",
    "share_topic_only": "Solo il tema",
    "share_nuovo": "Nuovi",
    "share_titles_nuovo": "Titoli nuovi",
}
MATCH_LABELS = {
    "known": ("Già noto", "stessa testa e stesso nucleo di un requisito del dizionario"),
    "group": ("Stesso requisito", "il più vicino ha coseno ≥ soglia di gruppo: prende gruppo e tema"),
    "topic": ("Stesso tema", "coseno tra le due soglie: prende solo il tema"),
    "nuovo": ("Nuovo", "coseno sotto la soglia di tema: nessun gruppo, da collocare al prossimo congelamento"),
}
SIGNAL_MATCH = {"known": "share_known", "group": "share_group_nearest",
                "topic": "share_topic_only", "nuovo": "share_nuovo"}


def _rate(cell: dict) -> float | None:
    return round(cell["errors"] / cell["pairs"], 4) if cell.get("pairs") else None


def quality_rows(c: dict) -> list[dict]:
    rows = []

    def add(key, area, misura, valore, n=None, errori=None, basso=None, alto=None, lettura="", nota=""):
        rows.append({"key": key, "area": area, "misura": misura, "valore": valore, "errori": errori,
                     "n": n, "basso": basso, "alto": alto, "lettura": lettura, "nota": nota})

    s = c["split_count"]["blind_half"]
    add("split_exact", "Split", "Numero di requisiti giusto", s["exact"], s["items"], None,
        *s["exact_ci95"], "cieca", "metà mai letta riga per riga; intervallo al 95%")
    add("split_over", "Split", "Diviso troppo", s["over_split"], s["items"], lettura="cieca")
    add("split_under", "Split", "Diviso troppo poco", s["under_split"], s["items"], lettura="cieca")
    for reading in ("blind", "rechecked"):
        p, lab = c["pairs"][reading], "cieca" if reading == "blind" else "ricontrollata"
        for lvl, area in (("requirement_group", "Gruppo requisiti (0,90)"),
                          ("requirement_topic", "Tema requisiti (0,80)")):
            m, a = p[lvl]["merged"], p[lvl]["apart"]
            add(f"{lvl}_wrong_{reading}", area, "Unioni sbagliate", _rate(m), m["pairs"], m["errors"], lettura=lab)
            add(f"{lvl}_missed_{reading}", area, "Unioni mancate", _rate(a), a["pairs"], a["errors"], lettura=lab,
                nota="coppie vicine scelte apposta: è un tetto, non la media del corpus")
        m, a = p["role"]["merged"], p["role"]["apart"]
        add(f"role_wrong_{reading}", "Ruoli", "Unioni sbagliate", _rate(m), m["pairs"], m["errors"], lettura=lab)
        add(f"role_missed_{reading}", "Ruoli", "Unioni mancate", _rate(a), a["pairs"], a["errors"], lettura=lab,
            nota="coppie a una parola di distanza: le più difficili")
    t = c["tests"]
    add("tests", "Regole", "Casi di test superati", t["passed"] / t["total"], t["total"],
        t["total"] - t["passed"], lettura="automatico", nota="comportamento deciso, non correttezza")
    if c.get("parity_with_batch"):
        q = c["parity_with_batch"]
        add("parity", "Libreria", "Split identico al batch", q["share_identical"], q["items"],
            q["items"] - q["items_identical"], lettura="automatico", nota="coerenza, non correttezza")
    lv = (c.get("lookup_vs_batch") or {}).get("by_match", {})
    if "group" in lv:
        add("lookup_group", "Dizionario", "Gruppo per somiglianza uguale al batch", lv["group"]["same_group"],
            lv["group"]["atoms"], lettura="automatico", nota="annunci che il dizionario non ha visto")
    if "topic" in lv:
        add("lookup_topic", "Dizionario", "Solo tema: tema uguale al batch", lv["topic"]["same_topic"],
            lv["topic"]["atoms"], lettura="automatico", nota="annunci che il dizionario non ha visto")
    return rows


def version_row(c: dict) -> dict:
    by = {r["key"]: r for r in quality_rows(c)}
    get = lambda k: by[k]["valore"] if k in by else None  # noqa: E731
    return {"versione": f"{c['rules_version']} · {c['dict_version']}", "regole": c["rules_version"],
            "dizionario": c["dict_version"], "data": c["generated"],
            "stato": "pronto per il rilascio" if c["release"] else "sviluppo",
            "conteggio_giusto": get("split_exact"),
            "unioni_requisiti_sbagliate": get("requirement_group_wrong_blind"),
            "unioni_ruoli_sbagliate": get("role_wrong_blind"),
            "ruoli_mancati": get("role_missed_rechecked"),
            "gruppo_uguale_batch": get("lookup_group"), "split_uguale_batch": get("parity")}


def cosine_rows(ref: dict, manifest: dict) -> list[dict]:
    g, t = manifest["group_threshold"], manifest["topic_threshold"]
    lv = ref["lookup_vs_batch"]["by_match"]
    bounds = {"known": (1.0, 1.0), "group": (g, 1.0), "topic": (t, g), "nuovo": (0.0, t)}
    out = []
    for k, (label, meaning) in MATCH_LABELS.items():
        agree = lv.get(k, {}).get("same_topic" if k == "topic" else "same_group")
        out.append({"livello": k, "etichetta": label, "da": bounds[k][0], "a": bounds[k][1],
                    "quota": ref["signals"][SIGNAL_MATCH[k]]["overall"],
                    "uguale_batch": agree, "significato": meaning})
    return out


def run_tables(rep: dict) -> tuple[list[dict], list[dict], list[dict]]:
    s = rep["summary"]
    summary = [{"annunci": s["postings"], "elementi": s["items"], "requisiti": s["requirements"],
                "requisiti_per_elemento": s["requirements_per_item"], "esito": rep["overall"],
                "regole": rep["versions"]["rules_version"], "dizionario": rep["versions"]["dict_version"]}]
    signals = [{"segnale": k, "etichetta": SIGNAL_LABELS[k], "valore": v["value"], "tipico": v["typical"],
                "da": v["normal_range"][0], "a": v["normal_range"][1], "luce": v["light"]}
               for k, v in rep["signals"].items()]
    check = ([{"tipo": "Lasciato intero", "testo": x["item"], "dettaglio": "", "n": x["n"]}
              for x in rep["to_check"]["items_kept_whole"][:5]]
             + [{"tipo": "Nuovo", "testo": x["requirement"], "dettaglio": "", "n": x["n"]}
                for x in rep["to_check"]["requirements_nuovo"][:5]]
             + [{"tipo": "Solo tema", "testo": x["requirement"], "dettaglio": x["topic"], "n": x["n"]}
                for x in rep["to_check"]["requirements_topic_only"][:5]])
    return summary, signals, check


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dict", required=True)
    p.add_argument("--run", help="a run_report saved as JSON")
    args = p.parse_args(argv)
    SITE.mkdir(parents=True, exist_ok=True)
    cards = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(QUALITY.glob("quality_*.json"))]
    cur = next(c for c in cards if c["dict_version"] == args.dict)
    d = STORE / args.dict
    ref = json.loads((d / "reference.json").read_text(encoding="utf-8"))
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    tables = {"qualita": quality_rows(cur), "versioni": [version_row(c) for c in cards],
              "coseno": cosine_rows(ref, manifest)}
    if args.run:
        tables["run_riepilogo"], tables["run_segnali"], tables["run_controllare"] = run_tables(
            json.loads(Path(args.run).read_text(encoding="utf-8")))
    for name, rows in tables.items():
        (SITE / f"{name}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {len(rows)} rows -> {SITE / (name + '.json')}")


if __name__ == "__main__":
    main()
