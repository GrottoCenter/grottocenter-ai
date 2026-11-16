from types import SimpleNamespace

import httpx
import mongomock
import pymongo.errors
import pytest

from application import create_app
from config.settings import (
    SettingsError,
    parse_cors_origins,
    resolve_log_level,
    validate_settings,
)
from controller.documentController import get_document_service

FRONT_ORIGIN = "https://grottocenter.org"
OTHER_ORIGIN = "https://evil.example"


def make_config(**overrides) -> SimpleNamespace:
    values = {
        "api_key": "dummy-greenpt-key",
        "greenpt_api_url": "https://greenpt.test/v1",
        "sso_salt_documents": "s" * 32,
        "mongo_uri": "mongodb://mongo.test:27017",
        "mongo_db_name": "grottocenter_test",
        "cors_origins": [FRONT_ORIGIN],
        "log_level": "INFO",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeMongoClient:
    """Records how it is created and closed; the database behind it is mongomock."""

    instances: list["FakeMongoClient"] = []

    def __init__(self, uri: str, **kwargs) -> None:
        self.uri = uri
        self.kwargs = kwargs
        self.closed = False
        self.ping_error: Exception | None = None
        self.admin = SimpleNamespace(command=self._command)
        self._backend = mongomock.MongoClient()
        FakeMongoClient.instances.append(self)

    def _command(self, name: str):
        if self.ping_error is not None:
            raise self.ping_error
        return {"ok": 1.0}

    def __getitem__(self, database_name: str):
        return self._backend[database_name]

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def fresh_fake_clients():
    FakeMongoClient.instances = []
    yield
    FakeMongoClient.instances = []


def build_app(**config_overrides):
    return create_app(make_config(**config_overrides), FakeMongoClient)


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


# --- CORS ---------------------------------------------------------------------


async def test_cors_request_from_unlisted_origin_gets_no_cors_headers():
    async with client_for(build_app()) as client:
        response = await client.get("/health", headers={"Origin": OTHER_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_cors_request_from_listed_origin_is_allowed_without_credentials():
    async with client_for(build_app()) as client:
        response = await client.get("/health", headers={"Origin": FRONT_ORIGIN})

    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


async def test_cors_preflight_for_analyze_from_listed_origin_is_accepted():
    async with client_for(build_app()) as client:
        response = await client.options(
            "/documents/analyze",
            headers={
                "Origin": FRONT_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


async def test_cors_preflight_from_unlisted_origin_is_refused():
    async with client_for(build_app()) as client:
        response = await client.options(
            "/documents/analyze",
            headers={
                "Origin": OTHER_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_cors_with_no_configured_origins_allows_no_browser_origin():
    async with client_for(build_app(cors_origins=[])) as client:
        response = await client.get("/health", headers={"Origin": FRONT_ORIGIN})

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        (" , ,", []),
        (FRONT_ORIGIN, [FRONT_ORIGIN]),
        (
            "https://a.example, https://b.example/ ,,http://localhost:3000",
            ["https://a.example", "https://b.example", "http://localhost:3000"],
        ),
    ],
)
def test_parse_cors_origins_trims_entries_and_drops_empty_ones(raw, expected):
    assert parse_cors_origins(raw) == expected


async def test_startup_refuses_wildcard_cors_origin_before_creating_any_client():
    app = build_app(cors_origins=["*"])

    with pytest.raises(SettingsError) as error:
        async with app.router.lifespan_context(app):
            pass

    assert error.value.problems == [
        "CORS_ORIGINS must not contain '*': list the allowed origins explicitly"
    ]
    assert FakeMongoClient.instances == []


# --- liveness and readiness -----------------------------------------------------


async def test_health_answers_without_the_lifespan_and_without_mongodb():
    async with client_for(build_app()) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "API is running"}


async def test_ready_answers_200_when_mongodb_responds_to_ping():
    app = build_app()

    async with app.router.lifespan_context(app):
        async with client_for(app) as client:
            response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "API is ready"}


async def test_ready_answers_503_without_leaking_the_uri_when_ping_fails():
    app = build_app(mongo_uri="mongodb://user:hunter2@mongo.test:27017")

    async with app.router.lifespan_context(app):
        FakeMongoClient.instances[0].ping_error = (
            pymongo.errors.ServerSelectionTimeoutError("mongo.test:27017 timed out")
        )
        async with client_for(app) as client:
            response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "message": "MongoDB is not reachable",
    }
    assert "hunter2" not in response.text


async def test_ready_answers_503_before_the_lifespan_has_created_the_client():
    async with client_for(build_app()) as client:
        response = await client.get("/ready")

    assert response.status_code == 503


# --- startup validation --------------------------------------------------------


def test_validate_settings_accepts_a_complete_configuration():
    assert validate_settings(make_config()) == []


def test_validate_settings_lists_every_missing_setting_together():
    config = make_config(
        mongo_uri="", mongo_db_name="", api_key="", sso_salt_documents=""
    )

    assert validate_settings(config) == [
        "MONGO_URI is required",
        "MONGO_DB_NAME is required",
        "GREENPT_API_KEY is required",
        "SSO_SALT_DOCUMENTS is required",
    ]


async def test_startup_failure_names_each_missing_setting_and_prints_no_secret():
    app = build_app(
        mongo_uri="",
        mongo_db_name="",
        api_key="greenpt-key-must-not-appear",
        sso_salt_documents="short-secret-must-not-appear",
    )

    with pytest.raises(SettingsError) as error:
        async with app.router.lifespan_context(app):
            pass

    message = str(error.value)
    assert "MONGO_URI is required" in message
    assert "MONGO_DB_NAME is required" in message
    assert "SSO_SALT_DOCUMENTS must be at least 32 bytes" in message
    assert "greenpt-key-must-not-appear" not in message
    assert "short-secret-must-not-appear" not in message
    assert FakeMongoClient.instances == []


def test_sso_secret_of_31_bytes_is_rejected():
    config = make_config(sso_salt_documents="a" * 31)

    assert validate_settings(config) == ["SSO_SALT_DOCUMENTS must be at least 32 bytes"]


def test_sso_secret_of_32_bytes_is_accepted():
    assert validate_settings(make_config(sso_salt_documents="a" * 32)) == []


def test_sso_secret_length_is_counted_in_bytes_not_characters():
    sixteen_two_byte_characters = "é" * 16
    fifteen_two_byte_characters = "é" * 15

    assert validate_settings(make_config(sso_salt_documents=sixteen_two_byte_characters)) == []
    assert validate_settings(make_config(sso_salt_documents=fifteen_two_byte_characters)) == [
        "SSO_SALT_DOCUMENTS must be at least 32 bytes"
    ]


def test_unknown_log_level_is_reported():
    assert validate_settings(make_config(log_level="LOUD")) == [
        "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("DEBUG", 10), ("info", 20), ("WARNING", 30), ("LOUD", 20), ("", 20)],
)
def test_log_level_names_resolve_to_numeric_levels_with_info_as_fallback(name, expected):
    assert resolve_log_level(name) == expected


# --- MongoDB client lifecycle -----------------------------------------------------


async def test_mongo_client_is_created_with_the_configured_uri_and_a_short_timeout():
    app = build_app(mongo_uri="mongodb://mongo.test:27017/app")

    async with app.router.lifespan_context(app):
        pass

    (client,) = FakeMongoClient.instances
    assert client.uri == "mongodb://mongo.test:27017/app"
    assert client.kwargs == {"serverSelectionTimeoutMS": 3000}


async def test_mongo_client_is_open_while_serving_and_closed_on_shutdown():
    app = build_app()

    async with app.router.lifespan_context(app):
        (client,) = FakeMongoClient.instances
        assert client.closed is False

    assert client.closed is True


async def test_mongo_client_is_closed_when_the_application_stops_with_an_error():
    app = build_app()

    with pytest.raises(RuntimeError, match="boom"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("boom")

    assert FakeMongoClient.instances[0].closed is True


async def test_document_service_uses_the_database_owned_by_the_lifespan():
    app = build_app(mongo_db_name="grottocenter_lifespan")

    async with app.router.lifespan_context(app):
        request = SimpleNamespace(app=app)
        service = get_document_service(request)

    assert service.mongo_repository.db.name == "grottocenter_lifespan"
