#!/bin/sh
# Build the API in Cloud Build and deploy it to Cloud Run.
#
#   scripts/deploy_cloud_run.sh <gcp-project-id> <keys-file>
#
# The keys file holds QDRANT_URL (or TARGET_QDRANT_URL), QDRANT_API_KEY (or
# TARGET_QDRANT_API_KEY), REDIS_URL and GROQ_API_KEY as KEY=value lines. Keys go to
# Secret Manager and are never passed on the command line. Needs `gcloud auth login`
# and a project with billing enabled.
#
# Cost controls: --max-instances 1 and scale to zero when idle. The image is built
# remotely (linux/amd64), so a Mac's arm64 build is never uploaded.
set -eu

PROJECT="${1:?usage: $0 <gcp-project-id> <keys-file>}"
KEYS="${2:?usage: $0 <gcp-project-id> <keys-file>}"
REGION="${REGION:-us-west1}"
SERVICE="${SERVICE:-securerag-api}"
REPO="${REPO:-securerag}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/api:$(git rev-parse --short HEAD)"
G="gcloud --project=$PROJECT --quiet"

get() { # first non-empty value among the given keys in the keys file
  for k in "$@"; do
    v=$(sed -n "s/^$k=//p" "$KEYS" | head -1)
    [ -n "$v" ] && { printf %s "$v"; return; }
  done
  echo "missing $* in $KEYS" >&2; exit 1
}
QDRANT_URL_VALUE=$(get QDRANT_URL TARGET_QDRANT_URL)
# Fail before changing anything if a key is missing (values are not printed).
get GROQ_API_KEY >/dev/null
get QDRANT_API_KEY TARGET_QDRANT_API_KEY >/dev/null
get REDIS_URL >/dev/null

$G services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com

$G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 ||
  $G artifacts repositories create "$REPO" --location="$REGION" --repository-format=docker

for pair in "groq-api-key:GROQ_API_KEY" "qdrant-api-key:QDRANT_API_KEY TARGET_QDRANT_API_KEY" \
            "redis-url:REDIS_URL"; do
  name=${pair%%:*}; keys=${pair#*:}
  # shellcheck disable=SC2086
  get $keys | { $G secrets describe "$name" >/dev/null 2>&1 ||
      $G secrets create "$name" --replication-policy=automatic >/dev/null
    $G secrets versions add "$name" --data-file=- >/dev/null; }
done

# Cloud Run's runtime service account needs to read the secrets.
SA="$($G projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for name in groq-api-key qdrant-api-key redis-url; do
  $G secrets add-iam-policy-binding "$name" --member="serviceAccount:$SA" \
    --role=roles/secretmanager.secretAccessor >/dev/null
done

# The dependency install takes ~20 min, past Cloud Build's 10 min default timeout.
$G builds submit --tag "$IMAGE" --timeout=3600s .

$G run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" \
  --allow-unauthenticated --memory 2Gi --cpu 1 --cpu-boost \
  --min-instances 0 --max-instances 1 --timeout 120 \
  --set-env-vars "UVICORN_WORKERS=1,QDRANT_URL=$QDRANT_URL_VALUE,QDRANT_COLLECTION_NAME=financebench_eval150_ctx,TOP_K_RERANK=8,TOP_K_RETRIEVE=20,LLM_PROVIDER=groq,LLM_MODEL=openai/gpt-oss-120b,RATE_LIMIT_PER_MINUTE=20" \
  --set-secrets "GROQ_API_KEY=groq-api-key:latest,QDRANT_API_KEY=qdrant-api-key:latest,REDIS_URL=redis-url:latest"

$G run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
