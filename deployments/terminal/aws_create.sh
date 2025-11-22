#!/usr/bin/env bash
# Create an AWS instance (uses credentials_aws.json in repo or env vars)
set -euo pipefail

BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"

PASSWORD="ChangeMeStrongP@ssw0rd"

cat - <<'JSON' | curl -sS -X POST "$BASE_URL/aws/create" -H "Content-Type: application/json" -d @- | jq
{
  "region": "${REGION}",
  "name": "t3-example-1",
  "image_id": "ami-03c1f788292172a4e",
  "instance_type": "t3.micro",
  "password": "${PASSWORD}"
}
JSON

echo
echo "Requested creation of t3- instance using password (check security groups and SSH settings)."
#!/usr/bin/env bash
set -euo pipefail

# Create AWS instance (will ensure Name tag starts with t3-). Edit values as needed.
BASE_URL="http://127.0.0.1:8001"
REGION="us-west-2"
AMI="ami-03c1f788292172a4e"
INSTANCE_TYPE="t3.micro"
KEY_NAME="my-key-pair"

curl -sS -X POST "$BASE_URL/aws/create" \
  -H "Content-Type: application/json" \
  -d "{\"region\": \"${REGION}\", \"name\": \"t3-example-1\", \"image_id\": \"${AMI}\", \"instance_type\": \"${INSTANCE_TYPE}\", \"key_name\": \"${KEY_NAME}\" }" | jq

echo
