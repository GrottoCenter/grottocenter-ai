"""The detailed logs for the test phase: the original file name, the answer, what the model said.

They exist only when LOG_ANALYSIS_DETAILS is true, and are fully absent otherwise.
"""

import json
from pathlib import Path

import pytest

from config.settings import UsageLimits, validate_settings
from logdetails import (
    MAX_FILE_NAME,
    RESULT_CHARACTERS,
    UPSTREAM_BODY_CHARACTERS,
    clean_file_name,
)
from tests.limits_support import (
    CHAT_URL,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tests.test_trace_id import TRACE_A

ROOT = Path(__file__).resolve().parent.parent
FILE_NAME = "Rapport Gouffre Berger 2024.pdf"


def upload(client, data, name=FILE_NAME, content_type="application/pdf", **headers):
    from tests.test_auth import mint

    return client.post(
        "/documents/analyze",
        files={"file": (name, data, content_type)},
        headers={"Authorization": f"Bearer {mint(sub=42)}", **headers},
    )


def detail_lines(lines):
    return [line for line in lines if line["logger"] == "service.documentService"]


# --- off by default -----------------------------------------------------------------------


async def test_nothing_of_the_document_is_logged_when_the_switch_is_off(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply('{"title": "Titre secret"}'))
    async with running_app() as (_app, client):
        response = await upload(client, distinct_pdf(1))

    text = json.dumps(log_lines(), ensure_ascii=False)
    assert response.status_code == 200
    assert "Rapport Gouffre" not in text and "Titre secret" not in text
    assert not any("file_name" in line or "result_json" in line for line in log_lines())


def test_the_switch_is_off_unless_it_is_set():
    assert getattr(make_limits_config(), "log_analysis_details", False) is False
    assert UsageLimits().__dict__.get("log_analysis_details") is None  # not part of the limits


# --- on ------------------------------------------------------------------------------------


async def test_the_request_line_has_the_original_name_the_size_and_the_trace_id(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    data = distinct_pdf(1)
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, data, **{"X-Trace-Id": TRACE_A})

    [line] = [item for item in detail_lines(log_lines()) if item["message"].startswith("analysis request")]
    assert line["file_name"] == FILE_NAME
    assert line["file_size_bytes"] == len(data)
    assert line["content_type"] == "application/pdf"
    assert line["trace_id"] == TRACE_A


async def test_the_result_line_has_the_answer_and_says_whether_it_came_from_storage(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply('{"title": "Gouffre Berger", "grottocenter_type": "book"}'))
    data = distinct_pdf(1)
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, data)
        await upload(client, data)

    results = [line for line in detail_lines(log_lines()) if line["message"].startswith("analysis result")]
    assert [line["source"] for line in results] == ["analyzed", "storage"]
    answers = [json.loads(line["result_json"]) for line in results]
    assert answers[0] == answers[1]
    assert answers[0][0]["title"] == "Gouffre Berger"
    assert results[0]["result_truncated"] is False


async def test_a_refused_file_still_has_its_name_in_the_log(log_lines):
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        response = await upload(client, b"This is not a PDF.\n", name="notes de terrain.pdf", content_type="text/plain")

    request_lines = [line for line in detail_lines(log_lines()) if line["message"].startswith("analysis request")]
    assert response.status_code == 415
    assert [line["file_name"] for line in request_lines] == ["notes de terrain.pdf"]


# --- the name is cleaned -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Rapport 2024.pdf", "Rapport 2024.pdf"),
        ("a\nb\rc\td.pdf", "a b c d.pdf"),
        ("evil\x1b[31m.pdf", "evil [31m.pdf"),
        ("../../etc/passwd.pdf", "../../etc/passwd.pdf"),
        ('quote".pdf', 'quote".pdf'),
        ("  spaced   name .pdf ", "spaced name .pdf"),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_file_name(raw, expected):
    assert clean_file_name(raw) == expected


def test_clean_file_name_cuts_a_long_name():
    cleaned = clean_file_name("n" * 1000 + ".pdf")

    assert len(cleaned) == MAX_FILE_NAME


async def test_a_hostile_name_stays_on_one_json_line(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1), name='x"}\n{"level": "CRITICAL", "message": "forged".pdf')

    lines = log_lines()  # parsing each line as JSON fails if the name broke a line
    names = [line["file_name"] for line in lines if "file_name" in line]
    assert names and all("\n" not in name for name in names)
    assert not any(line.get("message") == "forged" for line in lines)


# --- what the model said and what GreenPT said --------------------------------------------


async def test_the_raw_answer_is_logged_when_the_model_returns_no_json(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply("Désolé, je ne peux pas analyser ce document."))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1))

    [line] = [item for item in log_lines() if "raw_answer" in item]
    assert "Désolé, je ne peux pas" in line["raw_answer"]
    assert line["level"] == "WARNING"


