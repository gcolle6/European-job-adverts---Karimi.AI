"""Alert, timing metric and dashboard through the REST APIs (steps 16-17 without gcloud alpha/beta).

    python deploy/monitoring_setup.py --project <id> --email <you@example.com>

gcloud's `monitoring` commands are in its alpha and beta components, which on
Windows install in a separate window. The same objects through the APIs, with
the token of `gcloud auth print-access-token`. Idempotent by display name:
run it twice and nothing is created twice.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent


def token() -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    return subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True,
                          check=True, shell=gcloud.endswith(".cmd")).stdout.strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--email", required=True)
    a = p.parse_args()
    h = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json",
         "x-goog-user-project": a.project}
    mon = f"https://monitoring.googleapis.com/v3/projects/{a.project}"
    log = f"https://logging.googleapis.com/v2/projects/{a.project}"

    # 1. the timing metric: a distribution of seconds per chunk, from the job's log lines
    metric = {"name": "karimi_chunk_seconds", "description": "seconds per chunk of postings (karimi_timing)",
              "filter": 'jsonPayload.event="karimi_timing"', "valueExtractor": "EXTRACT(jsonPayload.seconds)",
              "metricDescriptor": {"metricKind": "DELTA", "valueType": "DISTRIBUTION", "unit": "s"},
              "bucketOptions": {"exponentialBuckets": {"numFiniteBuckets": 20, "growthFactor": 1.6, "scale": 1}}}
    r = requests.post(f"{log}/metrics", headers=h, json=metric)
    print("metric karimi_chunk_seconds:", r.status_code if r.status_code != 409 else "exists")

    # 2. the email channel
    chans = requests.get(f"{mon}/notificationChannels", headers=h).json().get("notificationChannels", [])
    chan = next((c["name"] for c in chans if c.get("displayName") == "karimi"), None)
    if not chan:
        r = requests.post(f"{mon}/notificationChannels", headers=h, json={
            "type": "email", "displayName": "karimi", "labels": {"email_address": a.email}})
        r.raise_for_status()
        chan = r.json()["name"]
    print("channel:", chan)

    # 3. the alert on karimi_red
    pols = requests.get(f"{mon}/alertPolicies", headers=h).json().get("alertPolicies", [])
    policy = json.loads((HERE / "alert_policy.json").read_text(encoding="utf-8"))
    policy["notificationChannels"] = [chan]
    if not any(x.get("displayName") == policy["displayName"] for x in pols):
        r = requests.post(f"{mon}/alertPolicies", headers=h, json=policy)
        print("alert:", r.status_code, r.text[:200] if r.status_code >= 300 else r.json()["name"])
    else:
        print("alert: exists")

    # 4. the dashboard
    dash = json.loads((HERE / "dashboard.json").read_text(encoding="utf-8"))
    dl = requests.get(f"https://monitoring.googleapis.com/v1/projects/{a.project}/dashboards", headers=h)
    if not any(x.get("displayName") == dash["displayName"] for x in dl.json().get("dashboards", [])):
        r = requests.post(f"https://monitoring.googleapis.com/v1/projects/{a.project}/dashboards", headers=h, json=dash)
        print("dashboard:", r.status_code, r.text[:300] if r.status_code >= 300 else r.json()["name"])
    else:
        print("dashboard: exists")
    print(f"open: https://console.cloud.google.com/monitoring/dashboards?project={a.project}")


if __name__ == "__main__":
    main()
