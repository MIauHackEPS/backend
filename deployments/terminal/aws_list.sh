#!/usr/bin/env bash
# List AWS instances (only t3- are returned by API)
set -euo pipefail
#!/usr/bin/env bash
# List AWS instances (only t3- are returned by API)
# Usage: ./aws_list.sh [STATE]
set -euo pipefail
#!/usr/bin/env bash
# List AWS instances (only t3- are returned by API)
# Usage: ./aws_list.sh [STATE]
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
REGION="${REGION:-us-west-2}"
STATE="${1:-${STATE:-}}"

if [ -n "$STATE" ]; then
  curl -sS -G "$BASE_URL/aws/list" --data-urlencode "region=${REGION}" --data-urlencode "state=${STATE}" | jq
else
  curl -sS -G "$BASE_URL/aws/list" --data-urlencode "region=${REGION}" | jq
fi

echo
