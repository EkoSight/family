#!/usr/bin/env bash
# One-command deploy of the Ekosight CEO Agent to Google Cloud Run.
#
# Prerequisites (once):
#   1. Install the gcloud CLI:  https://cloud.google.com/sdk/docs/install
#   2. gcloud auth login
#   3. Have a billing-enabled GCP project id ready.
#
# Usage:
#   PROJECT_ID=my-proj ./deploy/deploy.sh
#   # optional overrides:
#   REGION=asia-south1 SERVICE=ceo-agent DATABASE_URL=postgresql+psycopg://... ./deploy/deploy.sh
#
# By default it deploys with SQLite (fine for a first look, but the DB resets on
# every new revision / scaled instance). For real multi-user use, set
# DATABASE_URL to a Cloud SQL Postgres instance — see deploy/README.md.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID=your-gcp-project-id}"
REGION="${REGION:-asia-south1}"          # Mumbai; change if you prefer
SERVICE="${SERVICE:-ceo-agent}"
CEO_NAME="${CEO_NAME:-Dhiraj}"

echo "==> Project: $PROJECT_ID   Region: $REGION   Service: $SERVICE"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "==> Enabling required APIs (run, cloudbuild, artifactregistry)…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com >/dev/null

# Assemble runtime env vars.
ENVS="CEO_NAME=${CEO_NAME},COMPANY_NAME=Ekosight"
[ -n "${DATABASE_URL:-}" ] && ENVS="${ENVS},DATABASE_URL=${DATABASE_URL}"
[ -n "${LLM_PROVIDER:-}" ] && ENVS="${ENVS},LLM_PROVIDER=${LLM_PROVIDER}"

EXTRA=()
# Keep one warm instance so an in-container SQLite DB survives between requests.
if [ -z "${DATABASE_URL:-}" ]; then
  EXTRA+=(--min-instances=1 --max-instances=1)
  echo "!! No DATABASE_URL set -> using ephemeral SQLite, pinned to 1 instance."
fi
# If a Cloud SQL instance connection name is given, attach it.
[ -n "${CLOUDSQL_INSTANCE:-}" ] && EXTRA+=(--add-cloudsql-instances="${CLOUDSQL_INSTANCE}")

echo "==> Building & deploying from source (Cloud Build -> Cloud Run)…"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 --memory 512Mi \
  --set-env-vars "$ENVS" \
  "${EXTRA[@]}"

echo "==> Done. Service URL:"
gcloud run services describe "$SERVICE" --region "$REGION" \
  --format='value(status.url)'
