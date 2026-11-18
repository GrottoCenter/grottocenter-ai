#!/usr/bin/env bash
#
# Smoke test of the deployed AI server (https://ai.grottocenter.org).
#
# Checks, in three sections:
#   A  no login needed: health, readiness, TLS, redirect, 401 without a valid token, CORS,
#      and that ports 8000 and 27017 do not answer from outside.
#   B  needs a Grottocenter login: another product's token is refused, a non-PDF and an
#      oversized upload are refused, a real PDF is analysed, and the same PDF a second
#      time is answered from storage with an identical result.
#   C  only with --ssh-logs: the server's logs hold no token, and show that the second
#      upload was served from storage.
#
# Cost: a default run starts ONE analysis (one GreenPT call for the synthetic PDF, which
# is different on every run). The repeat upload is served from storage and costs nothing.
# --ocr adds one more analysis, through GreenPT's OCR.
#
# Not run here, to do by hand (see the README, "Smoke test"):
#   - the daily quota: the 6th analysis of the day gets 429 with Retry-After (costs 5);
#   - the kill switch: ANALYZE_ENABLED=false gives 503;
#   - the largest real PDF, to see that a request over 2 minutes survives Traefik:
#     run with --pdf BIG.pdf and read the duration printed for the analysis.
#
# Exit code: 0 all checks passed, 1 at least one FAIL, 2 nothing failed but section B
# could not run (no login). Tokens, passwords and codes are never printed, never written
# to disk and never put on a command line.

set -uo pipefail

AI_URL=${AI_URL:-https://ai.grottocenter.org}
API_URL=${API_URL:-https://api.grottocenter.org/api/v1}
FRONT_ORIGIN=${FRONT_ORIGIN:-https://grottocenter.org}
SSH_TARGET=${SSH_TARGET:-azureuser@ai-vm.grottocenter.org}

PDF_FILE=""
MAX_FILE_SIZE_MB=${MAX_FILE_SIZE_MB:-60}
DO_OCR=0
LOCAL=0
SSH_KEY=""

usage() {
  cat <<'EOF'
Usage: scripts/smoke_test.sh [--pdf FILE] [--ocr] [--local] [--ssh-logs KEYFILE]

  --pdf FILE          document to analyse (default: a synthetic PDF generated on each run)
  --ocr               also upload a tiny PDF, which goes through GreenPT's OCR (one more analysis)
  --local             AI_URL is a local http server: skip the TLS, redirect and closed-port checks
  --ssh-logs KEYFILE  read the server's logs over SSH and check them (section C)

Environment: AI_URL, API_URL, FRONT_ORIGIN, GC_TOKEN (a Grottocenter user token: skips the
login prompt), SSH_TARGET, MAX_FILE_SIZE_MB (the server's limit, default 60: the oversized
upload is 2 MB over it).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --pdf) PDF_FILE=${2:-}; shift 2 || { echo "--pdf needs a file" >&2; exit 64; } ;;
    --ocr) DO_OCR=1; shift ;;
    --local) LOCAL=1; shift ;;
    --ssh-logs) SSH_KEY=${2:-}; shift 2 || { echo "--ssh-logs needs a key file" >&2; exit 64; } ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 64 ;;
  esac
done

for tool in curl python3; do
  command -v "$tool" > /dev/null 2>&1 || { echo "$tool is required" >&2; exit 64; }
done
if [ -n "$PDF_FILE" ] && [ ! -f "$PDF_FILE" ]; then
  echo "File not found: $PDF_FILE" >&2
  exit 64
fi
if [ -n "$SSH_KEY" ] && [ ! -f "$SSH_KEY" ]; then
  echo "Key file not found: $SSH_KEY" >&2
  exit 64
fi

AI_URL=${AI_URL%/}
API_URL=${API_URL%/}
TMP=$(mktemp -d "${TMPDIR:-/tmp}/ai-smoke.XXXXXX")
USER_JWT=""
PASSES=0
FAILS=0
SKIPPED_B=0

# shellcheck disable=SC2329  # called through the trap below
cleanup() {
  rm -rf "$TMP"
  unset GC_TOKEN USER_JWT GC_PASSWORD GC_TOTP
}
trap cleanup EXIT
trap 'exit 130' INT TERM

