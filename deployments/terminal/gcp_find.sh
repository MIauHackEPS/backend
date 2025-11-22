#!/usr/bin/env bash
# Find GCP machine types matching cpu/ram in a zone
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
GCP_CRED="./credentials.json"
ZONE="europe-west1-b"
REGION="europe-west1"

cat - <<JSON | curl -sS -X POST "$BASE_URL/find" -H "Content-Type: application/json" -d @- | jq
{
  "credentials": "${GCP_CRED}",
  "zone": "${ZONE}",
  "region": "${REGION}",
  "cpus": 2,
  "ram": 4
}
JSON
