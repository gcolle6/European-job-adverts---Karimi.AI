"""Where a job's files live: a local folder, or a Cloud Storage bucket.

    KARIMI_STORE=./jobs                      # local: tests, and a first try on this machine
    KARIMI_STORE=gs://<project>-jobs         # GCP: the bucket in the EU region

One interface for both, so the API and the job run the same code here and on
Cloud Run. A job is a folder, `jobs/<id>/`:

* `input.jsonl`    one posting per line, as `process` takes it;
* `status.json`    state, postings done and total, times, error;
* `results.jsonl`  one posting per line: id, requirements, title;
* `report.json`    the run report over the whole job;
* `check.json`     what the check found (`check.py`).

`history/runs.jsonl` is the check's memory across jobs: one line per job,
counts and lights only, no text. It sits outside `jobs/` so the bucket's
30-day deletion (`deploy/lifecycle.json`, prefix `jobs/`) leaves it.

Nothing here logs text: the job files hold requirement text, the logs do not.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

UPLOAD_MINUTES = 60
DOWNLOAD_MINUTES = 60


class LocalStore:
    """A folder. Upload and download go through the API itself (`/v1/jobs/{id}/input`)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _p(self, name: str) -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_text(self, name: str, text: str) -> None:
        tmp = self._p(name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._p(name))          # a reader never sees half a status

    def read_text(self, name: str) -> str | None:
        p = self.root / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    def open_write(self, name: str):
        return self._p(name).open("w", encoding="utf-8")

    def open_read(self, name: str):
        return (self.root / name).open(encoding="utf-8")

    def exists(self, name: str) -> bool:
        return (self.root / name).exists()

    def jobs(self) -> list[str]:
        d = self.root / "jobs"
        return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []

    def upload_url(self, name: str, base_url: str) -> dict:
        job = name.split("/")[1]
        return {"method": "PUT", "url": f"{base_url}/v1/jobs/{job}/input",
                "headers": {"Content-Type": "application/x-ndjson"}}

    def download_url(self, name: str, base_url: str) -> str:
        _, job, file = name.split("/", 2)
        return f"{base_url}/v1/jobs/{job}/files/{file}"


class GCSStore:
    """A bucket. Upload and download use signed URLs: one file, one place, one hour."""

    def __init__(self, url: str):
        from google.cloud import storage

        self.bucket_name = url.removeprefix("gs://").strip("/")
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def write_text(self, name: str, text: str) -> None:
        self.bucket.blob(name).upload_from_string(text, content_type="application/json")

    def read_text(self, name: str) -> str | None:
        b = self.bucket.blob(name)
        return b.download_as_text() if b.exists() else None

    def open_write(self, name: str):
        return self.bucket.blob(name).open("w", encoding="utf-8")

    def open_read(self, name: str):
        return self.bucket.blob(name).open("r", encoding="utf-8")

    def exists(self, name: str) -> bool:
        return self.bucket.blob(name).exists()

    def jobs(self) -> list[str]:
        it = self.client.list_blobs(self.bucket_name, prefix="jobs/", delimiter="/")
        list(it)                                  # the prefixes are filled while pages are read
        return sorted(p.split("/")[1] for p in it.prefixes)

    def _signed(self, name: str, method: str, minutes: int, content_type: str | None = None) -> str:
        # On Cloud Run there is no key file: the service account signs through
        # the IAM API, which needs `iam.serviceAccountTokenCreator` on itself.
        import google.auth
        from google.auth.transport import requests

        creds, _ = google.auth.default()
        creds.refresh(requests.Request())
        return self.bucket.blob(name).generate_signed_url(
            version="v4", expiration=dt.timedelta(minutes=minutes), method=method,
            content_type=content_type, service_account_email=creds.service_account_email,
            access_token=creds.token)

    def upload_url(self, name: str, base_url: str) -> dict:
        ct = "application/x-ndjson"
        return {"method": "PUT", "url": self._signed(name, "PUT", UPLOAD_MINUTES, ct),
                "headers": {"Content-Type": ct}}

    def download_url(self, name: str, base_url: str) -> str:
        return self._signed(name, "GET", DOWNLOAD_MINUTES)


def open_store(where: str | None = None):
    where = where or os.environ.get("KARIMI_STORE", "jobs")
    return GCSStore(where) if where.startswith("gs://") else LocalStore(where)


def jf(job: str, name: str) -> str:
    """The store name of one of a job's files."""
    return f"jobs/{job}/{name}"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(store, name: str) -> dict | None:
    t = store.read_text(name)
    return json.loads(t) if t else None


def write_json(store, name: str, value: dict) -> None:
    store.write_text(name, json.dumps(value, ensure_ascii=False, indent=1))
