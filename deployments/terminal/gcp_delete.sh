#!/usr/bin/env bash
# Delete GCP instance by name (uses credentials.json)
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
GCP_CRED="./credentials.json"
ZONE="europe-west1-b"
NAME="mi-instancia-gcp-1"

cat - <<JSON | curl -sS -X POST "$BASE_URL/delete" -H "Content-Type: application/json" -d @- | jq
{
  "credentials": "${GCP_CRED}",
  "name": "${NAME}",
  "zone": "${ZONE}"
}
JSON
