#!/usr/bin/env sh
# The whole GCP setup, for a personal account (no organisation). NOT RUN YET.
# Read it, set the three variables, then run ONE STEP AT A TIME:
#
#   sh deploy/gcp_setup.sh 1      # ... up to 17
#
# Without an organisation the policy that refuses non-EU locations is not
# available (deploy/eu_setup.sh needs one), so REGION is written on every
# command below. Never drop it: a bucket without --location lands in the US,
# a build without --region runs in `global`.
#
# The guide that explains each step: "Guida: libreria, dizionario e API su GCP".
set -eu
# gcloud as winget installs it on Windows; harmless elsewhere.
# POSIX form on purpose: a Windows-form path here breaks gcloud's own wrapper.
export PATH="$PATH:/c/Users/giaco/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin"
# gcloud must not pick up another Python on PATH (uv's 3.14 did): use the one it ships with.
_bp="/c/Users/giaco/AppData/Local/Google/Cloud SDK/google-cloud-sdk/platform/bundledpython/python.exe"
[ -f "$_bp" ] && export CLOUDSDK_PYTHON="$_bp"

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID, e.g. karimi-normalise-1234}"
REGION="${REGION:-europe-west1}"          # open decision: europe-west1 (Belgium) or europe-west8 (Milan)
BILLING="${BILLING:-}"                     # gcloud billing accounts list
DICT_VERSION="${DICT_VERSION:-0.1.0}"

API_SA="karimi-api@${PROJECT_ID}.iam.gserviceaccount.com"
JOB_SA="karimi-job@${PROJECT_ID}.iam.gserviceaccount.com"
JOBS="gs://${PROJECT_ID}-jobs"
DICTS="gs://${PROJECT_ID}-dictionaries"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/karimi/karimi:${DICT_VERSION}"
CHECK_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/karimi/karimi-check:${DICT_VERSION}"

case "${1:?which step: 1-17}" in
1)  # the project, and the default for every later command
    gcloud projects create "$PROJECT_ID" --name="Karimi normalise"
    gcloud config set project "$PROJECT_ID"
    gcloud config set run/region "$REGION"
    ;;
2)  # billing, and a budget that warns at 50%, 90%, 100%. The amount is in the billing
    # account's own currency, which a currency code must match: 75 DKK is ~10 EUR
    gcloud billing projects link "$PROJECT_ID" --billing-account="${BILLING:?set BILLING}"
    gcloud services enable billingbudgets.googleapis.com
    gcloud billing budgets create --billing-account="$BILLING" --display-name="karimi" \
        --budget-amount="${BUDGET:-75}" --filter-projects="projects/${PROJECT_ID}" \
        --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
    ;;
3)  # the services used
    gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
        storage.googleapis.com iamcredentials.googleapis.com logging.googleapis.com \
        monitoring.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com
    ;;
4)  # Artifact Registry: images for Cloud Run, and the private Python package (deploy/release.sh)
    gcloud artifacts repositories create karimi --repository-format=docker --location="$REGION" \
        --description="karimi-normalise images"
    gcloud artifacts repositories create karimi-py --repository-format=python --location="$REGION" \
        --description="karimi-normalise, private"
    ;;
5)  # buckets: dictionaries (kept), jobs (deleted after 30 days)
    gcloud storage buckets create "$DICTS" --location="$REGION" --uniform-bucket-level-access
    gcloud storage buckets create "$JOBS" --location="$REGION" --uniform-bucket-level-access
    gcloud storage buckets update "$JOBS" --lifecycle-file=deploy/lifecycle.json
    ;;
6)  # the dictionary and its quality card into the bucket
    gcloud storage cp -r "New project/output/dictionaries/${DICT_VERSION}" "${DICTS}/"
    gcloud storage cp "New project/output/quality/quality_${DICT_VERSION}__${DICT_VERSION}.json" \
        "${DICTS}/${DICT_VERSION}/quality.json"
    ;;
