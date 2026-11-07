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
- authentication token validation through Grottocenter.

## Prerequisites

- Docker and Docker Compose;
- a GreenPT API key;
- an accessible Grottocenter instance to validate tokens.

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
| `AUTH_VERIFY_URL` | Grottocenter token verification endpoint | `http://localhost:1337/api/v1/auth/check` |

Never commit `.env` or place a real secret in a tracked file.
When running in Docker, this URL must point to an auth service reachable from
the container. `localhost` refers to the backend container itself; the
development Compose file uses `host.docker.internal` for an auth service on the
host.

## Run with Docker

The `docker-compose.dev.yml` file uses the default GreenPT URL and connects to
Grottocenter on the host machine (`host.docker.internal:1337`).

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
2. The token is verified through `AUTH_VERIFY_URL`.
3. The PDF is read in memory and its text is extracted page by page.
4. If the extracted text contains fewer than 1,000 characters, GreenPT is used
   for OCR.
5. Short documents are analyzed in one LLM call. Long documents are split into
   chunks, analyzed separately, and then merged.
6. The GreenPT response is validated with Pydantic models, stored in MongoDB,
   and returned to the client.
