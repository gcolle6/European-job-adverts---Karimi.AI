"""Inline the article 1 dataset into its template and write a standalone page.

Separate from article1_data.py on purpose: the data step loads the corpus and
takes a few seconds, the page step is instant, and the copy is edited far more
often than the numbers.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

data = json.loads((HERE / "data" / "article1.json").read_text(encoding="utf-8"))
tpl = (HERE / "article1_template.html").read_text(encoding="utf-8")

# `</script>` inside a JSON string would close the host tag early
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
page = tpl.replace("__DATA__", blob)

doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>html{color-scheme:light dark}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
""" + page + """
</html>
"""
out = HERE / "article1.html"
out.write_text(doc, encoding="utf-8")

print(f"data inlined: {len(blob)/1024:.1f} KB")
for k in "abcde":
    print(f"  {k}: {data[k]['title']}")
print(f"\n{out}")
print(f"{len(doc)/1024:.0f} KB — open it in a browser")
