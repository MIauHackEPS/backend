#!/usr/bin/env bash
# Find AWS instances by name prefix (only t3- matches)
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"

NAME="example-1" # without t3- prefix; API will add it

cat - <<JSON | curl -sS -X POST "$BASE_URL/aws/find" -H "Content-Type: application/json" -d @- | jq
{
  "region": "${REGION}",
  "name": "${NAME}"
}
JSON
#!/usr/bin/env bash
set -euo pipefail

# Find AWS instances by name fragment (searches for t3-<name>)
BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"
NAME_FRAGMENT="example-1"

curl -sS -X POST "$BASE_URL/aws/find" -H "Content-Type: application/json" -d "{ \"region\": \"${REGION}\", \"name\": \"${NAME_FRAGMENT}\" }" | jq

echo
