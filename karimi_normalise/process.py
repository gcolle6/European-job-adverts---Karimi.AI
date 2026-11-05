"""One call for a run: postings in, requirements, titles and the run report out.

    from karimi_normalise import Dictionary, TranslationCache, process

    d = Dictionary("dictionaries/0.1.0")
    out = process([{"id": "a1", "must_have": ["3+ years of Python and SQL"], "title": "Data Engineer"}],
                  d, cache=TranslationCache("translate_cache.jsonl"))
    out["report"]["overall"], out["postings"][0]["requirements"][0].req_group

Decided 2026-11-04: Karimi uses the LIBRARY, not the API, so the computation
and its cost are theirs. Everything the API returned is therefore here too,
the run report included. The steps run in order inside it, as in
`split_posting`; what this adds is that translation, the costliest step, runs
once for the whole run (`english_items`), each repeated item translated once
and remembered in ``cache``.
"""

from __future__ import annotations

from karimi import pos

from .metrics import run_report
from .requirements import english_items, split_posting
from .titles import normalise_title


def process(postings: list[dict], dictionary=None, translate: bool = True, cache=None,
            translator=None) -> dict:
    """Each posting: ``must_have`` (list of str), optional ``title``, ``id``,
    ``language`` (a fallback name such as `Deutsch`, for short items) and
    ``must_have_english`` (the caller's own translation, aligned with
    ``must_have``: those items are used as given, not translated).

    ``translator`` is the caller's choice for the rest: a function taking
    [(code, text)] and returning {(code, text): English}. Without one, opus-mt
    (`pip install karimi-normalise[translate]`), the translator the quality
    card was measured with; with another, run the count check again
    (`New project/score_counts.py`) before trusting the card.

    Returns ``postings`` (id, requirements, title) and ``report``
    (`metrics.run_report`: signals against the dictionary's reference, and
    the items worth a look).
    """
    english = (english_items([(p.get("must_have") or [], p.get("language"), p.get("must_have_english"))
                              for p in postings], cache, translator)
               if translate else [{} for _ in postings])
    if translate:
        pos.prime(e[it][0] if it in e else it for p, e in zip(postings, english) for it in p.get("must_have") or [])
    out, runs, titles = [], [], []
    for k, (p, e) in enumerate(zip(postings, english)):
        reqs = split_posting(p.get("must_have") or [], dictionary, translate, english=e)
        t = normalise_title(p["title"], dictionary) if p.get("title") else None
        runs.append(reqs)
        titles += [t] if t else []
        out.append({"id": p.get("id", k), "requirements": reqs, "title": t})
    return {"postings": out, "report": run_report(runs, titles, dictionary)}
