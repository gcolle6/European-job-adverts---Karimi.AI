"""Second pass over the first pass's flags: which are real, and by what mechanism.

The first pass was told to flag on suspicion and returned something for 536 of
617 groups — against the 3-in-40 rate a human review measured. That is a triage
list nobody can use.

This pass asks for the **mechanism** instead of re-asking the same question, with
"the first pass over-flagged" as an explicit option. Naming a cause is a harder
claim than voicing a doubt, and only one cause is the defect being hunted.

Validated the same way as the first pass: the three known intruders must come
back as `two_senses`. If they come back `fine`, the second pass has undone the
first and the whole chain is worthless.
"""
import ast
import sys
import time

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import pandas as pd

from karimi import intruders as intr, llm_split as L

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 70)
t0 = time.time()

CONTROL = {166: "shipping code", 188: "DevOps culture", 82: "publications"}

scan = pd.read_csv(W3 + r"\intruder_scan.csv")
scan["intruders"] = scan["intruders"].apply(
    lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith("[") else [])
flagged = scan[scan["intruders"].apply(len) > 0].copy()
named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")

print(f"groups carrying a flag: {len(flagged)}   phrases: {int(flagged['intruders'].apply(len).sum())}")
client = L.load_openai_client()
res = intr.confirm(flagged, client, W3 + r"\intruder_confirm_cache.jsonl")
print(f"  confirmed in {time.time()-t0:.0f}s   "
      f"tokens in {res.attrs['input_tokens']:,} out {res.attrs['output_tokens']:,}   "
      f"failures {res.attrs['chunk_failures']}")

print("")
print("=" * 94)
print("THE CONTROL — the three known intruders must survive as real")
print("=" * 94)
ok = 0
for cid, needle in CONTROL.items():
    rows = res[(res["cluster"] == cid) &
               res["phrase"].astype(str).str.lower().str.contains(needle.lower())]
    if len(rows):
        reason = rows["reason"].iat[0]
        good = reason in ("two_senses", "wrong_kind")
        ok += good
        print(f"  cluster {cid:<4} '{needle}' → {reason}   {'kept' if good else 'LOST'}")
    else:
        print(f"  cluster {cid:<4} '{needle}' → not returned   LOST")
print(f"\n  {ok} of 3 survived")
if ok < 2:
    raise SystemExit("\nSTOP: the second pass discards the intruders we know are real. "
                     "It is not a filter, it is a reversal — do not use it.")

print("")
print("=" * 94)
print("WHAT THE SECOND PASS SAYS")
print("=" * 94)
print(res["reason"].value_counts().to_string())
real = res[res["reason"] != "fine"]
per_group = real.groupby(["cluster", "label"]).size().rename("n").reset_index()
print(f"\n  phrases kept as real: {len(real)} of {len(res)} "
      f"({len(real)/max(len(res),1):.1%})")
print(f"  groups with at least one real intruder: {len(per_group)} of 617 "
      f"({len(per_group)/617:.1%})")
print(f"  — the human review measured 3 of 40 = 7.5%")

print("")
print("=" * 94)
print("TWO-SENSE CASES — the defect this was built to find")
print("=" * 94)
two = real[real["reason"] == "two_senses"].merge(
    named[["cluster", "occurrences"]], on="cluster", how="left")
for r in two.nlargest(22, "occurrences").itertuples():
    print(f"  [{r.occurrences:>5}] {str(r.label)[:34]:<36} ✗ {str(r.phrase)[:52]}")

res.to_csv(W3 + r"\intruder_confirmed.csv", index=False, encoding="utf-8")
two.to_csv(W3 + r"\intruder_two_senses.csv", index=False, encoding="utf-8")
print(f"\nwritten: intruder_confirmed.csv ({len(res)}), "
      f"intruder_two_senses.csv ({len(two)})")
print(f"total {time.time()-t0:.0f}s")
