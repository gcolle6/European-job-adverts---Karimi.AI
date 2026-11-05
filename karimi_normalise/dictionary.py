"""The frozen dictionary: where a requirement or a title nobody has seen goes.

The batch (`New project/group_requirements.py`, `normalise_titles.py`) groups
the whole corpus at once, so a single new posting has no group of its own.
The dictionary freezes one batch run (`freeze.py`) and a new item is LOOKED UP
in it:

* the same (head group, core) as a known one: its group and topic;
* otherwise the nearest known core in the same head group, with the same
  names (`normalise_req.names`):

  - cosine >= ``group_threshold`` (0.90) -> that core's group and topic;
  - cosine >= ``topic_threshold`` (0.80) -> its topic only;
  - below -> ``nuovo``: counted, and left for the next freeze to place.

A title goes to the group of its key; failing that, to the group of a known
role it is a spelling variant of (`normalise_title.variants`: plural,
`Fullstack` / `Full Stack`, acronyms, the Developer = Engineer list), as the
batch would have joined them; otherwise ``nuovo``.

The embedding model is the one the dictionary was made with, named in its
manifest, and no other: the vectors and the 0.90 / 0.80 thresholds belong to
that model's scale. When it is not installed, cores the dictionary does not
hold come back ``non_cercato`` (not looked up), never ``nuovo`` (looked up and
not found), so the run report does not mistake one for the other.

⚠️ Lookup is not the batch. The batch joins each core to its most FREQUENT
neighbour above the threshold; lookup takes the NEAREST. So the two can differ;
`reference.py` measures by how much on postings the dictionary did not see.

A dictionary is a directory with a ``manifest.json`` (version, thresholds, the
rules that made it, the sha256 of each file) and the tables beside it. It is
never edited in place: an improvement is a new freeze with a new version, and
`freeze.diff` says what moved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from karimi import normalise_req
from karimi import normalise_title as nt

FILES = ["req_cores.parquet", "req_vectors.npy", "titles.parquet", "title_acronyms.json"]


@dataclass(frozen=True)
class ReqMatch:
    group: str          # `req_group`, "" when only the topic is known or nothing is
    topic: str          # `req_topic`, "" when `nuovo`
    status: str         # known | group | topic | nuovo | empty | non_cercato
    cosine: float | None = None
    via: str = ""       # the known core it was matched to


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Dictionary:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        for f, digest in manifest["sha256"].items():
            if sha256(self.path / f) != digest:
                raise ValueError(f"{f} does not match its manifest: the dictionary was edited "
                                 "in place. Freeze a new version instead.")
        t = pd.read_parquet(self.path / "titles.parquet")
        ref = self.path / "reference.json"
        self._setup(manifest, pd.read_parquet(self.path / "req_cores.parquet"),
                    np.load(self.path / "req_vectors.npy"), t,
                    json.loads((self.path / "title_acronyms.json").read_text(encoding="utf-8")),
                    json.loads(ref.read_text(encoding="utf-8")) if ref.exists() else None)
        self._model = None

    @classmethod
    def from_tables(cls, manifest: dict, cores: pd.DataFrame, vectors: np.ndarray,
                    titles: pd.DataFrame, acronyms: dict, encoder=None) -> "Dictionary":
        """An in-memory dictionary, for measuring one before it is frozen (`reference.py`)."""
        d = cls.__new__(cls)
        d.path, d._model = None, None
        d._setup(manifest, cores.reset_index(drop=True), vectors, titles, acronyms, None)
        if encoder is not None:
            d._encode = encoder
        return d

    def _setup(self, manifest, cores, vectors, titles, acronyms, reference) -> None:
        self.manifest = manifest
        self.version = manifest["dict_version"]
        self.group_threshold = manifest["group_threshold"]
        self.topic_threshold = manifest["topic_threshold"]
        self.cores = cores
        self.vectors = vectors.astype(np.float32)
        self.reference = reference
        self._exact = {(h, c): i for i, (h, c) in enumerate(zip(cores.req_head_group, cores.req_core))}
        self._topic_of = dict(zip(cores.req_group, cores.req_topic))
        # Candidates share the head group AND the names, so the index is by both.
        buckets: dict[tuple, list[int]] = {}
        for i, (h, c) in enumerate(zip(cores.req_head_group, cores.req_core)):
            buckets.setdefault((h, normalise_req.names(c)), []).append(i)
        self._bucket = {k: np.array(v) for k, v in buckets.items()}
        self._title_group = dict(zip(titles.title_key, titles.title_group))
        self._title_name = dict(zip(titles.title_group, titles.title_name))
        self.acronyms = acronyms
        # Dictionaries frozen before 2026-11-04 carry keys only, and no variants.
        self._title_variant: dict[str, str] = {}
        self._singular = nt.make_singular({t for k in titles.title_key for t in k.split()})
        if "title_role" in titles:
            for role, g in zip(titles.title_role, titles.title_group):
                for v in nt.variants(role, self._singular, acronyms):
                    self._title_variant.setdefault(v, g)

    # --- requirements ---------------------------------------------------------

    def _encode(self, texts: list[str]) -> np.ndarray:
        from karimi import embed
        if self._model is None:
            self._model = embed.load_model(self.manifest["embed_model"])
        return embed.encode(self._model, texts).astype(np.float32)

    def lookup_requirements(self, parts: list[tuple[str, str]]) -> list[ReqMatch]:
        """(head group, core) -> match, for many at once: unknown cores are embedded together."""
        out: list[ReqMatch | None] = [self._known(h, c) for h, c in parts]
        todo = [k for k, m in enumerate(out) if m is None]
        if todo:
            try:
                vecs = self._encode([parts[k][1] for k in todo])
            except ImportError:
                # `pip install karimi-normalise[embed]` is missing.
                for k in todo:
                    out[k] = ReqMatch("", "", "non_cercato")
                return out
            for k, v in zip(todo, vecs):
                out[k] = self._nearest(*parts[k], v)
        return out

    def _known(self, head: str, core: str) -> ReqMatch | None:
        if not core.strip():
            return ReqMatch("", "", "empty")
        i = self._exact.get((head, core))
        if i is None and head == "":
            # A bare core is the competence with that core (`Python` / `Python
            # skills`), as in the batch: on an identical core only.
            g = "competence: " + core.casefold()
            if g in self._topic_of:
                return ReqMatch(g, self._topic_of[g], "known", 1.0, core)
        if i is None:
            return None
        r = self.cores.iloc[i]
        return ReqMatch(r.req_group, r.req_topic, "known", 1.0, core)

    def _nearest(self, head: str, core: str, v: np.ndarray) -> ReqMatch:
        idx = self._bucket.get((head, normalise_req.names(core)))
        if idx is None:
            return ReqMatch("", "", "nuovo")
        sims = self.vectors[idx] @ v
        j = int(sims.argmax())
        s, r = float(sims[j]), self.cores.iloc[idx[j]]
        if s >= self.group_threshold:
            return ReqMatch(r.req_group, r.req_topic, "group", s, r.req_core)
        if s >= self.topic_threshold:
            return ReqMatch("", r.req_topic, "topic", s, r.req_core)
        return ReqMatch("", "", "nuovo", s, r.req_core)

    # --- titles ---------------------------------------------------------------

    def lookup_title(self, role: str) -> tuple[str, str, str, str]:
        """(title_key, title_group, title_name, status): known | variant | nuovo."""
        k = nt.key(role, self.acronyms)
        g = self._title_group.get(k, "")
        status = "known" if g else "nuovo"
        if not g:
            for v in sorted(nt.variants(role, self._singular, self.acronyms)):
                if v in self._title_variant:
                    g, status = self._title_variant[v], "variant"
                    break
        return k, g, self._title_name.get(g, ""), status
