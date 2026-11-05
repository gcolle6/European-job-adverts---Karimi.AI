#!/usr/bin/env sh
# Phase 0: EU-only foundations. NOT RUN YET — read, set the variables, then run
# one block at a time. Needs an organisation (the location policy is set at
# org or folder level) and the right IAM roles.
#
# Done when: creating a bucket in us-central1 is REFUSED (last block).
set -eu

ORG_ID="<org id>"
PROJECT_ID="<project id>"
REGION="europe-west1"          # open decision: europe-west1 (Belgium) or europe-west8 (Milan)
BILLING="<billing account>"

# 1. Resources may only be created in EU locations.
gcloud resource-manager org-policies allow constraints/gcp.resourceLocations \
    in:eu-locations --project="$PROJECT_ID"

# 2. Logs: the _Default bucket is `global` unless the default location is set
#    BEFORE the project's buckets are created.
gcloud logging settings update --organization="$ORG_ID" --storage-location="$REGION"

# 3. Services, all regional.
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    storage.googleapis.com bigquery.googleapis.com cloudscheduler.googleapis.com \
    aiplatform.googleapis.com --project="$PROJECT_ID"
gcloud artifacts repositories create karimi --repository-format=docker \
    --location="$REGION" --project="$PROJECT_ID"
gcloud storage buckets create "gs://karimi-dictionaries-eu" --location="$REGION" \
    --uniform-bucket-level-access --project="$PROJECT_ID"
bq --location="$REGION" mk --dataset "$PROJECT_ID:karimi"

# 4. Budget alert.
gcloud billing budgets create --billing-account="$BILLING" --display-name="karimi" \
    --budget-amount=50EUR --threshold-rule=percent=0.5 --threshold-rule=percent=0.9

# 5. The check: this must FAIL with a location-policy error.
if gcloud storage buckets create "gs://karimi-policy-check-$$" --location=us-central1 \
        --project="$PROJECT_ID" 2>/dev/null; then
    echo "POLICY NOT ACTIVE: a US bucket was created"; exit 1
fi
echo "ok: non-EU location refused"
