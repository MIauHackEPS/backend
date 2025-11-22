# Curl Commands / Examples for FastAPI endpoints

This file lists the common curl commands and options to call the FastAPI endpoints in this project. Replace `BASE_URL` and any paths / IDs to match your environment.

---

## Variables used in examples

- `BASE_URL` — e.g. `http://127.0.0.1:8001` (adjust if your server is on another port/host)
- `GCP_CRED` — path to GCP credentials JSON (default `./credentials.json` in repo)
- `AWS_CRED` — path to AWS credentials JSON (default `./credentials_aws.json` in repo)
- `ZONE` — GCP zone, e.g. `europe-west1-b`
- `REGION` — AWS region, default `us-west-2`
- `INSTANCE_NAME` — name of instance (GCP name will be sanitized to valid format; AWS `Name` tag must be prefixed `t3-`)
- `INSTANCE_ID` — AWS instance id (i-...)
- `STATE` — optional state filter (e.g. `RUNNING`, `TERMINATED` for GCP; `running`, `stopped` for AWS)

---

## 1) Delete (combined) — `/all/delete` (deletes across GCP and AWS)

- JSON body example (file): `deployments/astro/all_delete.json` (this file in repo uses credential-file fallback by default)

Example curl (POST JSON file):

```bash
PAYLOAD="$(pwd)/deployments/astro/all_delete.json"

curl -sS -X POST "http://127.0.0.1:8001/all/delete" \
  -H "Content-Type: application/json" \
  -d "@${PAYLOAD}" | jq
```

If you want to delete a specific GCP name and AWS name inline:

```bash
curl -sS -X POST "http://127.0.0.1:8001/all/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "gcp_credentials": "./credentials.json",
    "gcp_name": "t3-mi-instancia-ambos-1",
    "gcp_zone": "europe-west1-b",
    "aws_region": "us-west-2",
    "aws_name": "t3-example-1"
  }' | jq
```

Notes:
- The combined endpoint by default reads `credentials.json` and `credentials_aws.json` from the repo directory if inline credentials are not supplied.
- AWS deletion will delete by `instance_id` if provided; otherwise it will look for `Name` tags starting with `t3-`.

---

## 2) Delete GCP only — `/delete`

Use the GCP-specific delete endpoint. This requires `credentials` (path to credentials JSON) in the request body.

Example (delete by name and zone):

```bash
curl -sS -X POST "http://127.0.0.1:8001/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": "./credentials.json",
    "name": "t3-mi-instancia-gcp-1",
    "zone": "europe-west1-b"
  }' | jq
```

If you omit `zone` the server will try to find the instance across zones and delete the first match.

---

## 3) Delete AWS only — `/aws/delete`

Example deleting by instance id (preferred):

```bash
curl -sS -X POST "http://127.0.0.1:8001/aws/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "region": "us-west-2",
    "instance_id": "i-0123456789abcdef0"
  }' | jq
```

Example deleting by `Name` tag (must begin with `t3-`):

```bash
curl -sS -X POST "http://127.0.0.1:8001/aws/delete" \
  -H "Content-Type: application/json" \
  -d '{
    "region": "us-west-2",
    "name": "t3-mi-instancia-aws-1"
  }' | jq
```

If your server cannot find AWS credentials, it will try `deployments/../credentials_aws.json` (repo root `credentials_aws.json`). You can also pass `aws_access_key`, `aws_secret_key`, and `aws_session_token` in the JSON body.

---

## 4) Other useful endpoints and curl notes

- List GCP instances (GET with query params):

```bash
curl -sS -G "http://127.0.0.1:8001/list" \
  --data-urlencode "credentials=./credentials.json" \
  --data-urlencode "zone=europe-west1-b" \
  --data-urlencode "state=RUNNING" | jq
```

- List AWS instances (GET with query params):

```bash
curl -sS -G "http://127.0.0.1:8001/aws/list" \
  --data-urlencode "region=us-west-2" \
  --data-urlencode "state=running" | jq
```

- Combined list `/all/list` (POST with JSON file):

```bash
curl -sS -X POST "http://127.0.0.1:8001/all/list" \
  -H "Content-Type: application/json" \
  -d '@deployments/astro/all_list.json' | jq
```

- Find and create endpoints also exist; look under `deployments/astro/` for example payloads.

---

## 5) Passing credentials securely

- By default the server will read local `credentials.json` (GCP) and `credentials_aws.json` (AWS) from the repo directory. Prefer using local files rather than embedding secrets in payloads.
- If you must send AWS keys inline for a one-off test, include `aws_access_key` and `aws_secret_key` fields in the `/aws/*` or `/all/*` request body.

---

## 6) Quick examples (one-liners)

- Delete GCP instance by name & zone:

```bash
curl -sS -X POST http://127.0.0.1:8001/delete -H "Content-Type: application/json" -d '{"credentials":"./credentials.json","name":"t3-node-1","zone":"europe-west1-b"}' | jq
```

- Delete AWS by name:

```bash
curl -sS -X POST http://127.0.0.1:8001/aws/delete -H "Content-Type: application/json" -d '{"region":"us-west-2","name":"t3-node-aws-1"}' | jq
```

- Combined delete (both providers):

```bash
curl -sS -X POST http://127.0.0.1:8001/all/delete -H "Content-Type: application/json" -d '{"gcp_credentials":"./credentials.json","gcp_name":"t3-node","gcp_zone":"europe-west1-b","aws_region":"us-west-2","aws_name":"t3-node"}' | jq
```

---

If you want, I can also:

- Replace the broken `deployments/terminal/all_list.sh` with the cleaned `all_list_fixed.sh` I created.
- Add a small README or script to help run these commands with environment variables.
- Add examples for using inline AWS credentials securely via environment variables (not in payloads).

Tell me which of those you'd like next.