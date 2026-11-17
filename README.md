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
| `CORS_ALLOW_LOCALHOST` | `true` also allows a developer's machine: `localhost`, `127.0.0.1` and `[::1]`, on any port, over http or https (default `false`) | `true` |
| `CORS_ORIGIN_REGEX` | A regular expression matched against the whole origin, for staging deployments whose address changes (default empty). Write it with `[0-9]` and `[.]` rather than `\d` and `\.` | `https://orange-rock-0d4f87503-[0-9]+[.]westeurope[.]azurestaticapps[.]net` |
| `LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (default `INFO`) | `INFO` |
| `FORWARDED_ALLOW_IPS` | Proxies whose `X-Forwarded-For` uvicorn trusts; read by uvicorn itself (default `127.0.0.1,::1`) | `127.0.0.1` |
| `AI_SERVER_PORT` | Host port the compose files publish the API on (default `8000`) | `8000` |
| `ANALYZE_ENABLED` | Kill switch: `false` makes `POST /documents/analyze` answer 503 without redeploying (default `true`) | `true` |
| `USER_DAILY_LIMIT` | Analyses one user may start per UTC day (default `5`) | `5` |
| `USER_MAX_CONCURRENT` | Analyses one user may have running at once (default `2`) | `2` |
| `GLOBAL_DAILY_LIMIT` | Analyses across all users per UTC day; placeholder until the price of one analysis is known (default `200`) | `200` |
| `MAX_FILE_SIZE_MB` | Largest accepted upload (default `60`) | `60` |
| `MAX_PAGES` | Most pages a PDF may have (default `300`) | `300` |
| `MAX_LLM_CALLS` | Most model calls one document may need (default `10`) | `10` |
| `QUOTA_EXEMPT_USER_IDS` | Grottocenter user ids with no daily quota, comma-separated (default empty: nobody) | `1,60181` |

The server checks its settings at startup and refuses to start, listing every
problem at once, when `MONGO_URI`, `MONGO_DB_NAME`, `GREENPT_API_KEY` or
`SSO_SALT_DOCUMENTS` is missing, when the SSO secret is shorter than 32 bytes, or
when `CORS_ORIGINS` contains `*`. The messages name the variables, never their values.

`CORS_ORIGIN_REGEX` is checked too: it must compile, be at most 500 characters, and match none of
a set of unrelated origins (`https://evil.example`, another tenant of azurestaticapps.net, github.io,
and so on). A pattern such as `.*`, or one that is a wildcard on a shared hosting domain, stops the
server from starting, so it cannot silently become the wildcard that `CORS_ORIGINS` refuses.
Browsers only call this API with a bearer token that the Grottocenter API issues for the user, and
no cookie is involved, so allowing localhost or a staging address lets that origin make requests
on behalf of a user who is logged in there, and nothing more.

The limit variables are passed to the container by both compose files with the defaults above.

The limit variables must be integers between 1 and a sane maximum (`ANALYZE_ENABLED`
must be `true` or `false`); the server refuses to start otherwise.

### Cost and abuse limits

The daily quota can be lifted for a few people with `QUOTA_EXEMPT_USER_IDS`, a comma-separated
list of Grottocenter user ids (the `sub` of their token; ids match whole, so `1` does not
exempt `10`). An exempt user has no daily quota and no counter, and every other limit still
applies to them: their analyses count toward `GLOBAL_DAILY_LIMIT` (and are refused with 503
once it is reached), they have the same concurrency cap, file size, page and model-call limits,
and `ANALYZE_ENABLED=false` stops them too. Each exempt analysis is logged as
`analysis quota exempt caller=<id>`. The variable is read at startup and checked: anything
that is not a list of positive integers (or more than 50 ids) stops the server from starting.
To change the list on the VM, edit `~/services/.env` and recreate the container with
`docker compose up -d ai-server`.

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
On the dedicated AI server VM the same services run behind Traefik instead; see
`cloud_azure/ai_vm` in the private infrastructure repository.

The image has a health check on `GET /ready`, so `docker compose ps` shows the backend
as `unhealthy` when MongoDB cannot be reached. The `db-init` service is a one-shot job
that creates the application user, the collections and their indexes, and exits.

Database passwords go into the MongoDB connection URI: use URL-safe characters (for
example `openssl rand -hex 24`).

## Deployment

`.github/workflows/deploy.yml` builds the image in CI and ships it over SSH to the
dedicated AI server VM (`grottocenter-ai`), with no registry, the same way as the OAI and
Z3950 servers are deployed to their own VM. The VM side (creation, compose file, volumes,
`.env`, Traefik, backups) is described in `cloud_azure/ai_vm/README.md` in the private
infrastructure repository.

