from types import SimpleNamespace

import mongomock
import pytest

from config.settings import (
    UsageLimits,
    parse_bool,
    parse_positive_int,
    validate_settings,
)
from scripts.init_db import ensure_usage_indexes
from tests.limits_support import make_limits_config

LIMIT_VARIABLES = [
    ("USER_DAILY_LIMIT", "user_daily_limit", 1_000),
    ("USER_MAX_CONCURRENT", "user_max_concurrent", 20),
    ("GLOBAL_DAILY_LIMIT", "global_daily_limit", 100_000),
    ("MAX_FILE_SIZE_MB", "max_file_size_mb", 200),
    ("MAX_PAGES", "max_pages", 5_000),
    ("MAX_LLM_CALLS", "max_llm_calls", 100),
]


def test_production_defaults_are_the_agreed_limits():
    limits = UsageLimits()

    assert limits.analyze_enabled is True
    assert limits.user_daily_limit == 5
    assert limits.user_max_concurrent == 2
    assert limits.global_daily_limit == 200
    assert limits.max_file_size_mb == 60
    assert limits.max_file_size_bytes == 62_914_560
    assert limits.max_pages == 300
    assert limits.max_llm_calls == 10


def test_limits_from_a_configuration_without_limit_attributes_use_the_defaults():
    limits = UsageLimits.from_config(SimpleNamespace(max_pages=12))

    assert limits.max_pages == 12
    assert limits.user_daily_limit == 5


def test_a_valid_configuration_has_no_problem():
    assert validate_settings(make_limits_config()) == []


def test_a_configuration_without_limit_attributes_is_still_valid():
    config = make_limits_config()
    for _, attribute, _ in LIMIT_VARIABLES:
        delattr(config, attribute)
    del config.analyze_enabled

    assert validate_settings(config) == []


@pytest.mark.parametrize(("variable", "attribute", "maximum"), LIMIT_VARIABLES)
@pytest.mark.parametrize("bad_value", [0, -1, None, "7", 2.5, True])
def test_limit_that_is_not_a_positive_integer_is_reported_by_name(
    variable, attribute, maximum, bad_value
):
    problems = validate_settings(make_limits_config(**{attribute: bad_value}))

    assert problems == [f"{variable} must be an integer between 1 and {maximum}"]


@pytest.mark.parametrize(("variable", "attribute", "maximum"), LIMIT_VARIABLES)
def test_limit_is_accepted_up_to_its_maximum_and_refused_above(variable, attribute, maximum):
    assert validate_settings(make_limits_config(**{attribute: maximum})) == []
    assert validate_settings(make_limits_config(**{attribute: maximum + 1})) == [
        f"{variable} must be an integer between 1 and {maximum}"
    ]


def test_analyze_enabled_that_is_not_a_boolean_is_reported():
    problems = validate_settings(make_limits_config(analyze_enabled=None))

    assert problems == ["ANALYZE_ENABLED must be true or false"]


def test_problem_messages_never_contain_the_offending_value():
    problems = validate_settings(make_limits_config(max_pages="not-a-number-9f3a"))

    assert "9f3a" not in " ".join(problems)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12", 12), ("  12  ", 12), ("", 5), ("   ", 5), ("abc", None), ("1.5", None), ("12x", None)],
)
def test_integer_environment_variable_is_parsed_or_marked_invalid(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_LIMIT", raw)

    assert parse_positive_int("SOME_LIMIT", 5) == expected


def test_integer_environment_variable_that_is_not_set_uses_the_default(monkeypatch):
    monkeypatch.delenv("SOME_LIMIT", raising=False)

    assert parse_positive_int("SOME_LIMIT", 5) == 5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("off", False),
        (" false ", False),
        ("", True),
        ("maybe", None),
    ],
)
def test_boolean_environment_variable_is_parsed_or_marked_invalid(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_FLAG", raw)

    assert parse_bool("SOME_FLAG", True) is expected


# --- the TTL index created by scripts/init_db.py --------------------------------


def test_usage_counters_expire_through_a_ttl_index_on_expires_at():
    database = mongomock.MongoClient()["init_test"]

    ensure_usage_indexes(database)

    index = database["usage"].index_information()["expiresAt_ttl"]
    assert index["key"] == [("expiresAt", 1)]
    assert index["expireAfterSeconds"] == 0


def test_creating_the_usage_indexes_twice_changes_nothing():
    database = mongomock.MongoClient()["init_test"]
    ensure_usage_indexes(database)
    before = database["usage"].index_information()

    ensure_usage_indexes(database)

    assert database["usage"].index_information() == before
