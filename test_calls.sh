#!/usr/bin/env bash
# Test calls for local FastAPI server (backend)
# Usage: edit placeholders and run: bash test_calls.sh

BASE_URL="http://127.0.0.1:8001"
GCP_CRED="./credentials.json"
AWS_REGION="us-west-2"

set -euo pipefail

echo "--- GCP: List instances (uses ./credentials.json by default)"
curl -sS -G "$BASE_URL/list" --data-urlencode "credentials=$GCP_CRED" --data-urlencode "zone=europe-west1-b" | jq || true
echo

echo "--- GCP: Find machine types (cpus=2, ram=4)"
curl -sS -X POST "$BASE_URL/find" -H "Content-Type: application/json" -d "{
  \"credentials\": \"$GCP_CRED\",
  \"zone\": \"europe-west1-b\",
  \"region\": \"europe-west1\",
  \"cpus\": 2,
  \"ram\": 4
}" | jq || true
echo

echo "--- GCP: Create instance (password-based, t3- prefix)"
GCP_PASS="ChangeMeStrongP@ssw0rd"
curl -sS -X POST "$BASE_URL/create" -H "Content-Type: application/json" -d "{
  \"credentials\": \"$GCP_CRED\",
  \"zone\": \"europe-west1-b\",
  \"name\": \"t3-mi-instancia-gcp-1\",
  \"machine_type\": \"e2-medium\",
  \"password\": \"${GCP_PASS}\"
}" | jq || true
echo

echo "--- GCP: Delete instance (by name + zone)"
curl -sS -X POST "$BASE_URL/delete" -H "Content-Type: application/json" -d "{
  \"credentials\": \"$GCP_CRED\",
  \"name\": \"t3-mi-instancia-gcp-1\",
  \"zone\": \"europe-west1-b\"
}" | jq || true
echo

echo "--- AWS: List instances (uses credentials_aws.json if present)"
curl -sS -X GET "$BASE_URL/aws/list?region=$AWS_REGION" -H "Content-Type: application/json" | jq || true
echo

echo "--- AWS: Create instance (password-based, t3- prefix)"
AWS_PASS="ChangeMeStrongP@ssw0rd"
curl -sS -X POST "$BASE_URL/aws/create" -H "Content-Type: application/json" -d "{
  \"region\": \"$AWS_REGION\",
  \"name\": \"t3-example-1\",
  \"image_id\": \"ami-03c1f788292172a4e\",
  \"instance_type\": \"t3.micro\",
  \"password\": \"${AWS_PASS}\"
}" | jq || true
echo

echo "--- AWS: Delete instance (by name, will only delete t3- instances)"
curl -sS -X POST "$BASE_URL/aws/delete" -H "Content-Type: application/json" -d "{
  \"region\": \"$AWS_REGION\",
  \"name\": \"t3-example-1\"
}" | jq || true
echo

echo "--- ALL: Create in BOTH providers"
curl -sS -X POST "$BASE_URL/all/create" -H "Content-Type: application/json" -d "{
  \"gcp\": {
    \"credentials\": \"$GCP_CRED\",
    \"zone\": \"us-central1-a\",
    \"name\": \"mi-instancia-ambos-1\",
    \"machine_type\": \"e2-medium\"
  },
  "gcp": {
    "credentials": "$GCP_CRED",
    "zone": "europe-west1-b",
    "name": "t3-mi-instancia-ambos-1",
    "machine_type": "e2-medium",
    "password": "${GCP_PASS}"
  },
  "aws": {
    "region": "$AWS_REGION",
    "name": "t3-example-1",
    "image_id": "ami-03c1f788292172a4e",
    "instance_type": "t3.micro",
    "password": "${AWS_PASS}"
  }
  \"gcp_zone\": \"us-central1-a\",
  \"aws_region\": \"$AWS_REGION\"
}" | jq || true
echo

echo "--- ALL: Find on both providers"
curl -sS -X POST "$BASE_URL/all/find" -H "Content-Type: application/json" -d "{
  \"gcp_credentials\": \"$GCP_CRED\",
  \"gcp_zone\": \"us-central1-a\",
  \"gcp_region\": \"us-central1\",
  \"gcp_cpus\": 2,
  \"gcp_ram\": 4,
  \"aws_region\": \"$AWS_REGION\",
  \"aws_min_vcpus\": 2,
  \"aws_min_memory_gb\": 4
}" | jq || true
echo

echo "--- ALL: Delete both (GCP by name, AWS by instance id)"
curl -sS -X POST "$BASE_URL/all/delete" -H "Content-Type: application/json" -d "{
  \"gcp_credentials\": \"$GCP_CRED\",
  \"gcp_name\": \"mi-instancia-ambos-1\",
  \"gcp_zone\": \"us-central1-a\",
  \"aws_region\": \"$AWS_REGION\",
  \"aws_instance_id\": \"i-0123456789abcdef0\"
}" | jq || true
echo

echo "Finished test calls. Adjust placeholders before running for real operations (create/delete are real and billable)."
