"""The group-merging method, run end to end — the version that survives new data.

Prints what each signal contributes, so the boundary between what is solved and
what is left for a person is visible rather than asserted.
"""
import sys

sys.path.insert(0, r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai")

import numpy as np
import pandas as pd

from karimi import cluster as cl

OUT = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 2\output"
W1 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 1\output"
W3 = r"C:\Users\giaco\OneDrive\Desktop\Karimi.ai\week 3"
pd.set_option("display.width", 250)

named = pd.read_csv(OUT + r"\cluster_dictionary_named.csv")
z = np.load(OUT + r"\cluster_centroids.npz", allow_pickle=True)
reqs = pd.read_parquet(W1 + r"\requirements.parquet")
asg = pd.read_parquet(OUT + r"\phrase_clusters.parquet")

a = cl.merge_aliases(named, z["cluster_ids"], z["centroids"])
print(f"labels only        {a['n_groups_before']} -> {a['n_groups_after']} groups   "
      f"families {len(a['families'])}   largest {a['largest_family']}   "
      f"accepted {len(a['accepted'])}  rejected {len(a['rejected'])}")

vocab = cl.member_vocabulary(asg, reqs)
try:
    b = cl.merge_aliases(named, z["cluster_ids"], z["centroids"], vocab=vocab)
    print(f"+ member vocabulary {b['n_groups_before']} -> {b['n_groups_after']} groups   "
          f"families {len(b['families'])}   largest {b['largest_family']}   "
          f"accepted {len(b['accepted'])}  rejected {len(b['rejected'])}")
    print("")
    print("what each signal contributed:")
    print(b["accepted"]["why"].str.replace(r"^(?!identical|member).*$", "shared name",
                                           regex=True).value_counts().head(6).to_string())
    print("")
    print("merges that ONLY the member-vocabulary signal found:")
    extra = b["accepted"][b["accepted"]["why"].str.startswith("member overlap")]
    lab = dict(zip(named["cluster"], named["label"]))
    for x in extra.nlargest(12, "overlap").itertuples():
        print(f"  {x.overlap:.3f}  {str(lab.get(x.a))[:34]:<36} + {str(lab.get(x.b))[:34]}")
except ValueError as e:
    print(f"+ member vocabulary  GUARD FIRED: {e}")
    print("\n  This is the guard doing its job: adding the third signal chains")
    print("  credential groups into one component, which is the documented blind")
    print("  spot. Use vocab=None until that family is resolved by adjudication.")

pd.DataFrame({"cluster": list(a["alias"]), "merged_into": list(a["alias"].values())}
             ).to_csv(W3 + r"\alias_table.csv", index=False, encoding="utf-8")
a["rejected"].to_csv(W3 + r"\merge_rejected_for_review.csv", index=False, encoding="utf-8")
print(f"\nwritten: alias_table.csv, merge_rejected_for_review.csv "
      f"({len(a['rejected'])} pairs for a person)")