7)  # two service accounts, each with the least it needs
    gcloud iam service-accounts create karimi-api --display-name="karimi API (Cloud Run service)"
    gcloud iam service-accounts create karimi-job --display-name="karimi batch (Cloud Run job)"
    for sa in "$API_SA" "$JOB_SA"; do
        gcloud storage buckets add-iam-policy-binding "$JOBS" --member="serviceAccount:$sa" \
            --role=roles/storage.objectAdmin
    done
    # the API signs upload and download URLs as itself, with no key file
    gcloud iam service-accounts add-iam-policy-binding "$API_SA" --member="serviceAccount:$API_SA" \
        --role=roles/iam.serviceAccountTokenCreator
    # the API key for the trial (decided 2026-11-05): a secret the service reads at start
    python -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
        gcloud secrets create karimi-api-key --data-file=- --replication-policy=user-managed \
            --locations="$REGION"
    gcloud secrets add-iam-policy-binding karimi-api-key --member="serviceAccount:$API_SA" \
        --role=roles/secretmanager.secretAccessor
    ;;
8)  # build the image in the EU and push it
    gcloud builds submit --region="$REGION" --config=deploy/cloudbuild.yaml \
        --substitutions="_REGION=${REGION},_DICT_VERSION=${DICT_VERSION},_TAG=${DICT_VERSION}"
    ;;
9)  # logs in the EU: a log bucket there, and the _Default sink pointed at it
    gcloud logging buckets create karimi-eu --location="$REGION" --retention-days=30
    gcloud logging sinks update _Default \
        "logging.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}/buckets/karimi-eu"
    ;;
10) # the batch job, then the API that starts it
    gcloud run jobs deploy karimi-batch --image="$IMAGE" --region="$REGION" \
        --service-account="$JOB_SA" --cpu=4 --memory=8Gi --task-timeout=24h --max-retries=0 \
        --command=python --args=-m,karimi_normalise.job --set-env-vars="KARIMI_STORE=${JOBS}"
    gcloud run jobs add-iam-policy-binding karimi-batch --region="$REGION" \
        --member="serviceAccount:$API_SA" --role=roles/run.developer
    gcloud iam service-accounts add-iam-policy-binding "$JOB_SA" --member="serviceAccount:$API_SA" \
        --role=roles/iam.serviceAccountUser
    # Reachable by anyone, refused by the app without the key (api.py): the
    # trial's access model. IAM-only would be --no-allow-unauthenticated plus step 12.
    gcloud run deploy karimi-api --image="$IMAGE" --region="$REGION" --service-account="$API_SA" \
        --allow-unauthenticated --concurrency=1 --cpu=2 --memory=4Gi \
        --min-instances=0 --max-instances=3 --timeout=900 \
        --set-secrets="KARIMI_API_KEY=karimi-api-key:latest" \
        --set-env-vars="KARIMI_STORE=${JOBS},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},KARIMI_RUN_JOB=projects/${PROJECT_ID}/locations/${REGION}/jobs/karimi-batch"
    ;;
11) # the check: health (open), then one posting with the key
    URL=$(gcloud run services describe karimi-api --region="$REGION" --format='value(status.url)')
    KEY=$(gcloud secrets versions access latest --secret=karimi-api-key)
    curl -s "$URL/health"; echo
    curl -s -X POST "$URL/v1/process" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
        -d '{"postings":[{"id":"t1","title":"Data Engineer","must_have":["3+ years of Python and SQL"]}],"translate":false}' \
        | head -c 400; echo
    ;;
12) # what to send the tester: the URL and the key (by a separate channel from each other)
    echo "URL: $(gcloud run services describe karimi-api --region="$REGION" --format='value(status.url)')"
    echo "KEY: $(gcloud secrets versions access latest --secret=karimi-api-key)"
    ;;
13) # the judge's reference, then its image. The model itself is fetched by Cloud
    #   Build from Hugging Face at a pinned commit and checked by sha256
    #   (deploy/cloudbuild_check.yaml): 2.5 GB is not worth uploading from here.
    gcloud storage cp "New project/output/tester/judge_reference_${DICT_VERSION}.json" \
        "${DICTS}/${DICT_VERSION}/judge_reference.json"
    gcloud builds submit --region="$REGION" --config=deploy/cloudbuild_check.yaml \
        --substitutions="_REGION=${REGION},_DICT_VERSION=${DICT_VERSION},_TAG=${DICT_VERSION}"
    ;;
