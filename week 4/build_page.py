"""Inline the six datasets into the page, and write a standalone local copy.

The data is embedded rather than fetched. Two reasons: the published page's
policy blocks cross-origin requests and a same-origin fetch is one more thing
that can fail silently at open time, and the local copy has to work from the
filesystem with no server at all. 140 KB of JSON inside the document costs
nothing against a 16 MB budget.
"""
import json
import pathlib

SCRATCH = pathlib.Path(r"C:\Users\giaco\AppData\Local\Temp\claude"
                       r"\c--Users-giaco-OneDrive-Desktop-Karimi-ai"
                       r"\4b6971b1-348b-41fb-bfd2-11115c9bf682\scratchpad")
W4 = pathlib.Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 4")

data = {
    "tiles": json.loads((W4 / "data" / "tiles.json").read_text(encoding="utf-8")),
    "weighting": json.loads((W4 / "data" / "weighting.json").read_text(encoding="utf-8")),
    "c1": json.loads((W4 / "data" / "chart1_drivers.json").read_text(encoding="utf-8")),
    "c2": json.loads((W4 / "data" / "chart2_core_shell.json").read_text(encoding="utf-8")),
    "c3": json.loads((W4 / "data" / "chart3_residual.json").read_text(encoding="utf-8")),
    "c4": json.loads((W4 / "data" / "chart4_employers.json").read_text(encoding="utf-8")),
}

tpl = (SCRATCH / "dash.html").read_text(encoding="utf-8")
# `</script>` inside a JSON string would close the host tag early
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
page = tpl.replace("__DATA__", blob)

(SCRATCH / "dash_built.html").write_text(page, encoding="utf-8")

local = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html{color-scheme:light dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
""" + page + """
</html>
"""
(W4 / "dashboard.html").write_text(local, encoding="utf-8")

print(f"data inlined: {len(blob)/1024:.0f} KB")
print(f"  chart 2 groups   : {len(data['c2']['groups'])}")
print(f"  chart 4 employers: {len(data['c4']['employers'])}")
print(f"page: {len(page)/1024:.0f} KB")
print(f"\nartifact source: dash_built.html")
print(f"local copy:      week 4/dashboard.html")
