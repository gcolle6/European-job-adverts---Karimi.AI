"""A4 needs the raw segment TEXT, not an id — the reviewer has to read it.

The first draw emitted a vacancy id and a count, which reviews nothing. A4 is a
blind re-labelling: the reviewer reads the original sentence and writes out the
requirements they see, without being shown our split. So the item has to carry
the segment exactly as the employer wrote it, and nothing else.
"""
import json
import pathlib
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np

from karimi import atomise as atom, config, data

W3 = pathlib.Path(r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3")
SEED = 20260914
rng = np.random.default_rng(SEED)

base = data.build_analysis_base().df
long_segs = []
for vid, mh, lg in zip(base["vacancy_id"], base["must_have"], base["language"]):
    for s in atom.segments(str(mh)):
        s = s.strip()
        if len(s) > config.LONG_SEGMENT_CHARS:
            long_segs.append({"vacancy_id": str(vid), "segment": s, "language": str(lg)})

print(f"long segments in the corpus: {len(long_segs):,} "
      f"(over {config.LONG_SEGMENT_CHARS} characters)")

idx = rng.choice(len(long_segs), size=30, replace=False)
a4 = [{"n": i, "segment": long_segs[k]["segment"],
       "language": long_segs[k]["language"], "vacancy_id": long_segs[k]["vacancy_id"]}
      for i, k in enumerate(sorted(idx), 1)]

p = W3 / "review_sets.json"
payload = json.loads(p.read_text(encoding="utf-8"))
payload["a4"] = {
    "method": "random long segments (>120 characters), raw text only — our split "
              "is deliberately not shown, because a reviewer shown a split grades "
              "it instead of reproducing it",
    "items": a4,
}
p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"\nA4 replaced: {len(a4)} segments with their text")
for x in a4[:3]:
    print(f"  [{x['language']}] {x['segment'][:110]}")
print(f"\nmedian length: {int(np.median([len(x['segment']) for x in a4]))} characters")
print(f"written: {p.name}")
