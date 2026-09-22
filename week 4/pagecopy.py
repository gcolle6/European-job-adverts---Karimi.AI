"""Read copy.md — the one file that holds every word on the page.

The copy used to live in three places: headings in the page template, chart
titles and notes in the dataset builder, bullets in a Python dict. Editing the
page meant knowing which. It now lives in one Markdown file, because the person
rewriting it is writing prose, not editing a data structure, and prose does not
want quotes and trailing commas around it.

Named pagecopy rather than copy: a module called `copy` on sys.path shadows
the standard library's, and pyarrow calls copy.deepcopy during import, so the
obvious name breaks every script that touches a parquet file.

Deliberately small. It understands `## key`, three slot shapes, and the two
inline marks a heading or a bullet needs. It is not a Markdown parser
and should not become one: anything it does not understand is passed through as
text, which fails visibly rather than silently.
"""
from __future__ import annotations

import html
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "copy.md"

_KEY = re.compile(r"^##\s+([A-Za-z0-9_.]+)\s*$", re.M)


def load(path: pathlib.Path | None = None) -> dict[str, str]:
    """Every `## key` in the file, mapped to its raw body text."""
    text = (path or SOURCE).read_text(encoding="utf-8")
    out, marks = {}, list(_KEY.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        # a `---` rule or a `#` heading ends a slot; they are the file's own
        # furniture, not part of anyone's copy
        body = re.split(r"^(?:---\s*|#\s+.*)$", body, maxsplit=1, flags=re.M)[0]
        out[m.group(1)] = body.strip()
    return out


def inline(s: str) -> str:
    """`**bold**` and `` `code` ``, escaped first so the source cannot inject HTML."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def items(body: str) -> list[str]:
    """The `- ` lines of a list slot, in order."""
    return [ln[2:].strip() for ln in body.splitlines() if ln.strip().startswith("- ")]


def steps(body: str) -> list[dict[str, str]]:
    """`- **lead** trailing` → the method strip's two-part rows."""
    out = []
    for it in items(body):
        m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", it, re.S)
        out.append({"lead": inline(m.group(1)), "rest": inline(m.group(2))}
                   if m else {"lead": inline(it), "rest": ""})
    return out


def points(body: str) -> list[dict[str, str]]:
    """``- `figure` text`` → the chips and sentences under a chart.

    A bullet with no backticked figure keeps its whole text and shows no chip,
    rather than silently dropping half the line.
    """
    out = []
    for it in items(body):
        m = re.match(r"`(.+?)`\s*(.*)$", it, re.S)
        if m:
            out.append({"stat": m.group(1).strip(), "text": " ".join(m.group(2).split())})
        else:
            out.append({"stat": "", "text": " ".join(it.split())})
    return out


def link(body: str) -> dict[str, str]:
    """`label → https://url` → the two halves, or a bare label with no url."""
    m = re.match(r"(.*?)(https?://\S+)\s*$", body.strip(), re.S)
    if not m:
        return {"label": body.strip(), "url": ""}
    return {"label": m.group(1).strip().rstrip("→").strip() + " →",
            "url": m.group(2)}

