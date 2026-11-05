"""From a job title to a role, a level and the parts that are neither.

The rules are `karimi/normalise_title.py`, as in the batch
(`New project/normalise_titles.py`). Give the English title: the export carries
one (`job_title_english`, translated upstream). The batch also translates the
71 titles that lack it, deciding their language from words learned on the
whole corpus; that step needs the corpus and is not in the library yet.

A new title joins a group on an identical key, or as a spelling variant of a
role the dictionary holds (`Developers` / `Developer`, `Fullstack` /
`Full Stack`), the same variants the batch joins. A role that is neither comes
back `nuovo` until the next freeze.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from karimi import normalise_title as nt

from .versions import RULES_VERSION


@dataclass
class Title:
    title: str
    title_role: str
    title_level: str
    title_extra: str
    title_key: str
    title_group: str = ""
    title_name: str = ""
    match: str = ""         # known | variant | nuovo, "" without a dictionary
    rules_version: str = RULES_VERSION
    dict_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def normalise_title(title: str, dictionary=None) -> Title:
    d = nt.decompose(title)
    acronyms = dictionary.acronyms if dictionary is not None else None
    t = Title(title=title, title_role=d["role"], title_level=d["level"], title_extra=d["extra"],
              title_key=nt.key(d["role"], acronyms))
    if dictionary is not None:
        _, t.title_group, t.title_name, t.match = dictionary.lookup_title(d["role"])
        t.dict_version = dictionary.version
    return t
