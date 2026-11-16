# Grottocenter AI Server

FastAPI service for the automatic analysis of PDF documents for Grottocenter.
The server extracts bibliographic metadata with GreenPT and returns a format
compatible with Grottocenter documents.

## Features

- PDF text extraction with PyMuPDF;
- OCR through GreenPT for scanned PDFs or PDFs containing little text;
- metadata analysis with an LLM;
- map-reduce processing for long documents;
- detection of articles contained in a journal issue;
- short-lived SSO token validation for document analysis.

## Prerequisites

- Docker and Docker Compose;
- a GreenPT API key;
- a shared SSO secret configured in both Grottocenter and this service.

## Configuration

Copy the example environment file and add your GreenPT API key:

```bash
cp .env.example .env
```

On Windows, copy `.env.example` to `.env` manually if the `cp` command is not
available.

Available `.env` variables:

| Variable | Description | Example |
| --- | --- | --- |
| `GREENPT_API_URL` | GreenPT API URL | `https://api.greenpt.ai/v1` |
| `GREENPT_API_KEY` | GreenPT secret API key | `your-api-key` |
| `SSO_SALT_DOCUMENTS` | Shared HS256 secret for document SSO, at least 32 bytes; set the same value in Grottocenter | generated secret |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API. `*` is refused. Empty means no browser origin | `https://grottocenter.org` |
| `LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (default `INFO`) | `INFO` |
| `FORWARDED_ALLOW_IPS` | Proxies whose `X-Forwarded-For` uvicorn trusts; read by uvicorn itself (default `127.0.0.1,::1`) | `127.0.0.1` |
| `AI_SERVER_PORT` | Host port the compose files publish the API on (default `8000`) | `8000` |
| `ANALYZE_ENABLED` | Kill switch: `false` makes `POST /documents/analyze` answer 503 without redeploying (default `true`) | `true` |
| `USER_DAILY_LIMIT` | Analyses one user may start per UTC day (default `5`) | `5` |
| `USER_MAX_CONCURRENT` | Analyses one user may have running at once (default `2`) | `2` |
| `GLOBAL_DAILY_LIMIT` | Analyses across all users per UTC day; placeholder until the price of one analysis is known (default `200`) | `200` |
| `MAX_FILE_SIZE_MB` | Largest accepted upload (default `50`) | `50` |
| `MAX_PAGES` | Most pages a PDF may have (default `300`) | `300` |
| `MAX_LLM_CALLS` | Most model calls one document may need (default `10`) | `10` |

The server checks its settings at startup and refuses to start, listing every
problem at once, when `MONGO_URI`, `MONGO_DB_NAME`, `GREENPT_API_KEY` or
`SSO_SALT_DOCUMENTS` is missing, when the SSO secret is shorter than 32 bytes, or
when `CORS_ORIGINS` contains `*`. The messages name the variables, never their values.

The limit variables are passed to the container by both compose files with the defaults above.

The limit variables must be integers between 1 and a sane maximum (`ANALYZE_ENABLED`
must be `true` or `false`); the server refuses to start otherwise.

### Cost and abuse limits

Anyone with a Grottocenter account may analyse a PDF and sign-up is open, so the
limits are what protects the GreenPT bill. `POST /documents/analyze` answers:

| Status | When |
| --- | --- |
| 413 | The upload is over `MAX_FILE_SIZE_MB` |
| 415 | The file is not a PDF |
| 422 | The PDF cannot be read, is password protected, has no pages, has more than `MAX_PAGES` pages, or needs more than `MAX_LLM_CALLS` model calls |
| 429 | The user has `USER_MAX_CONCURRENT` analyses running (`Retry-After`: 10 s), or used `USER_DAILY_LIMIT` today (`Retry-After`: seconds until midnight UTC) |
| 503 | `ANALYZE_ENABLED=false`, or `GLOBAL_DAILY_LIMIT` is reached (`Retry-After`: seconds until midnight UTC) |

A request without a valid SSO token is answered 401 (or 503 if verification is not
configured) before its body is read, so an anonymous caller cannot make the server receive
an upload. `RequireValidTokenMiddleware` checks the token with the same function as the
route (`auth.authenticate`), and runs before the size limit, so the 413 is only ever shown to
authenticated callers.

A file that was analysed before is answered from storage with no model call, so it
uses no quota. Daily counts are kept in MongoDB (collection `usage`, removed by a TTL
index that `scripts/init_db.py` creates), so a restart does not reset them. A count is
not given back when an analysis fails afterwards, because OCR and model calls may
already have been paid for. The concurrency count lives in memory and assumes a single
instance.

### Errors from the analysis

Besides the limits above, `POST /documents/analyze` answers:

| Status | When |
| --- | --- |
| 422 | The upload is empty, or no text could be extracted from the PDF (even by OCR) |
| 502 | GreenPT answered with an error (any 4xx or 5xx, including a rejected key or its own rate limit), could not be reached, or answered something that is not JSON |
| 504 | GreenPT did not answer within the client's timeout |
| 500 | Anything else: a bug or an outage nobody planned for |

The answer is always a short `{"detail": "..."}` and never contains what GreenPT said.
A GreenPT 401 or 429 is a 502 here, so it cannot be mistaken for a problem with the
caller's own token or quota. The cause is in the log (the status and the first 500
characters of GreenPT's answer; for a 500, the traceback).

### One analysis per file

Two simultaneous uploads of the same file cost one analysis: the second waits for the
first and is answered from storage, without using quota or a model call. This is a lock in
the server process, so it assumes a single instance, like the concurrency limit. As a safety
net for anything else that writes to the same database, `scripts/init_db.py` creates a unique
index `hash_position_unique` on a file's hash and the `position` of each stored document
(0 for the file or issue itself, 1 to n for its articles); a second writer gets the stored
result instead of an error. Documents stored before `position` existed have none, and the
index skips them. Re-run `db-init` (it is idempotent, and the compose files run it on every
start) to create the index on an existing database.

`GET /health` only says that the process is up. `GET /ready` also pings MongoDB
and answers 503 when it is unreachable.

Never commit `.env` or place a real secret in a tracked file. Configure
`SSO_SALT_DOCUMENTS` in the Grottocenter API environment as well; do not use
the Superset signing secret for document SSO.

## Run with Docker

Two compose files, for two purposes.

### Local development: `docker-compose.dev.yml`

Not for deployment. It mounts `AI_Serveur/` into the container and reloads the server
when a file changes, logs at `DEBUG`, allows the local front-end origins
(`http://localhost:3000` and `http://localhost:5173`) and publishes MongoDB on
`127.0.0.1:27017` only.

