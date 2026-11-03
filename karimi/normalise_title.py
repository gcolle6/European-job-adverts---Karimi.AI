"""One role, however the job title is written (decided 2026-11-02).

`data scientist`, `Data Scientist`, `DATA SCIENTIST (m/w/d)` and `Senior Data
Scientist - Paris` are one role; so are `Engineer of data` and `Data Engineer`.
Titles fragment exactly as requirement strings do (`New project/project.md`
§3.1: 17,190 distinct titles over 25,800 postings), and the same treatment
applies: rules first, every removed part kept in a column of its own, so
grouping loses nothing.

What is removed from the role, and where it goes:

* gender markers — nothing, they carry nothing (`(m/f/d)`, `H/F`, `all genders`);
* seniority — ``level``: the export has its own `seniority` field, and a career
  map wants seniority as an axis, not as a different node;
* brackets and trailing parts after ` - `, ` | `, `, ` or `: ` — ``extra``:
  location, team, product, contract (`- Sovereign Cloud Delivery Germany`).

The KEY of a role is its content words as a set, lowercased, so word order and
case do not make a new role (`Engineer of data` = `Data Engineer`, `Manager AI
Delivery` = `AI Delivery Manager`). Spelling variants join after that, in
`group_titles`: `Full-Stack` = `Fullstack`, `Systems` = `System`, and acronyms
the titles define themselves (`Site Reliability Engineer (SRE)`).

⚠️ No embedding. Over-merging is the fatal error on this axis (`project.md`
§3.5): `Data Analyst` and `Data Scientist` are the comparison the product
exists to make, and a sentence embedding puts them side by side. A different
content word is a different role here, always.
"""

from __future__ import annotations

import collections
import re

# Gender markers of European adverts, with or without brackets: `(m/w/d)`,
# `(f/m/x)`, `(F/M/)`, `H/F`, `M/F`, `(all genders)`, `(m/f)`, and a feminine
# ending bracketed onto the word itself: `Stagiair(e)`, `Mitarbeiter(in)`.
_GENDER_RE = re.compile(
    r"\(\s*(?:all\s+genders?|[mwfdhxi*](?:\s*[/|,]\s*[mwfdhxi*]?){1,3}\s*)\)|"
    r"(?<=[^\W\d_])\((?:e|in|ne|ssa)\)|"
    r"(?<![\w/])[mwfdhx](?:\s*/\s*[mwfdhx]){1,3}(?![\w/])|"
    r"\ball\s+genders?\b|\bgn\*",
    re.I)
_BRACKET_RE = re.compile(r"[(\[{]([^)\]}]*)[)\]}]")
# A separator with space on both sides, or a comma/colon: never inside a word
# (`Full-Stack`, `S/4HANA`, `R&D` stay whole). The same trap as `atomise`.
_SEP_RE = re.compile(r"\s+[-–—|/]\s+|\s*[,:;]\s+|\s+[–—]\s*|\s*[–—]\s+")

# Seniority words. Always seniority: these never name a role by themselves.
_LEVEL_ALWAYS = {
    "senior": "senior", "sr": "senior", "snr": "senior", "junior": "junior", "jr": "junior",
    "mid-level": "mid", "midlevel": "mid", "medior": "mid", "mid": "mid",
    "intern": "intern", "internship": "intern", "trainee": "intern", "apprentice": "intern",
    "apprenticeship": "intern", "werkstudent": "intern", "graduate": "graduate",
    "entry-level": "entry", "experienced": "experienced",
    # Grade numbers of tech ladders: `Software Engineer II`.
    "ii": "grade 2", "iii": "grade 3", "iv": "grade 4",
}
_LEVEL_PHRASES = re.compile(
    r"\b(?:working\s+student|student\s+assistant|entry\s+level|mid\s+level|"
    r"stagiaire|stagiair|alternance|alternant|stage|tirocinio|stagista|becario|praktikant(?:in)?|lehrstelle)\b", re.I)
# Seniority only IN FRONT of another role word: `Lead Data Engineer`,
# `Principal Engineer`, `Expert DevOps Engineer`. At the end they are the role:
# `Tech Lead`, `Battery Integration Expert`, `Research Associate`.
_LEVEL_PREFIX = {"lead": "lead", "principal": "principal", "staff": "staff", "expert": "expert",
                 "associate": "associate", "chief": None, "head": None}

# Words that are function words, not content: they do not make a role.
_STOP = {"of", "for", "in", "the", "a", "an", "and", "&", "with", "at", "to", "on", "de", "du",
         "des", "la", "le", "et", "der", "die", "das", "und", "im", "per", "di", "del", "e",
         "y", "en", "van", "voor", "het"}