async def test_the_raw_answer_is_not_logged_when_the_switch_is_off(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply("Désolé, je ne peux pas analyser ce document."))
    async with running_app() as (_app, client):
        await upload(client, distinct_pdf(1))

    assert "Désolé" not in json.dumps(log_lines(), ensure_ascii=False)


async def test_the_values_of_dropped_fields_are_logged_only_with_the_switch(respx_mock, log_lines):
    answer = '{"title": "Un titre", "grottocenter_type": "not-a-type-at-all"}'
    respx_mock.post(CHAT_URL).respond(json=chat_reply(answer))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1))

    [line] = [item for item in log_lines() if "raw_answer" in item and "dropped" in item["message"]]
    assert "not-a-type-at-all" in line["raw_answer"]


@pytest.mark.parametrize("switch, expected", [(False, 500), (True, UPSTREAM_BODY_CHARACTERS)])
async def test_the_logged_greenpt_error_body_is_longer_with_the_switch(respx_mock, log_lines, switch, expected):
    respx_mock.post(CHAT_URL).respond(500, text="e" * 5000)
    async with running_app(make_limits_config(log_analysis_details=switch)) as (_app, client):
        await upload(client, distinct_pdf(1))

    [line] = [item for item in log_lines() if item["logger"] == "client.GreenPT"]
    assert line["message"].count("e") >= expected
    assert line["message"].count("e") < expected + 200  # the words of the message itself


# --- configuration -------------------------------------------------------------------------


def test_a_value_that_is_not_true_or_false_stops_the_startup_and_names_the_variable():
    problems = validate_settings(make_limits_config(log_analysis_details="maybe"))

    assert "LOG_ANALYSIS_DETAILS must be true or false" in problems


def test_the_switch_reaches_the_container_from_every_compose_file_and_the_example():
    for name in ("docker-compose.yml", "docker-compose.dev.yml"):
        assert "LOG_ANALYSIS_DETAILS" in (ROOT / name).read_text(), name
    assert "LOG_ANALYSIS_DETAILS=false" in (ROOT / ".env.example").read_text()


async def test_the_biggest_detailed_line_stays_under_the_size_rsyslog_accepts(respx_mock, log_lines):
    # Quotes in the metadata are escaped twice (JSON inside JSON), the worst case for the size.
    heavy = json.dumps({"title": "T", "descriptions": ['say "hello" ' * 2000]})
    respx_mock.post(CHAT_URL).respond(json=chat_reply(heavy))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1), name="n" * 500 + ".pdf")

    import logging

    from tracing import JsonFormatter

    formatter = JsonFormatter()
    sizes = []
    for line in log_lines():
        record = logging.LogRecord(line["logger"], logging.INFO, __file__, 1, line["message"], None, None)
        for key, value in line.items():
            if key not in ("timestamp", "level", "logger", "message"):
                setattr(record, key, value)
        sizes.append(len(formatter.format(record).encode()))
    assert max(sizes) < 8192


# --- an answer that does not fit is shown in a shorter form that can still be read --------


def many_articles(count: int) -> str:
    articles = [
        {"title": f"Article numéro {number}", "authors": ["A. Martin"], "page_start": number, "page_end": number + 1}
        for number in range(1, count + 1)
    ]
    return json.dumps(
        {
            "title": "Numéro spécial",
            "grottocenter_type": "issue",
            "descriptions": ["Un long résumé du numéro. " * 40],
            "articles": articles,
        }
    )


async def test_an_answer_too_long_for_one_line_is_logged_as_titles_and_stays_readable(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply(many_articles(18)))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        response = await upload(client, distinct_pdf(1))

    [line] = [item for item in detail_lines(log_lines()) if item["message"].startswith("analysis result")]
    shown = json.loads(line["result_json"])  # fails if the text was cut in the middle
    assert response.status_code == 200
    assert line["result_compact"] is True and line["result_truncated"] is False
    assert len(shown) == 19  # the issue and its 18 articles, none dropped
    assert [item["title"] for item in shown[1:4]] == ["Article numéro 1", "Article numéro 2", "Article numéro 3"]
    assert set(shown[0]) == {"title", "grottocenter_type", "pages"}


async def test_an_answer_that_fits_is_logged_whole(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply('{"title": "Court", "descriptions": ["Un résumé."]}'))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1))

    [line] = [item for item in detail_lines(log_lines()) if item["message"].startswith("analysis result")]
    assert line["result_compact"] is False
    assert json.loads(line["result_json"])[0]["descriptions"] == ["Un résumé."]


async def test_even_the_short_form_is_cut_when_there_are_hundreds_of_documents(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply(many_articles(400)))
    async with running_app(make_limits_config(log_analysis_details=True)) as (_app, client):
        await upload(client, distinct_pdf(1))

    [line] = [item for item in detail_lines(log_lines()) if item["message"].startswith("analysis result")]
    assert (line["result_compact"], line["result_truncated"]) == (True, True)
    assert len(line["result_json"]) == RESULT_CHARACTERS
