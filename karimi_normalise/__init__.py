"""karimi-normalise — split `must_have` into single requirements and normalise them.

    from karimi_normalise import Dictionary, TranslationCache, process

    d = Dictionary("dictionaries/0.1.0")
    out = process([{"must_have": ["3+ years of Python and SQL", "Fließend Deutsch"],
                    "title": "Senior Data Engineer (m/w/d)"}],
                  d, cache=TranslationCache("translate_cache.jsonl"))
    for r in out["postings"][0]["requirements"]:
        print(r.atom_norm, r.req_group, r.req_topic, r.match)
    out["report"]["overall"]          # green / yellow / red, and why in out["report"]["signals"]

`process` is the one call to use. `split_posting` and `normalise_title` do one
posting or one title. The rules live in `karimi/` and are shared with the
analysis: a rule fixed there is fixed here. Every output carries
`rules_version` and `dict_version`. Plan: `New project/PIANO_SVILUPPO.md`.
"""

from .dictionary import Dictionary, ReqMatch
from .metrics import log_run, run_report
from .process import process
from .requirements import Requirement, split, split_posting
from .titles import Title, normalise_title
from .translate import TranslationCache
from .versions import RULES_VERSION

__version__ = RULES_VERSION
__all__ = ["Dictionary", "ReqMatch", "Requirement", "Title", "TranslationCache", "log_run", "process",
           "run_report", "split", "split_posting", "normalise_title", "RULES_VERSION"]
