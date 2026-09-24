"""Build the public page for GitHub Pages, and set the repo up to serve it.

One difference from the internal build: it writes into docs/ for GitHub Pages.

The employer cloud used to be anonymised here. That chart has moved to article 1,
so this page names no company at all, and what remains is a check that it stays
that way — see below. The anonymisation itself has to travel with the chart: the
article build is now the place where 309 employers must stop being named.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pagecopy

W4 = pathlib.Path(__file__).resolve().parent
ROOT = W4.parent

data = {k: json.loads((W4 / "data" / f"{f}.json").read_text(encoding="utf-8"))
        for k, f in [("tiles", "tiles"),
                     ("c1", "chart1_drivers"), ("c2", "chart2_core_shell")]}

# Chart 4 carried 311 named employers and was anonymised here before publishing.
# It has moved to article 1, so nothing on this page names a company — and the
# anonymisation has nothing left to act on. It is replaced by a check rather than
# by nothing: deleting a guard along with the thing it guarded is how the guard
# fails to be there the next time something similar arrives. If a dataset with
# employer names reaches this build again, it stops here.
named_fields = [k for k, v in data.items()
                if isinstance(v, dict) and "employers" in v]
if named_fields:
    raise SystemExit(
        f"{', '.join(named_fields)} carries employer names and this build no "
        f"longer anonymises them. Restore the anonymisation before publishing.")

tpl = (W4 / "page_template.html").read_text(encoding="utf-8")

# every word on the page comes from pagecopy.md; the template holds only structure
C = pagecopy.load()
fill = {k: pagecopy.inline(v) for k, v in C.items()}
fill["method.steps"] = "".join(
    f'<div class="step"><span class="s">{i+1}</span><span class="t">'
    f'<b>{st["lead"]}</b> <em>{st["rest"]}</em></span></div>'
    for i, st in enumerate(pagecopy.steps(C["method.steps"])))
fill["limits.items"] = "".join(f"<li>{pagecopy.inline(x)}</li>"
                               for x in pagecopy.items(C["limits.items"]))
for who in ("author", "data"):
    ln = pagecopy.link(C[f"credits.{who}.link"])
    fill[f"credits.{who}.link"] = (
        f'<a href="{ln["url"]}">{pagecopy.inline(ln["label"])}</a>' if ln["url"]
        else pagecopy.inline(ln["label"]))

missing = re.findall(r"{{([a-z0-9_.]+)}}", tpl)
absent = [k for k in missing if k not in fill]
if absent:
    raise SystemExit(f"pagecopy.md has no slot for: {', '.join(sorted(set(absent)))}")
for k, v in fill.items():
    tpl = tpl.replace("{{" + k + "}}", v)
left = re.findall(r"{{[a-z0-9_.]+}}", tpl)
assert not left, f"unfilled placeholders: {set(left)}"
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
page = tpl.replace("__DATA__", blob)

doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="What European employers ask for when the job stays the same: 25,800 job adverts, two job families, eleven industries.">
<meta property="og:title" content="What employers ask for, when the job stays the same">
<meta property="og:description" content="Hold the role fixed, change the context, and see which requirements move.">
<meta property="og:type" content="article">
<style>html{color-scheme:light dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
""" + page + """
</html>
"""

docs = ROOT / "docs"
docs.mkdir(exist_ok=True)
current = docs / "index.html"

# --check answers one question: is the published page what copy.md and the
# datasets currently say? Editing copy.md and committing without rebuilding
# leaves docs/index.html a version behind, and nothing about the diff looks
# wrong — the page is valid, just stale. Run it before committing.
if "--check" in sys.argv:
    live = current.read_text(encoding="utf-8") if current.exists() else ""
    if live == doc:
        print("docs/index.html is up to date with copy.md and the datasets")
        raise SystemExit(0)
    print("docs/index.html is STALE — copy.md or the datasets have moved on.")
    print("Rebuild before committing:  python \"week 4/build_public.py\"")
    raise SystemExit(1)

current.write_text(doc, encoding="utf-8")
# GitHub Pages runs Jekyll by default, which skips files and folders beginning
# with an underscore; this switches it off so the directory is served verbatim.
(docs / ".nojekyll").write_text("", encoding="utf-8")

print(f"docs/index.html  {len(doc)/1024:.0f} KB")
print(f"docs/.nojekyll   (serves the folder verbatim)")
print("")
print("To publish: commit docs/, push, then in the repository's")
print("Settings → Pages set Source = 'Deploy from a branch', branch = main, folder = /docs.")