Put the variables from `.env.example` in a `.env` file first. In development,
`SSO_SALT_DOCUMENTS` must be the value `grottocenter-api` signs with: when that API
runs with `NODE_ENV=development` and no `SSO_SALT_DOCUMENTS` of its own, this is the
`DEV_FALLBACK_SALT` constant in `api/services/SsoService.js`. Compose stops with a
message when a required variable is missing.

```bash
docker compose -f docker-compose.dev.yml up --build
```

The API is then at `http://localhost:8000`. Other commands:

```bash
docker compose -f docker-compose.dev.yml up --build -d   # in the background
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml down
```

### Production-like: `docker-compose.yml`

Builds the image and runs it the way it runs in production: no source mounted, the
root filesystem read-only (the application writes nothing to disk; `/tmp` is a tmpfs),
no extra Linux capabilities, and MongoDB reachable only from the compose network, with
no published port. The container runs as the unprivileged user `app` (uid 10001).

```bash
docker compose up --build -d
```

It publishes the API on `AI_SERVER_PORT` (default 8000) so the file can run on its own.
On the Grottocenter VM the same services run behind Traefik instead; see
`cloud_azure/worker_instance` in the private infrastructure repository.

The image has a health check on `GET /ready`, so `docker compose ps` shows the backend
as `unhealthy` when MongoDB cannot be reached. The `db-init` service is a one-shot job
that creates the application user, the collections and their indexes, and exits.

Database passwords go into the MongoDB connection URI: use URL-safe characters (for
example `openssl rand -hex 24`).

## Deployment

`.github/workflows/deploy.yml` builds the image in CI and ships it to the Grottocenter VM
(worker1) over SSH, with no registry, the same way as the OAI and Z3950 servers. The VM
side (compose file, volumes, `.env`, Traefik, backups) is described in
`cloud_azure/worker_instance` in the private infrastructure repository.

The workflow runs on a push to `develop` that changes `AI_Serveur/**`, and by hand. The
code lives on `feat/analyse-document` until it reaches `develop`, so until then:

```bash
gh workflow run deploy.yml --ref feat/analyse-document
```

A manual run deploys whatever branch you give it, so see the environment below.

### What it does

1. Runs the CI workflow (ruff and pytest). Nothing is shipped if it fails.
2. Builds `ai-server` for `linux/amd64`.
3. On the VM, tags the running image `ai-server:previous`, the rollback target.
4. Ships the image with `docker save | bzip2 | ssh docker load`, and checks that the
   image on the VM is the one that was built.
5. Runs `db-init` with the new image (users, collections and indexes are applied on every
   deploy), then `docker compose up -d --no-deps ai-server`.