pass() { PASSES=$((PASSES + 1)); printf 'PASS  %s%s\n' "$1" "${2:+ - $2}"; }
fail() { FAILS=$((FAILS + 1)); printf 'FAIL  %s%s\n' "$1" "${2:+ - $2}"; }
info() { printf '      %s\n' "$1"; }
section() { printf '\n== %s\n' "$1"; }

# jget KEY: print the value at KEY (dots go into objects) from the JSON on stdin, or nothing.
jget() {
  python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)
    for key in sys.argv[1].split("."):
        value = value[key] if isinstance(value, dict) else None
    print("" if value is None else value)
except Exception:
    print("")
' "$1"
}

# A curl config that carries a bearer token. It is read from a pipe (process substitution),
# so the token is never on a command line, where `ps` could show it, and never in a file.
bearer_config() { printf 'header = "Authorization: Bearer %s"\n' "$1"; }

host_of() {
  local url=${1#*://}
  url=${url%%/*}
  printf '%s' "${url%%:*}"
}

# status_of URL [curl options...]: the HTTP status code, or 000 if nothing answered.
status_of() {
  local url=$1
  shift
  curl -sS -o /dev/null --max-time 20 -w '%{http_code}' "$@" "$url" 2> /dev/null || true
}

# ---------------------------------------------------------------------------------------
# Test documents
# ---------------------------------------------------------------------------------------

# make_pdf FILE LINES TAG: a valid one-page PDF with LINES lines of plain text. TAG makes
# the content, hence its hash, different on every run, so that each run really analyses.
make_pdf() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys

path, lines, tag = sys.argv[1], int(sys.argv[2]), sys.argv[3]
text = [
    "Spelunca - Bulletin de la Federation francaise de speleologie",
    "Numero 12 - Juin 2024 - ISSN 0245-9647 - Document de test synthetique " + tag,
    "Sommaire: exploration du reseau de la Combe aux Prestres, topographie des galeries,",
    "etude des crues de la riviere souterraine, compte rendu du congres regional,",
    "bibliographie speleologique de l'annee et vie des clubs de la region Bourgogne.",
]
body = []
for i in range(max(lines - len(text), 0)):
    body.append("Ligne %02d: la galerie principale descend vers la salle des Concretions "
                "puis rejoint le collecteur (%s)." % (i, tag))
rows = (text + body)[:lines]

def esc(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

stream = "BT /F1 9 Tf 36 800 Td 11 TL\n" + "".join("(%s) Tj T*\n" % esc(row) for row in rows) + "ET\n"
objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
    "/Resources << /Font << /F1 5 0 R >> >> >>",
    "<< /Length %d >>\nstream\n%sendstream" % (len(stream.encode("latin-1")), stream),
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
]
out = bytearray(b"%PDF-1.4\n")
offsets = []
for number, obj in enumerate(objects, start=1):
    offsets.append(len(out))
    out += ("%d 0 obj\n%s\nendobj\n" % (number, obj)).encode("latin-1")
xref = len(out)
out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)).encode("latin-1")
for offset in offsets:
    out += ("%010d 00000 n \n" % offset).encode("latin-1")
out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)).encode("latin-1")
open(path, "wb").write(bytes(out))
PY
}

# ---------------------------------------------------------------------------------------
# Login and tokens (section B)
# ---------------------------------------------------------------------------------------

# login_request EMAIL PASSWORD TOTP: POST /login. Prints "BODY<newline>HTTP_CODE".
# The credentials travel through the environment of one python3 process and a pipe.
login_request() {
  local body
  body=$(GC_EMAIL_IN=$1 GC_PASSWORD_IN=$2 GC_TOTP_IN=$3 python3 -c '
import json, os
data = {"email": os.environ["GC_EMAIL_IN"], "password": os.environ["GC_PASSWORD_IN"]}
if os.environ.get("GC_TOTP_IN"):
    data["totpCode"] = os.environ["GC_TOTP_IN"]
print(json.dumps(data))
')
  printf '%s' "$body" | curl -sS --max-time 20 -X POST -H 'Content-Type: application/json' \
    --data-binary @- -w '\n%{http_code}' "$API_URL/login" 2> /dev/null
  unset body
}

acquire_user_jwt() {
  if [ -n "${GC_TOKEN:-}" ]; then
    USER_JWT=$GC_TOKEN
    info "Using the token from GC_TOKEN."
    return 0
  fi
  if [ ! -t 0 ]; then
    info "No GC_TOKEN and no terminal to ask for a login: section B is skipped."
    return 1
  fi

  local email password totp response code json status
  printf 'Grottocenter email: ' >&2
  read -r email
  printf 'Password (not shown): ' >&2
  read -rs password
  printf '\n' >&2
  totp=""

  local attempt
  for attempt in 1 2; do
    response=$(login_request "$email" "$password" "$totp")
    code=${response##*$'\n'}
    json=${response%$'\n'*}
    status=$(printf '%s' "$json" | jget status)
    case "$code:$status" in
      200:Success)
        USER_JWT=$(printf '%s' "$json" | jget token)
        unset email password totp response json
        [ -n "$USER_JWT" ] && return 0
        info "The login answered Success without a token."
        return 1
        ;;
      401:MfaRequired)
        if [ "$attempt" = 2 ]; then
          info "The login asked for the one-time code again."
          break
        fi
        printf 'One-time code (6 digits, not shown): ' >&2
        read -rs totp
        printf '\n' >&2
        ;;
      401:MfaEnrollmentRequired) info "This administrator account has no two-factor login yet: enrol on grottocenter.org first."; break ;;
      401:Mismatch) info "Wrong email or password."; break ;;
      401:InvalidTotpCode) info "The one-time code is not valid."; break ;;
      401:TotpAlreadyUsed) info "That one-time code was already used: wait for the next one and run again."; break ;;
      401:MustReset) info "This account must reset its password first."; break ;;
      401:NotVerified) info "This account's email is not verified yet."; break ;;
      000:*) info "The login request got no answer from $API_URL."; break ;;
      *) info "The login answered HTTP $code."; break ;;
    esac
  done
  unset email password totp response json
  return 1
}

# sso_token PRODUCT VARNAME: put a fresh 30-second token for PRODUCT in the variable VARNAME
# (empty on failure, with the reason in SSO_ERROR). It sets variables, not stdout, because a
# command substitution would run in a subshell and lose SSO_ERROR.
sso_token() {
  local response code json
  SSO_ERROR=""
  response=$(curl -sS --max-time 20 -K <(bearer_config "$USER_JWT") -X POST \
    -H 'Content-Type: application/json' -d "{\"product\":\"$1\"}" \
    -w '\n%{http_code}' "$API_URL/sso/auth-token" 2> /dev/null)
  code=${response##*$'\n'}
  json=${response%$'\n'*}
  if [ "$code" = 200 ]; then
    printf -v "$2" '%s' "$(printf '%s' "$json" | jget token)"
  else
    printf -v "$2" '%s' ""
    SSO_ERROR="HTTP $code $(printf '%s' "$json" | jget message)"
  fi
}

# explain CODE: what an HTTP status from /documents/analyze usually means here.
explain() {
  case "$1" in
    401) printf 'the token was refused (expired, wrong product, or the server has another secret)' ;;
    413) printf 'the upload is over the size limit' ;;
    415|422) printf 'the file was refused as not a readable PDF' ;;
    429) printf 'this account used its daily quota (5 analyses a day) or has analyses running: see Retry-After, wait until 00:00 UTC, or use another account' ;;
    500) printf 'an unexpected server error: read the server logs (it is often MongoDB, check /ready)' ;;
    502) printf 'the analysis service (GreenPT) failed' ;;
    503) printf 'analyses are switched off (ANALYZE_ENABLED) or the global daily cap was reached' ;;
    504) printf 'the analysis service (GreenPT) did not answer in time' ;;
    000) printf 'no answer from the server' ;;
    *) printf '' ;;
  esac
}

# detail_of FILE: the "detail" of a JSON error body (the server's generic message), or nothing.
detail_of() {
  python3 -c '
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("detail", ""))
except Exception:
    print("")
' "$1"
}

# upload FILE TOKEN OUT [NAME]: POST the file; the body goes to OUT; prints "CODE SECONDS".
upload() {
  local file=$1 token=$2 out=$3 name=${4:-issue.pdf}
  curl -sS --max-time 600 -o "$out" -w '%{http_code} %{time_total}' \
    -K <(bearer_config "$token") -F "file=@${file};type=application/pdf;filename=${name}" \
    "$AI_URL/documents/analyze" 2> /dev/null || true
}

# ---------------------------------------------------------------------------------------
# Section A: no login needed
# ---------------------------------------------------------------------------------------
section "A. Server, TLS and refusals (no login)"

code=$(status_of "$AI_URL/health")
if [ "$code" = 200 ]; then pass "GET /health" "200"; else fail "GET /health" "HTTP $code"; fi

code=$(status_of "$AI_URL/ready")
if [ "$code" = 200 ]; then pass "GET /ready" "200 (MongoDB answers)"; else fail "GET /ready" "HTTP $code"; fi

# Answers carry no `server` header, which would name the HTTP server behind the API.
headers=$(curl -sS -D - -o /dev/null --max-time 20 "$AI_URL/health" 2> /dev/null || true)
if printf '%s' "$headers" | grep -qi '^server:'; then
  fail "no server header" "$(printf '%s' "$headers" | grep -i '^server:' | tr -d '\r')"
else
  pass "no server header" "none sent"
fi

# Every answer carries a trace id: a UUID sent by the caller is kept, otherwise one is made.
probe_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
echoed=$(curl -sS -D - -o /dev/null --max-time 20 -H "X-Trace-Id: $probe_id" "$AI_URL/health" 2> /dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-trace-id" {print $2}')
generated=$(curl -sS -D - -o /dev/null --max-time 20 "$AI_URL/health" 2> /dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-trace-id" {print $2}')
if [ "$echoed" = "$probe_id" ] && printf '%s' "$generated" | grep -qE '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'; then
  pass "trace id on every answer" "kept when sent, generated when not"
else
  fail "trace id on every answer" "sent $probe_id, got '${echoed:-none}'; without one got '${generated:-none}'"
fi

# The public documentation: the document and the page name neither the application nor
# the framework, and the page loads its files from this server only.
docs_bad=""
for path in /openapi.json /docs; do
  if curl -sS --max-time 20 "$AI_URL$path" 2> /dev/null | grep -qiE 'fastapi|starlette|pydantic|uvicorn|tiangolo|jsdelivr|AI Tools'; then
    docs_bad="$docs_bad $path"
  fi
done
docs_status=$(status_of "$AI_URL/docs")
external=$(curl -sS --max-time 20 "$AI_URL/docs" 2> /dev/null | grep -oE '(src|href)="https?://[^"]*"' | tr '\n' ' ' || true)
if [ "$docs_status" = 200 ] && [ -z "$docs_bad" ] && [ -z "$external" ]; then
  pass "public documentation" "/docs and /openapi.json: no framework name, nothing loaded from another host"
else
  fail "public documentation" "/docs HTTP $docs_status, names found in:${docs_bad:- none}, external references: ${external:-none}"
fi

if [ "$LOCAL" = 0 ]; then
  verify=$(curl -sS -o /dev/null --max-time 20 -w '%{ssl_verify_result}' "$AI_URL/health" 2> /dev/null || true)
  if [ "$verify" = 0 ]; then pass "TLS certificate verifies" "no -k needed"; else fail "TLS certificate verifies" "ssl_verify_result=${verify:-none} (0 means valid)"; fi

  http_url="http://${AI_URL#*://}"
  redirect=$(curl -sS -o /dev/null --max-time 20 -w '%{http_code} %{redirect_url}' "$http_url/health" 2> /dev/null || true)
  redirect=${redirect:-"000 "}
  rcode=${redirect%% *}
  rurl=${redirect#* }
  case "$rurl" in
    https://*) if [ "$rcode" = 301 ]; then pass "http redirects to https" "301"; else fail "http redirects to https" "HTTP $rcode"; fi ;;
    *) fail "http redirects to https" "HTTP $rcode, no https Location" ;;
  esac
else
  info "--local: TLS and redirect checks skipped."
fi

response=$(curl -sS --max-time 30 -X POST -F "file=@/dev/null;filename=a.pdf" -w '\n%{http_code}' "$AI_URL/documents/analyze" 2> /dev/null || true)
code=${response##*$'\n'}
detail=$(printf '%s' "${response%$'\n'*}" | jget detail)
if [ "$code" = 401 ] && [ "$detail" = "Invalid or missing token" ]; then
  pass "analyze without a token" "401, $detail"
else
  fail "analyze without a token" "HTTP $code, detail '$detail'"
fi

response=$(curl -sS --max-time 30 -X POST -H 'Authorization: Bearer abc.def.ghi' -F "file=@/dev/null;filename=a.pdf" -w '\n%{http_code}' "$AI_URL/documents/analyze" 2> /dev/null || true)
code=${response##*$'\n'}
detail=$(printf '%s' "${response%$'\n'*}" | jget detail)
if [ "$code" = 401 ] && [ "$detail" = "Invalid token" ]; then
  pass "analyze with a forged token" "401, $detail"
else
  fail "analyze with a forged token" "HTTP $code, detail '$detail'"
fi

headers=$(curl -sS --max-time 20 -o /dev/null -D - -X OPTIONS "$AI_URL/documents/analyze" \
  -H "Origin: $FRONT_ORIGIN" -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization' 2> /dev/null | tr -d '\r' || true)
pcode=$(printf '%s\n' "$headers" | awk 'NR==1 {print $2}')
allow=$(printf '%s\n' "$headers" | awk -F': ' 'tolower($1)=="access-control-allow-origin" {print $2}')
if [ "$pcode" = 200 ] && [ "$allow" = "$FRONT_ORIGIN" ]; then
  pass "CORS preflight from the front" "200, allows $allow"
else
  fail "CORS preflight from the front" "HTTP $pcode, allow-origin '$allow'"
fi

headers=$(curl -sS --max-time 20 -o /dev/null -D - -X OPTIONS "$AI_URL/documents/analyze" \
  -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: POST' 2> /dev/null | tr -d '\r' || true)
allow=$(printf '%s\n' "$headers" | awk -F': ' 'tolower($1)=="access-control-allow-origin" {print $2}')
if [ -z "$allow" ]; then
  pass "CORS preflight from another origin" "no allow-origin header"
else
  fail "CORS preflight from another origin" "allow-origin '$allow'"
fi

if [ "$LOCAL" = 0 ]; then
  ai_host=$(host_of "$AI_URL")
  for port in 8000 27017; do
    answer=$(curl -sS -o /dev/null --max-time 4 -w '%{http_code}' "http://$ai_host:$port/" 2> /dev/null || true)
    case "$answer" in
      ""|000) pass "port $port is closed from outside" "no answer in 4 s" ;;
      *) fail "port $port is closed from outside" "answered HTTP $answer" ;;
    esac
  done
else
  info "--local: closed-port checks skipped."
fi

# ---------------------------------------------------------------------------------------
# Section B: needs a login
# ---------------------------------------------------------------------------------------
section "B. Documents (login)"

# Both documents are generated on every run, so each run really analyses (and pays for) one.
RUN_TAG="run-$(date +%Y%m%d%H%M%S)-$$"
if [ -n "$PDF_FILE" ]; then
  DOC=$PDF_FILE
  info "Analysing your file: $PDF_FILE (if it was analysed before, the first answer comes from storage too)."
else
  DOC="$TMP/synthetic.pdf"
  make_pdf "$DOC" 40 "$RUN_TAG"
fi

SSO_ERROR=""
if acquire_user_jwt; then
  # Another product's token must not work here.
  sso_token superset other
  if [ -z "$other" ]; then
    fail "cross-product token refused" "could not get a superset token: $SSO_ERROR"
  else
    code=$(upload "$DOC" "$other" "$TMP/out-superset.json" | awk '{print $1}')
    if [ "$code" = 401 ]; then pass "token for another product (superset) refused" "401"; else fail "token for another product (superset) refused" "HTTP $code, expected 401"; fi
  fi
  unset other

  sso_token documents token
  if [ -z "$token" ]; then
    fail "documents token from the API" "$SSO_ERROR"
    SKIPPED_B=1
  else
    pass "documents token from the API" "POST /sso/auth-token"

    # A text file with a .pdf name.
    printf 'This is not a PDF.\n' > "$TMP/not-a-pdf.pdf"
    result=$(upload "$TMP/not-a-pdf.pdf" "$token" "$TMP/out-text.json" "fake.pdf")
    code=${result%% *}
    case "$code" in
      415|422) pass "a text file named .pdf is refused" "HTTP $code" ;;
      *) fail "a text file named .pdf is refused" "HTTP $code, expected 415 or 422" ;;
    esac

    # An upload over the limit, refused without being received.
    sso_token documents token
    dd if=/dev/zero of="$TMP/oversized.pdf" bs=1048576 count=$((MAX_FILE_SIZE_MB + 2)) 2> /dev/null
    result=$(upload "$TMP/oversized.pdf" "$token" "$TMP/out-big.json" "big.pdf")
    rm -f "$TMP/oversized.pdf"
    code=${result%% *}
    seconds=${result#* }
    if [ "$code" = 413 ] && python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < 20 else 1)' "$seconds"; then
      pass "a $((MAX_FILE_SIZE_MB + 2)) MB upload is refused" "413 in ${seconds}s"
    else
      fail "a $((MAX_FILE_SIZE_MB + 2)) MB upload is refused" "HTTP $code in ${seconds}s, expected 413 under 20 s"
    fi

    # The real analysis.
    sso_token documents token
    result=$(upload "$DOC" "$token" "$TMP/out-1.json")
    code=${result%% *}
    first_seconds=${result#* }
    count=$(python3 -c '
import json, sys
try:
    body = json.load(open(sys.argv[1]))
    docs = body.get("document_metadata") or []
    ok = bool(body.get("filename")) and isinstance(docs, list) and len(docs) > 0
    title = (docs[0].get("title") if docs and isinstance(docs[0], dict) else "") or ""
    print("%d\t%s" % (len(docs) if ok else 0, title))
except Exception:
    print("0\t")
' "$TMP/out-1.json")
    n_docs=${count%%$'\t'*}
    title=${count#*$'\t'}
    if [ "$code" = 200 ] && [ "${n_docs:-0}" -gt 0 ]; then
      pass "analysis of the document" "200 in ${first_seconds}s, $n_docs document(s), first title: ${title:-none}"
      if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) > 120 else 1)' "$first_seconds"; then
        info "That request took over 2 minutes and still went through Traefik."
      fi

      # The same file again: answered from storage.
      sso_token documents token
      result=$(upload "$DOC" "$token" "$TMP/out-2.json")
      code2=${result%% *}
      second_seconds=${result#* }
      verdict=$(python3 -c '
import json, sys
try:
    first = json.load(open(sys.argv[1])).get("document_metadata")
    second = json.load(open(sys.argv[2])).get("document_metadata")
except Exception:
    print("unreadable"); sys.exit(0)
if json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True):
    print("identical")
else:
    differing = sorted({k for a, b in zip(first or [], second or []) if isinstance(a, dict) and isinstance(b, dict)
                        for k in set(a) | set(b) if a.get(k) != b.get(k)})
    print("different: lists %d/%d, differing keys: %s" % (len(first or []), len(second or []), ", ".join(differing) or "none"))
' "$TMP/out-1.json" "$TMP/out-2.json")
      if [ "$code2" = 200 ] && [ "$verdict" = identical ]; then
        pass "same file again is served from storage" "200 in ${second_seconds}s, identical result"
        if python3 -c 'import sys; sys.exit(0 if float(sys.argv[2]) < float(sys.argv[1]) else 1)' "$first_seconds" "$second_seconds"; then
          info "Durations: first ${first_seconds}s, second ${second_seconds}s."
        else
          info "Note: the second answer (${second_seconds}s) was not faster than the first (${first_seconds}s)."
        fi
      else
        fail "same file again is served from storage" "HTTP $code2, result $verdict; $(explain "$code2")"
      fi
    else
      fail "analysis of the document" "HTTP $code in ${first_seconds}s, ${n_docs:-0} document(s), detail '$(detail_of "$TMP/out-1.json")'; $(explain "$code")"
    fi

    if [ "$DO_OCR" = 1 ]; then
      make_pdf "$TMP/tiny.pdf" 5 "$RUN_TAG-ocr"
      sso_token documents token
      result=$(upload "$TMP/tiny.pdf" "$token" "$TMP/out-ocr.json" "tiny.pdf")
      code=${result%% *}
      if [ "$code" = 200 ]; then
        pass "tiny PDF through the OCR path" "200 in ${result#* }s"
      else
        fail "tiny PDF through the OCR path" "HTTP $code; $(explain "$code")"
      fi
    fi
  fi
else
  SKIPPED_B=1
fi
unset token

# ---------------------------------------------------------------------------------------
# Section C: the server's logs
# ---------------------------------------------------------------------------------------
if [ -n "$SSH_KEY" ]; then
  section "C. Server logs (SSH)"
  # A request with a known trace id that matches no route: it must show up in the logs with that id.
  log_probe_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
  curl -sS -o /dev/null --max-time 20 -H "X-Trace-Id: $log_probe_id" "$AI_URL/smoke-test-log-probe" 2> /dev/null || true
  sleep 1
  logs=$(ssh -i "$SSH_KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=15 "$SSH_TARGET" 'docker logs --tail 300 ai-server 2>&1' 2> /dev/null)
  ssh_status=$?
  if [ "$ssh_status" != 0 ] || [ -z "$logs" ]; then
    fail "read the server logs" "ssh to $SSH_TARGET failed (status $ssh_status)"
  else
    jwt_lines=$(printf '%s\n' "$logs" | grep -cE 'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.' || true)
    auth_lines=$(printf '%s\n' "$logs" | grep -c 'Authorization' || true)
    if [ "$jwt_lines" = 0 ] && [ "$auth_lines" = 0 ]; then
      pass "no token in the last 300 log lines" "no JWT-shaped string, no Authorization header"
    else
      fail "no token in the last 300 log lines" "$jwt_lines JWT-shaped line(s), $auth_lines Authorization line(s)"
    fi

    if printf '%s\n' "$logs" | grep "$log_probe_id" | grep -q '"http_status": 404'; then
      pass "a request is logged with its trace id" "$log_probe_id found with its status"
    else
      fail "a request is logged with its trace id" "$log_probe_id not found in the last 300 log lines"
    fi

    printf '%s\n' "$logs" | grep 'analysis caller=' | tail -n 6 | while IFS= read -r line; do info "${line#*analysis }"; done

    if command -v shasum > /dev/null 2>&1; then
      prefix=$(shasum -a 256 "$DOC" | cut -c1-12)
    else
      prefix=$(sha256sum "$DOC" | cut -c1-12)
    fi
    last_source=$(printf '%s\n' "$logs" | grep "analysis caller=.* hash=$prefix " | tail -n 1 | sed -n 's/.* source=\([a-z]*\).*/\1/p')
    if [ "$SKIPPED_B" = 0 ] && [ "$last_source" = storage ]; then
      pass "the second upload was served from storage" "last log line for hash $prefix says source=storage"
    elif [ "$SKIPPED_B" = 1 ]; then
      info "Section B did not run, so no upload to look for in the logs."
    else
      fail "the second upload was served from storage" "last log line for hash $prefix says source='${last_source:-none}'"
    fi
  fi
fi

# ---------------------------------------------------------------------------------------
section "Summary"
printf '%d passed, %d failed' "$PASSES" "$FAILS"
if [ "$SKIPPED_B" = 1 ]; then printf ', section B not run'; fi
printf '\n'
if [ "$FAILS" -gt 0 ]; then exit 1; fi
if [ "$SKIPPED_B" = 1 ]; then exit 2; fi
exit 0
