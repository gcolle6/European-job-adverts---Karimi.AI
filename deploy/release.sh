#!/usr/bin/env sh
# Release a version to Karimi: the CD half of CI/CD. NOT RUN YET.
#
# Private first (decided 2026-11-04): the package goes to a Python repository
# in Artifact Registry, the dictionary to a bucket, both in an EU region, read
# only by the accounts given access. PyPI, public, comes later and carries the
# code only: the dictionary is made from Karimi's ads and stays private unless
# they agree otherwise.
#
#   sh deploy/release.sh setup              # once: repository, bucket, access
#   sh deploy/release.sh grant dev@karimi.ai # once per reader
#   sh deploy/release.sh 0.1.0              # every release
#
# Without a Google Cloud ORGANISATION (a personal account has none) the policy
# that refuses non-EU locations is not available: the region is set here, on
# every resource, and nothing in this script creates one without it.
set -eu

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-europe-west1}"          # open decision: europe-west1 (Belgium) or europe-west8 (Milan)
REPO="karimi-py"
BUCKET="gs://${PROJECT_ID}-karimi-dictionaries"
PY="${KARIMI_PYTHON:-python}"
INDEX="https://${REGION}-python.pkg.dev/${PROJECT_ID}/${REPO}/"
DICTS="New project/output/dictionaries"
CARDS="New project/output/quality"

case "${1:?usage: release.sh setup | grant <email> | <version>}" in
setup)
    gcloud services enable artifactregistry.googleapis.com storage.googleapis.com --project="$PROJECT_ID"
    gcloud artifacts repositories create "$REPO" --repository-format=python \
        --location="$REGION" --project="$PROJECT_ID" --description="karimi-normalise, private"
    gcloud storage buckets create "$BUCKET" --location="$REGION" \
        --uniform-bucket-level-access --project="$PROJECT_ID"
    ;;
grant)
    who="${2:?email}"
    gcloud artifacts repositories add-iam-policy-binding "$REPO" --location="$REGION" \
        --project="$PROJECT_ID" --member="user:$who" --role=roles/artifactregistry.reader
    gcloud storage buckets add-iam-policy-binding "$BUCKET" --member="user:$who" \
        --role=roles/storage.objectViewer
    ;;
*)
    v="$1"
    [ -f "$DICTS/$v/manifest.json" ] || { echo "no dictionary $v"; exit 1; }
    # 1. CI: every check, the slow gates included. A failing gate stops the release.
    "$PY" -m pytest -q tests
    # 2. The package, and the quality card it is released with.
    rm -rf dist && "$PY" -m pip wheel --no-deps -w dist .
    [ -f "$CARDS/quality_${v}__${v}.json" ] || "$PY" -m karimi_normalise.quality --dict "$v"
    # 3. Upload: package to the repository, dictionary and card to the bucket.
    "$PY" -m twine upload --repository-url "$INDEX" dist/*.whl
    gcloud storage cp -r "$DICTS/$v" "$BUCKET/$v"
    gcloud storage cp "$CARDS/quality_${v}__${v}.json" "$BUCKET/$v/quality.json"
    echo "released $v"
    echo "Karimi installs with:"
    echo "  pip install keyring keyrings.google-artifactregistry-auth"
    echo "  gcloud auth application-default login"
    echo "  pip install --extra-index-url ${INDEX}simple/ 'karimi-normalise[all]==$v'"
    echo "  gcloud storage cp -r $BUCKET/$v dictionaries/"
    ;;
esac
