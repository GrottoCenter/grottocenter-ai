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

A file that was analysed before is answered from storage with no model call, so it
uses no quota. Daily counts are kept in MongoDB (collection `usage`, removed by a TTL
index that `scripts/init_db.py` creates), so a restart does not reset them. A count is
not given back when an analysis fails afterwards, because OCR and model calls may
already have been paid for. The concurrency count lives in memory and assumes a single
instance.

`GET /health` only says that the process is up. `GET /ready` also pings MongoDB
and answers 503 when it is unreachable.

Never commit `.env` or place a real secret in a tracked file. Configure
`SSO_SALT_DOCUMENTS` in the Grottocenter API environment as well; do not use
the Superset signing secret for document SSO.

## Run with Docker

The `docker-compose.dev.yml` file uses the default GreenPT URL.

From the repository root, run:

```bash
docker compose -f docker-compose.dev.yml up --build
```

The API is available at `http://localhost:8000`.

Run the service in the background with:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

View the logs:

```bash
docker compose -f docker-compose.dev.yml logs -f backend
```

Stop the service:

```bash
docker compose -f docker-compose.dev.yml down
```

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