6. Waits up to 180 s for the container to be `healthy`. If it is not, it prints the last 50
   log lines, puts `ai-server:previous` back, restarts it, and fails the job.

On the very first deploy there is no previous image, so a failure leaves the new
container as it is and says so.

### Secrets

| Secret | Value |
| --- | --- |
| `WORKER_HOST` | Host name of the VM, for example `worker1.grottocenter.org` |
| `WORKER_USER` | The SSH user on the VM (it must be allowed to use Docker) |
| `WORKER_SSH_KEY` | The private half of a key made for this deployment only, without a passphrase |
| `WORKER_HOST_KEY` | The VM's host key line, used instead of `ssh-keyscan` so the workflow only talks to the real VM |

Create the key and the host key line on your machine, once:

```bash
# A key used for nothing else, so it can be revoked on its own
ssh-keygen -t ed25519 -N '' -C 'ai-server deploy' -f ./ai_deploy_key
# Authorise it on the VM (append ai_deploy_key.pub to ~/.ssh/authorized_keys of WORKER_USER)

# The host key line. It must name the same host as WORKER_HOST.
ssh-keyscan -t ed25519 worker1.grottocenter.org
```

Do not trust the `ssh-keyscan` output blindly: compare its fingerprint with the one on the
VM (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, run there), then store the line as
`WORKER_HOST_KEY`. Delete the local private key once it is stored.

### Environment

The deploy job uses the GitHub environment `worker1` (Settings, Environments). It is
created on the first run, and it is the place to put the four secrets so that only this
job can read them. Two settings are worth adding:

- **Required reviewers**, so that nobody deploys to production without a second pair of
  eyes.
- **Deployment branches**, restricted to `develop` and `feat/analyse-document`, because a
  manual run deploys the branch it is started from.

### Rollback

When a deploy fails its health check the workflow rolls back by itself. To go back to the
previous image by hand, on the VM:

```bash
docker tag ai-server:previous ai-server
docker compose -f services/docker-compose.yml up -d --no-deps ai-server
```

### About the deploy key

The key can run commands on the VM as `WORKER_USER`, and being allowed to use Docker is
equivalent to being root there, so treat it as a production credential. Limit the damage:
use a dedicated key, a dedicated user, the `restrict` option in `authorized_keys` (no
port, agent or X11 forwarding), and the environment protections above. A forced command
that only accepts the workflow's operations would be stricter still, but the switch-over
script is sent over SSH, so it would first have to live on the VM; that is not set up here.

## API

### Check that the server is running

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
	"status": "ok",
	"message": "API is running"
}
```

### Analyze a PDF

The analysis endpoint requires a valid token and a PDF uploaded as
`multipart/form-data`:

```bash
curl -X POST "http://localhost:8000/documents/analyze" \
   -H "Authorization: Bearer YOUR_TOKEN" \
   -F "file=@/path/to/document.pdf"
```

The response includes:

- `message`: operation result;
- `filename`: generated document identifier;
- `document_metadata`: a list of normalized metadata objects.

If the document is a journal issue, detected articles are converted into
`article` documents with their title, authors and page ranges. Each returned
metadata object is stored in MongoDB with the uploaded file's hash and filename;
re-uploading the same file returns the stored metadata instead of inserting it
again.

## Project architecture

```text
AI_Serveur/
├── main.py                         # FastAPI application creation
├── auth.py                         # Bearer token verification
├── client/
│   ├── GreenPT.py                  # GreenPT chat and OCR calls
│   └── HttpClient.py               # Shared HTTP client lifecycle
├── config/settings.py              # Configuration loading
├── controller/
│   └── documentController.py       # POST /documents/analyze route
├── service/
│   ├── documentService.py          # PDF reading and final transformation
│   └── documentLlmAnalyzeService.py # Prompts, chunking and LLM analysis
└── model/
    ├── DocumentMetadata.py          # Pydantic metadata schemas
    ├── GrottocenterType.py          # Document types
    ├── LicenseName.py               # Licenses
    └── TopLevelSubjectCode.py       # Subject taxonomy
```

## Analysis workflow

1. A request reaches `POST /documents/analyze` with a Bearer token.
2. The token signature, expiry, and `documents` audience are verified using
   `SSO_SALT_DOCUMENTS`.
3. The PDF is read in memory and its text is extracted page by page.
4. If the extracted text contains fewer than 1,000 characters, GreenPT is used
   for OCR.
5. Short documents are analyzed in one LLM call. Long documents are split into
   chunks, analyzed separately, and then merged.
6. The GreenPT response is validated with Pydantic models, stored in MongoDB,
   and returned to the client.
