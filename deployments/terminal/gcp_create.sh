#!/usr/bin/env bash
# Create a GCP instance via backend API (example)
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
GCP_CRED="./credentials.json"

ZONE="europe-west1-b"
PASSWORD="ChangeMeStrongP@ssw0rd"

cat - <<JSON | curl -sS -X POST "$BASE_URL/create" -H "Content-Type: application/json" -d @- | jq
{
  "credentials": "${GCP_CRED}",
  "zone": "${ZONE}",
  "name": "mi-instancia-gcp-1",
  "machine_type": "e2-medium",
  "password": "${PASSWORD}"
}
JSON
