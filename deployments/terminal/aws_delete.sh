#!/usr/bin/env bash
# Delete AWS instance by name (only t3- instances will be deleted)
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"

NAME="example-1" # without t3- prefix

cat - <<JSON | curl -sS -X POST "$BASE_URL/aws/delete" -H "Content-Type: application/json" -d @- | jq
{
  "region": "${REGION}",
  "name": "${NAME}"
}
JSON

echo
echo "Requested deletion for t3-${NAME} (if exists)."
#!/usr/bin/env bash
set -euo pipefail

# Delete AWS instance by name (will only delete if Name tag starts with t3-)
BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"
NAME="t3-example-1"

curl -sS -X POST "$BASE_URL/aws/delete" -H "Content-Type: application/json" -d "{ \"region\": \"${REGION}\", \"name\": \"${NAME}\" }" | jq

echo