# Nouns that head a job title. A part of a title that ends in one of these is
# the role; other parts are context (`Honeywell - Building Management Systems
# Engineer`). A closed class: the ways a job is named, not what it is about.
_ROLE_NOUNS = {
    "engineer", "developer", "analyst", "scientist", "architect", "manager", "consultant",
    "specialist", "administrator", "designer", "tester", "lead", "owner", "master", "officer",
    "director", "head", "intern", "technician", "researcher", "programmer", "expert", "advisor",
    "adviser", "associate", "coordinator", "executive", "representative", "operator", "assistant",
    "support", "trainee", "student", "postdoc", "fellow", "professor", "lecturer", "editor",
    "writer", "author", "recruiter", "partner", "president", "vp", "cto", "cio", "ciso", "ceo",
    "auditor", "controller", "planner", "strategist", "evangelist", "advocate", "agent",
    "steward", "champion", "instructor", "trainer", "teacher", "buyer", "seller", "engineering",
    "apprentice", "graduate", "phd", "candidate", "thesis", "technologist", "modeler", "modeller",
    "integrator", "inspector", "supervisor", "mechanic", "electrician", "expert", "guard",
}


def _words(s: str) -> list[str]:
    return re.findall(r"[\w+#.&'’/-]+", s)


def clean(title: str) -> str:
    """The title without gender markers, quotes and stray punctuation."""
    s = _GENDER_RE.sub(" ", title or "")
    s = re.sub(r"[»«\"“”]", " ", s)
    s = re.sub(r"\(\s*\)|\[\s*\]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" -–—|,.:;/*")


def _only_level(part: str) -> bool:
    ws = [w.lower().strip(".") for w in _words(_LEVEL_PHRASES.sub(" intern ", part))]
    return bool(ws) and all(w in _LEVEL_ALWAYS for w in ws)


def _is_role_part(part: str) -> bool:
    """A part naming a role: it holds a role noun that is not a seniority word."""
    ws = [w.lower().strip(".") for w in _words(part)]
    return any(w in _ROLE_NOUNS and w not in _LEVEL_ALWAYS for w in ws)


def _phrase_level(phrase: str) -> str:
    p = phrase.lower()
    return "entry" if p.startswith("entry") else "mid" if p.startswith("mid") else "intern"


def decompose(title: str) -> dict:
    """``role`` (as written), ``level``, ``extra`` and the order-free ``key``."""
    s = clean(title)
    extra: list[str] = []
    levels: list[str] = []

    # Brackets: a seniority word goes to the level, anything else to extra.
    def _bracket(m: re.Match) -> str:
        inner = m.group(1).strip()
        found = [_LEVEL_ALWAYS[w.lower().strip(".")] for w in _words(inner)
                 if w.lower().strip(".") in _LEVEL_ALWAYS]
        if found and len(_words(inner)) <= 2:
            levels.extend(found)
        elif inner:
            extra.append(inner)
        return " "
    s = re.sub(r"\s+", " ", _BRACKET_RE.sub(_bracket, s)).strip(" -–—|,.:;/")

    # Separated parts: the first that is headed by a role noun is the role.
    parts = [p.strip() for p in _SEP_RE.split(s) if p and p.strip()]
    role_k = next((k for k, p in enumerate(parts) if _is_role_part(p) and not _only_level(p)), 0)
    role = parts[role_k] if parts else ""
    for k, p in enumerate(parts):
        if k == role_k:
            continue
        lv = [_LEVEL_ALWAYS[w.lower().strip(".")] for w in _words(p) if w.lower().strip(".") in _LEVEL_ALWAYS]
        if lv and len(_words(p)) <= 2:
            levels.extend(lv)
        elif _LEVEL_PHRASES.fullmatch(p):
            # `... - Alternance`, `... - Working Student`.
            levels.append(_phrase_level(p))
        else:
            extra.append(p)

    # Seniority inside the role.
    for m in _LEVEL_PHRASES.finditer(role):
        levels.append(_phrase_level(m.group()))
    role = _LEVEL_PHRASES.sub(" ", role)
    # `Medior/Senior`, `Junior/Mid`: levels joined by a slash are levels.
    words = [x for w in _words(role)
             for x in (w.split("/") if all(y.lower().strip(".") in _LEVEL_ALWAYS for y in w.split("/") if y)
                       else [w]) if x]
    kept = []
    for i, w in enumerate(words):
        lw = w.lower().strip(".")
        if lw in _LEVEL_ALWAYS and len(words) > 1:
            levels.append(_LEVEL_ALWAYS[lw])
            continue
        # A level word in front of another role word: `Lead Data Engineer`.
        if lw in _LEVEL_PREFIX and _LEVEL_PREFIX[lw] and i < len(words) - 1 \
                and any(x.lower() in _ROLE_NOUNS - {lw} for x in words[i + 1:]):
            levels.append(_LEVEL_PREFIX[lw])
            continue
        kept.append(w)
    role = " ".join(kept).strip(" -–—|,.:;/")

    # `Intern - Data Science`, `Staff Engineer - Endpoint security`: once the
    # seniority is out, the role is a bare noun or nothing, and what it is about
    # sits after the dash. The two are one role (`Endpoint security Engineer`).
    # Only the first such part, and only a short one: a long tail is a project
    # description (`Internship | Development of an Office Reservation System`).
    if role and _only_level(role):
        # `Internship - Data Science`: the level IS the role part.
        levels.extend(_LEVEL_ALWAYS.get(w.lower().strip("."), "intern") for w in _words(role))
        role = ""
    bare = not role or (len(_words(role)) == 1 and role.lower() in _ROLE_NOUNS)
    tail = next((p for p in parts if p != parts[role_k] and p in extra), None) if parts else None
    if bare and tail and len(_words(tail)) <= 6:
        extra.remove(tail)
        role = clean(f"{role} {tail}")

    return {"role": role, "level": "|".join(dict.fromkeys(levels)), "extra": " | ".join(extra),
            "key": key(role)}


def _tokens(role: str, acronyms: dict[str, str] | None = None) -> list[str]:
    """Content words, lowercased, hyphens and slashes opened (`full-stack` ->
    full, stack), defined acronyms written out (`AI/ML` -> artificial
    intelligence machine learning)."""
    out = []
    for w in _words(role.lower()):
        for t in re.split(r"[-/]", w.strip(".'’")):
            for x in (acronyms or {}).get(t, t).split():
                if x and x not in _STOP:
                    out.append(x)
    return out


def key(role: str, acronyms: dict[str, str] | None = None) -> str:
    """The set of content words, sorted: order and case make no new role."""
    return " ".join(sorted(set(_tokens(role, acronyms))))


def group_titles(roles: list[str], acronyms: dict[str, str] | None = None) -> dict[str, str]:
    """Map each role key to the key of its group, joining spelling variants.

    Three variants, each joined only when BOTH spellings occur in the data, so
    nothing is invented:

    * plural: `systems engineer` = `system engineer`, `solutions architect` =
      `solution architect` — a word ending in -s joins its singular if the
      singular is a word of some other title (`devops` stays: no `devop`);
    * compounds: `fullstack` = `full stack`, `backend` = `back end`, by the
      letters in written order;
    * acronyms the titles define: `Site Reliability Engineer (SRE)` makes `sre`
      = `site reliability`. Read from the raw titles by `learn_acronyms`.

    Returns key -> group key; the group key is the key of the most frequent
    member, so the group is named by its commonest wording.
    """
    keys = collections.Counter(key(r, acronyms) for r in roles)
    vocab = {t for k in keys for t in k.split()}

    def singular(t: str) -> str:
        if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) and t[:-1] in vocab:
            return t[:-1]
        return t

    parent: dict[str, str] = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            # The more frequent key names the group.
            if (keys[ra], ra) < (keys[rb], rb):
                ra, rb = rb, ra
            parent[rb] = ra

    by_variant: dict[str, str] = {}
    for r in roles:
        k = key(r, acronyms)
        if not k:
            continue
        toks = _tokens(r, acronyms)
        variants = {
            " ".join(sorted({singular(t) for t in toks})),
            # the letters in written order: `full stack` = `fullstack`
            "#" + "".join(singular(t) for t in toks),
        }
        if _developer_head(r):
            # Decided 2026-11-02: a Developer is the same role as an Engineer.
            variants.add(" ".join(sorted({singular("engineer" if t == "developer" else t) for t in toks})))
        for v in variants:
            if v in by_variant:
                union(by_variant[v], k)
            else:
                by_variant[v] = k
    return {k: find(k) for k in keys}


def _developer_head(role: str) -> bool:
    """`Developer` heads the title (`Backend Developer`, `Software Developer`),
    so it is the engineer role. Not a `Business Developer` or `Sales
    Developer`: that is business development, a sales role. And not `Developer`
    as a modifier: `Developer Platform Engineer` is about a developer platform."""
    ws = [w.lower() for w in _words(role)]
    return bool(ws) and ws[-1] in ("developer", "developers") \
        and not {"business", "sales"} & set(ws)


_ACRONYM_RE = re.compile(r"((?:[A-Za-z][\w-]*\s+){1,4}[A-Za-z][\w-]*)\s*\(\s*([A-Z]{2,5})\s*\)")


def learn_acronyms(titles: list[str]) -> dict[str, str]:
    """Acronyms the titles define themselves: `... Site Reliability Engineer
    (SRE)`. The initials of the words before the bracket must spell it; the
    expansion stops at the role noun, which the acronym may include or not."""
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for t in titles:
        for m in _ACRONYM_RE.finditer(t or ""):
            words, acr = m.group(1).split(), m.group(2).lower()
            for n in range(len(acr), 1, -1):
                cand = words[-n:]
                if "".join(w[0].lower() for w in cand) == acr:
                    out[acr][" ".join(w.lower() for w in cand)] += 1
                    break
    # Kept only when defined one way and attested: defined twice, or written
    # out in full in at least three titles. One definition alone taught `ppc` =
    # `penitentiary psychiatric center` and `se` = `solutions engineer`.
    low = [(t or "").lower() for t in titles]
    keep = {}
    for a, c in out.items():
        if len(c) != 1:
            continue
        full, n = c.most_common(1)[0]
        if n >= 2 or sum(full in t for t in low) >= 3 + n:
            keep[a] = full
    return keep