The AI server has its own VM on purpose: it parses PDFs uploaded by any registered user,
and the shared worker1 VM has no memory to spare next to the search index. The workflow
refuses to run if the configured host is worker1.

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
7. Checks the result twice more, because a green job must mean the new container is
   serving: the remote script has to print `REMOTE_DEPLOY_OK` as its very last line (a
   script that stops early, for example because a command swallowed its input, is a failed
   deploy), then a separate SSH call reads back from Docker that `ai-server` is running,
   healthy, and runs the image that was just built, and finally the runner requests
   `https://ai.grottocenter.org/ready` with certificate verification on, retrying for up to
   3 minutes (Traefik requests the certificate after the first healthy start).

On the very first deploy there is no previous image, so a failure leaves the new
container as it is and says so.

The remote script reaches the VM on stdin, so a command inside it that reads stdin would
swallow the rest of the script. Every `docker` call in it therefore runs with its input
closed. Keep that in mind when adding commands to it.

### Secrets

| Secret | Value |
| --- | --- |
| `AI_VM_HOST` | Host name of the AI server VM, for example `ai-vm.grottocenter.org` |
| `AI_VM_USER` | The SSH user on the VM (it must be allowed to use Docker), `azureuser` |
| `AI_VM_SSH_KEY` | The private half of a key made for this deployment only, without a passphrase |
| `AI_VM_HOST_KEY` | The VM's host key line, used instead of `ssh-keyscan` so the workflow only talks to the real VM |

Store them as secrets of the `ai-vm` environment (see below), not as repository secrets.
The names differ from the earlier `WORKER_*` ones so that a leftover secret can never
point a deploy at another VM.

Create the key and the host key line on your machine, once:

```bash
# A key used for nothing else, so it can be revoked on its own
ssh-keygen -t ed25519 -N '' -C 'ai-server deploy' -f ./ai_deploy_key
# Authorise it on the VM (append ai_deploy_key.pub to ~/.ssh/authorized_keys of AI_VM_USER,
# prefixed with `restrict `, see "About the deploy key" below)

# The host key line. It must name the same host as AI_VM_HOST.
ssh-keyscan -t ed25519 ai-vm.grottocenter.org > ai_vm_known_hosts
ssh-keygen -lf ai_vm_known_hosts
```