14) # the check job (judge inside), the sweep job, and the batch job told to start the check
    gcloud run jobs deploy karimi-check --image="$CHECK_IMAGE" --region="$REGION" \
        --service-account="$JOB_SA" --cpu=4 --memory=8Gi --task-timeout=1h --max-retries=0 \
        --set-env-vars="KARIMI_STORE=${JOBS}"
    gcloud run jobs deploy karimi-sweep --image="$CHECK_IMAGE" --region="$REGION" \
        --service-account="$JOB_SA" --cpu=1 --memory=1Gi --task-timeout=10m --max-retries=0 \
        --args=--sweep --set-env-vars="KARIMI_STORE=${JOBS}"
    # the batch job starts the check as itself
    gcloud run jobs add-iam-policy-binding karimi-check --region="$REGION" \
        --member="serviceAccount:$JOB_SA" --role=roles/run.developer
    gcloud iam service-accounts add-iam-policy-binding "$JOB_SA" --member="serviceAccount:$JOB_SA" \
        --role=roles/iam.serviceAccountUser
    # the sweep asks Cloud Run how each execution ended
    gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$JOB_SA" \
        --role=roles/run.viewer
    gcloud run jobs update karimi-batch --region="$REGION" \
        --update-env-vars="KARIMI_RUN_CHECK=projects/${PROJECT_ID}/locations/${REGION}/jobs/karimi-check"
    # the API starts a check after every /v1/process call too
    gcloud run jobs add-iam-policy-binding karimi-check --region="$REGION" \
        --member="serviceAccount:$API_SA" --role=roles/run.developer
    gcloud run services update karimi-api --region="$REGION" \
        --update-env-vars="KARIMI_RUN_CHECK=projects/${PROJECT_ID}/locations/${REGION}/jobs/karimi-check"
    ;;
15) # the sweep every morning at 06:00: finds runs that died without a word
    gcloud run jobs add-iam-policy-binding karimi-sweep --region="$REGION" \
        --member="serviceAccount:$JOB_SA" --role=roles/run.invoker
    gcloud scheduler jobs create http karimi-sweep --location="$REGION" --schedule="0 6 * * *" \
        --time-zone="Europe/Rome" --http-method=POST \
        --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/karimi-sweep:run" \
        --oauth-service-account-email="$JOB_SA"
    ;;
16) # the alert: an email when a check is red, or a check could not run
    email="${2:?your email}"
    gcloud logging metrics create karimi_red --description="karimi check red, or check failed" \
        --log-filter='jsonPayload.event=("karimi_check" OR "karimi_check_failed" OR "karimi_judge_not_started") AND severity>=ERROR'
    channel=$(gcloud beta monitoring channels create --display-name="karimi" --type=email \
        --channel-labels=email_address="$email" --format='value(name)')
    sed "s#CHANNEL#${channel}#" deploy/alert_policy.json > "${TMPDIR:-/tmp}/karimi_alert.json"
    gcloud alpha monitoring policies create --policy-from-file="${TMPDIR:-/tmp}/karimi_alert.json"
    ;;
17) # observability: a metric from the timing lines, and the dashboard (deploy/dashboard.json)
    gcloud logging metrics create karimi_chunk_seconds --description="seconds per chunk of postings" \
        --log-filter='jsonPayload.event="karimi_timing"' --value-extractor='EXTRACT(jsonPayload.seconds)' \
        --bucket-name=karimi-eu 2>/dev/null || \
    gcloud logging metrics create karimi_chunk_seconds --description="seconds per chunk of postings" \
        --log-filter='jsonPayload.event="karimi_timing"' --value-extractor='EXTRACT(jsonPayload.seconds)'
    gcloud monitoring dashboards create --config-from-file=deploy/dashboard.json
    echo "Logs Explorer query for one job:  jsonPayload.job=\"<id>\""
    ;;
esac
