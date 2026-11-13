"""Which rules made an output, so every output can be traced and redone.

Two versions travel with every result (`PIANO_SVILUPPO.md`, phase 1):

* ``RULES_VERSION`` — the split and normalisation rules. Bumped by hand on
  every rule change, with a line in `karimi_normalise/CHANGELOG.md`;
* ``dict_version`` — the frozen dictionary, read from its manifest
  (`dictionary.py`), because the dictionary is data, not code.

A version bumped by hand can be forgotten, so ``RULES_FINGERPRINT`` pins the
rule sources themselves: `tests/test_library.py` fails when the code changes
and the fingerprint does not. Forgetting is then a red build, not a silent
change under the same version number.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

RULES_VERSION = "0.4.1"
RULES_FINGERPRINT = "2059ceca7cabe512"

ROOT = Path(__file__).resolve().parents[1]
# Every file whose change can change an output. `config.py` holds analysis
# thresholds too, so some bumps will be for nothing: cheaper than a silent one.
RULE_SOURCES = ["karimi/atomise.py", "karimi/normalise_req.py", "karimi/normalise_title.py",
                "karimi/pos.py", "karimi/language.py", "karimi/config.py",
                "karimi_normalise/translate.py", "karimi_normalise/requirements.py",
                "karimi_normalise/titles.py", "karimi_normalise/dictionary.py",
                "karimi_normalise/process.py", "karimi_normalise/casing.json"]


def fingerprint() -> str:
    """Hash of the rule sources, line endings ignored (the folder is in OneDrive)."""
    h = hashlib.sha256()
    for rel in RULE_SOURCES:
        h.update(rel.encode())
        h.update((ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]