Do not trust the `ssh-keyscan` output blindly: both the scan and the first connection come
over the same network, so a matching fingerprint proves nothing. Log in with your own
administrator key and read the fingerprint on the VM itself
(`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, run there). The two must be
identical. Then test the deploy key the way the workflow will connect, with the pinned
host key and strict checking:

```bash
ssh -i ./ai_deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=./ai_vm_known_hosts \
  -o StrictHostKeyChecking=yes azureuser@ai-vm.grottocenter.org \
  'docker version --format "{{.Server.Version}}" && echo OK'
```

Store the key and the `ai_vm_known_hosts` file as `AI_VM_SSH_KEY` and `AI_VM_HOST_KEY`
(`gh secret set AI_VM_SSH_KEY --env ai-vm -R <repo> < ./ai_deploy_key`), then delete the
local private key. GitHub never shows a secret again.

### Environment

The deploy job uses the GitHub environment `ai-vm` (Settings, Environments). Create it
before the first run, and put the four secrets on it so that only this job can read them.
Add one setting:

- **Deployment branches**, restricted to `develop` and `feat/analyse-document`, because a
  manual run deploys the branch it is started from.

GitHub only offers **required reviewers** (an approval before each deploy) on private
repositories with GitHub Enterprise. On the Team plan the API answers 422 "billing plan"
when you ask for them, so there is no approval step: anyone who can push to a permitted
branch, or run the workflow by hand, can deploy. The protections that remain are the
branch restriction above, the deploy key being limited to this one VM, and the health
check with automatic rollback. If an approval gate is wanted later, either upgrade the
plan or protect `develop` so that it only changes through a reviewed pull request.

### Rollback

When a deploy fails its health check the workflow rolls back by itself. To go back to the
previous image by hand, on the VM:

```bash
docker tag ai-server:previous ai-server
docker compose -f services/docker-compose.yml up -d --no-deps ai-server
```

### About the deploy key

The key can run commands on the VM as `AI_VM_USER`, and being allowed to use Docker is
equivalent to being root there, so treat it as a production credential. Limit the damage:
use a dedicated key, a dedicated user, the `restrict` option in `authorized_keys` (no
port, agent or X11 forwarding), and the environment protections above. A forced command
that only accepts the workflow's operations would be stricter still, but the switch-over
script is sent over SSH, so it would first have to live on the VM; that is not set up here.

## Smoke test

`scripts/smoke_test.sh` checks a deployed server from the outside. It needs `bash`, `curl`
and `python3` only. Run it after a deploy, from your own machine:

```bash
scripts/smoke_test.sh                        # asks for a Grottocenter email and password
GC_TOKEN=<your user token> scripts/smoke_test.sh   # no prompt
scripts/smoke_test.sh --ocr --ssh-logs ~/.ssh/grottocenter_ai_ed25519
```

To test with a real document, `scripts/smoke_candidates.sql` picks a few public PDFs from the
Grottocenter database (run it on a read-only connection): validated documents with a validated
PDF, under a licence that allows reuse (the text goes to GreenPT), of type Book, Issue, Article
or Report, and not tied to a sensitive massif or entrance (a PDF can contain coordinates). It
returns a few per type and size class with the title, licence and download URL. The file size
is not in the database, so check it first with `curl -sI <url>`: the server refuses over 60 MB (`MAX_FILE_SIZE_MB`).

For the capacity check of the VM, `scripts/largest_candidates.sql` lists the 20 longest eligible documents (40 to 300 pages) with the same filters. The file size is again not in the database, so check each URL's `Content-Length` and take the biggest one under 60 MB; the file size, more than the page count, is what loads the server's memory.

| Option | Meaning |
| --- | --- |
| `--pdf FILE` | analyse this document instead of the synthetic one the script generates (new on every run, so each run really analyses) |
| `--ocr` | also upload a tiny PDF, which goes through GreenPT's OCR (one more analysis) |
| `--local` | `AI_URL` is a local http server: skip the TLS, redirect and closed-port checks |
| `--ssh-logs KEYFILE` | read the server's logs over SSH (`SSH_TARGET`, default `azureuser@ai-vm.grottocenter.org`) and check them |
| `AI_URL`, `API_URL`, `FRONT_ORIGIN` | the server, the Grottocenter API and the front origin to test CORS with (defaults are production) |

What it checks:

- **A, no login:** `/health` and `/ready` answer 200, answers carry no `server` header, the public
  documentation names no framework and loads nothing from another host, the certificate
  verifies, `http` redirects to `https`, a missing or forged token gets 401, the CORS preflight
  is allowed from the front and not from another origin, and ports 8000 and 27017 do not
  answer from outside.
- **B, with a login:** a token for another product (`superset`) is refused, a text file named
  `.pdf` gets 415 or 422, an upload just over `MAX_FILE_SIZE_MB` gets 413, a real PDF is analysed (it prints the
  duration, the number of documents and the first title), and the same PDF again returns an
  identical result straight from storage.
- **C, with `--ssh-logs`:** the last 300 log lines hold no JWT and no `Authorization` header, and
  the second upload shows `source=storage` in its `analysis caller=...` line.

The login prompts for an email and a password (and the one-time code if the account needs one),
asks the Grottocenter API for a fresh 30-second token for each call, and never prints, stores or
passes on a command line a token, a password or a code.

**Cost and quota.** A default run starts one analysis (one GreenPT call), and `--ocr` starts one
more. The repeat upload is served from storage and is free. Every analysis counts against the
quota of the account you log in with (5 a day), so a few runs in one day can end in a 429 that
the script explains.

Exit code: `0` all checks passed, `1` at least one failed, `2` nothing failed but section B could
not run (no login, no terminal).

Not covered by default, to do by hand:

- **Daily quota.** Lower `USER_DAILY_LIMIT` to `1` in the VM's `.env`, recreate the container
  (`cd ~/services && docker compose up -d --no-deps ai-server`), run the script twice with the
  same account: the second run's analysis must say 429. Put the limit back afterwards.
- **Kill switch.** Set `ANALYZE_ENABLED=false` the same way: the analysis must say 503
  ("temporarily disabled"). Put it back to `true`.
- **A request over 2 minutes.** Run `scripts/smoke_test.sh --pdf BIG.pdf` with the largest real PDF
  and read the duration it prints; it notes when a request took over 2 minutes and still went
  through Traefik.

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

### API documentation

The documentation is public on purpose, so that front-end developers can build against it
without reading the code:

- `GET /docs`: the interactive page (Swagger UI, "Try it out" included once you authorize with
  a token).
- `GET /openapi.json`: the OpenAPI document. It describes `POST /documents/analyze` with the
  schema of the 200 answer (and an example), and every error it can return: 401, 413, 415, 422,
  429 and 503 (both with `Retry-After`), 500, 502 and 504, all with the body
  `{"detail": "<message>"}`. It also describes how to get the token (30 seconds, from the
  Grottocenter API) and the `multipart/form-data` upload. `/health`, `/ready` and `/` work but
  are not documented.

It names neither the application nor the framework, on purpose: no `server` header (uvicorn
runs with `--no-server-header`), no framework page, no generated component names, and a
request that does not match the endpoint gets the same `{"detail": "..."}` body (422) as every
other error. The page loads Swagger UI from `AI_Serveur/static/swagger-ui` (see its README),
not from a CDN, and the online validator is turned off, so opening it contacts no other
host. ReDoc is not offered.

`tests/test_api_documentation.py` fails when the server returns a status that the document
does not list, so a new error status has to be declared in `AI_Serveur/api_docs.py`.

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
