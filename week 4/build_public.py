"""Build the public page for GitHub Pages, and set the repo up to serve it.

Two differences from the internal build, both about what goes public.

**The employer cloud is anonymised.** Chart 4 carries 311 employers and its
tooltip names each one, which on a public page is a browsable ranking of
companies by how much they repeat their own job adverts. The observation is
factual and drawn from public adverts, but being one of 311 dots is not the same
as being a row in a published list, and that is a commercial judgement rather
than a technical one.

The two named examples stay, because they carry the argument and neither is an
accusation: the largest poster writes 975 genuinely different adverts, and the
counter-example writes 86 near-identical ones. The other 309 become "an employer"
— the cloud exists to show the two are not cherry-picked, and it does that
without names.

**Nothing else changes.** Group labels, industry names and every aggregate are
already impersonal.

Run with `--named` to build the version that keeps all 311, if that is decided.
"""
import json
import pathlib
import shutil
import sys

W4 = pathlib.Path(__file__).resolve().parent
ROOT = W4.parent

KEEP_NAMED = "--named" in sys.argv

data = {k: json.loads((W4 / "data" / f"{f}.json").read_text(encoding="utf-8"))
        for k, f in [("tiles", "tiles"), ("weighting", "weighting"),
                     ("c1", "chart1_drivers"), ("c2", "chart2_core_shell"),
                     ("c3", "chart3_residual"), ("c4", "chart4_employers")]}

if not KEEP_NAMED:
    n = 0
    for e in data["c4"]["employers"]:
        if not e["highlight"]:
            e["name"] = "an employer"
            n += 1
    data["c4"]["note"] += (" Individual employers are not named: the two labelled "
                           "examples carry the point and the rest are shown as a "
                           "distribution.")
    print(f"anonymised {n} employers; {len(data['c4']['employers']) - n} kept named")

tpl = (W4 / "page_template.html").read_text(encoding="utf-8")
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
page = tpl.replace("__DATA__", blob)

doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="What European employers ask for when the job stays the same: 25,800 job adverts, two job families, eleven industries.">
<meta property="og:title" content="What employers ask for, when the job stays the same">
<meta property="og:description" content="Hold the role fixed, change the context, and see which requirements actually move.">
<meta property="og:type" content="article">
<style>html{color-scheme:light dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
""" + page + """
</html>
"""

docs = ROOT / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(doc, encoding="utf-8")
# GitHub Pages runs Jekyll by default, which skips files and folders beginning
# with an underscore; this switches it off so the directory is served verbatim.
(docs / ".nojekyll").write_text("", encoding="utf-8")

print(f"docs/index.html  {len(doc)/1024:.0f} KB")
print(f"docs/.nojekyll   (serves the folder verbatim)")
print("")
print("To publish: commit docs/, push, then in the repository's")
print("Settings → Pages set Source = 'Deploy from a branch', branch = main, folder = /docs.")
