"""Nothing a consumer can read names the framework or a library behind the API."""

import re
import shlex
from pathlib import Path

import pytest

from tests.limits_support import (
    CHAT_URL,
    analyze,
    chat_reply,
    distinct_pdf,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tests.test_auth import mint

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["fastapi", "starlette", "pydantic", "uvicorn", "tiangolo", "python-multipart"]


def fingerprints(response) -> list[str]:
    seen = response.text.lower() + " " + str(dict(response.headers)).lower()
    return [name for name in NAMES if name in seen]


async def test_request_without_a_file_field_gets_the_usual_detail_body_and_no_library_url():
    async with running_app() as (_app, client):
        response = await client.post(
            "/documents/analyze",
            data={"other": "value"},
            files={"x": ("x.txt", b"x")},
            headers={"Authorization": f"Bearer {mint(sub=42)}"},
        )

    body = response.json()
    assert response.status_code == 422
    assert list(body) == ["detail"]
    assert body["detail"] == "Invalid request: file: Field required"
    assert fingerprints(response) == []


async def test_request_that_is_not_multipart_gets_the_usual_detail_body():
    async with running_app() as (_app, client):
        response = await client.post(
            "/documents/analyze",
            json={"file": "x"},
            headers={"Authorization": f"Bearer {mint(sub=42)}"},
        )

    assert response.status_code == 422
    assert list(response.json()) == ["detail"]
    assert response.json()["detail"].startswith("Invalid request: ")
    assert fingerprints(response) == []
    assert "http" not in response.json()["detail"].lower()


async def test_unknown_path_and_wrong_method_answer_with_the_usual_detail_body():
    async with running_app() as (_app, client):
        missing = await client.get("/nothing-here")
        wrong_method = await client.get("/documents/analyze")

    assert (missing.status_code, missing.json()) == (404, {"detail": "Not Found"})
    assert (wrong_method.status_code, wrong_method.json()) == (405, {"detail": "Method Not Allowed"})
    assert fingerprints(missing) == [] and fingerprints(wrong_method) == []


async def test_success_and_refusal_answers_name_no_framework(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app() as (_app, client):
        ok = await analyze(client, distinct_pdf(1))
        unauthorized = await client.post(
            "/documents/analyze", files={"file": ("a.pdf", b"x", "application/pdf")}
        )
        root = await client.get("/")

    assert [r.status_code for r in (ok, unauthorized, root)] == [200, 401, 200]
    assert [fingerprints(r) for r in (ok, unauthorized, root)] == [[], [], []]
    assert "AI Tools" not in root.text


def command_of(path: Path, pattern: str) -> list[str]:
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    assert match, f"no uvicorn command found in {path.name}"
    return shlex.split(match.group(1).replace('"', " ").replace(",", " "))


@pytest.mark.parametrize(
    "path, pattern",
    [
        ("AI_Serveur/Dockerfile", r"^CMD \[(\"uvicorn\".*)\]"),
        ("docker-compose.dev.yml", r"command: \[(\"uvicorn\".*)\]"),
    ],
)
def test_uvicorn_is_started_without_its_server_header(path, pattern):
    assert "--no-server-header" in command_of(ROOT / path, pattern)


def test_the_entry_point_run_by_hand_has_no_server_header_either():
    assert "server_header=False" in (ROOT / "AI_Serveur/main.py").read_text()
