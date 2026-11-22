"""Retest: earlier batches run again under today's rules, ON THIS MACHINE, never published.

Decided 2026-11-19/20: every four batches, the postings of the previous four
are run again with the current rules and dictionary, to see how much the
model improved overall. The results are ours: they go to no bucket, no
history and no page of the site.

    python "New project/retest_batches.py"            # batches 1-4
    python "New project/retest_batches.py" 5 6 7 8    # when the job ids are added below

It takes the production code paths (`job.run`, then `check.check` with the
local judge at http://127.0.0.1:8080), a local store under
`New project/output/retests/<rules version>/`, the frozen dictionary and the
curator's resolved spellings. The originals are copied from the bucket
READ-ONLY with `gcloud storage cp`. Explorer (Gemini) off.

The comparison is the retest against the ORIGINAL OUTPUT READ BY TODAY'S
INSPECTOR (`check.retest_baseline`), never against the colour of the day: the
inspector learns new kinds between batches, so the old colours are not
comparable. First run, 2026-11-19, 0.4.6 / 0.3.7: batch 1 15.0% -> 7.2%,
2 15.6% -> 6.4%, 3 14.5% -> 5.1%, 4 8.1% -> 6.0%.
"""

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# the batches' original jobs (client_log.jsonl of each batch folder)
JOBS = {1: "4e0ddade887f5fd1", 2: "c912c7c114abe681", 3: "98f8655ab9bf0230", 4: "07b7429290f06593",
        5: "f76845a0cb2038e4"}
BUCKET = "gs://karimi-normalise-2026-jobs"
SDK = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Cloud SDK/google-cloud-sdk"


def gcloud_cp(src: str, dst: Path) -> None:
    """Read-only copy from the bucket. Through gcloud.py with the bundled python:
    gcloud.cmd re-parses its arguments through cmd.exe."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(SDK / "platform/bundledpython/python.exe"), str(SDK / "lib/gcloud.py"),
                    "storage", "cp", src, str(dst)], check=True, capture_output=True)


def main() -> int:
    from karimi_normalise import Dictionary, job
    from karimi_normalise.dashboard import _retest
    from karimi_normalise.freeze import STORE
    from karimi_normalise.store import LocalStore, jf, write_json
    from karimi_normalise.versions import RULES_VERSION

    dict_dir = sorted(STORE.glob("[0-9]*/manifest.json"),
                      key=lambda p: tuple(int(x) for x in p.parent.name.split(".")))[-1].parent
    os.environ["KARIMI_DICT"] = str(dict_dir)
    os.environ.setdefault("KARIMI_JUDGE_URL", "http://127.0.0.1:8080")
    os.environ.setdefault("KARIMI_JUDGE_REFERENCE", str(ROOT / "judge_reference.json"))
    for k in ("KARIMI_RUN_CHECK", "KARIMI_RUN_JOB", "KARIMI_EXPLORER"):
        os.environ.pop(k, None)

    out_dir = ROOT / "New project/output/retests" / RULES_VERSION
    local = LocalStore(out_dir / "store")
    gcloud_cp(f"{BUCKET}/curator/aliases.jsonl", out_dir / "store/curator/aliases.jsonl")
    d = Dictionary(os.environ["KARIMI_DICT"])
    results_file = out_dir / "results.json"
    out = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    for k in [int(x) for x in sys.argv[1:]] or [1, 2, 3, 4]:
        orig = JOBS[k]
        for name in ("results.jsonl", "check.json", "status.json"):
            gcloud_cp(f"{BUCKET}/jobs/{orig}/{name}", out_dir / "store" / jf(orig, name))
        new = secrets.token_hex(8)
        local.write_text(jf(new, "input.jsonl"),
                         (ROOT / f"New project/output/new_postings/batch_{k:02d}/postings.jsonl")
                         .read_text(encoding="utf-8"))
        write_json(local, jf(new, "status.json"), {"job": new, "source": "job", "state": "queued",
                                                  "translate": True, "retest_of": orig,
                                                  "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
        t0 = time.time()
        print(f"=== batch {k}: retest {new} of {orig}, dictionary {dict_dir.name}", flush=True)
        job.run(new, local, d)
        line = [json.loads(x) for x in local.read_text("history/runs.jsonl").splitlines() if x.strip()][-1]
        assert line["job"] == new
        out[str(k)] = {**_retest(line), "minutes": round((time.time() - t0) / 60, 1)}
        print(f"=== batch {k}: {json.dumps(out[str(k)])}", flush=True)
        results_file.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
