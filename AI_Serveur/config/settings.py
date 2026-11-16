import logging
import os
from dataclasses import dataclass

# PyJWT warns on HMAC keys shorter than the hash output (RFC 7518, section 3.2).
MIN_SSO_SECRET_BYTES = 32
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Defaults for the cost and abuse limits. Anyone with a verified Grottocenter account may
# analyse, and sign-up is open, so these numbers are the protection against running up
# the GreenPT bill. GLOBAL_DAILY_LIMIT is a placeholder until the price of one analysis
# is known.
DEFAULT_USER_DAILY_LIMIT = 5
DEFAULT_USER_MAX_CONCURRENT = 2
DEFAULT_GLOBAL_DAILY_LIMIT = 200
DEFAULT_MAX_FILE_SIZE_MB = 50
DEFAULT_MAX_PAGES = 300
DEFAULT_MAX_LLM_CALLS = 10

# Upper bounds that catch a typo (an extra zero) rather than express a policy.
INTEGER_SETTINGS = (
    # (variable, attribute, default, maximum)
    ("USER_DAILY_LIMIT", "user_daily_limit", DEFAULT_USER_DAILY_LIMIT, 1_000),
    ("USER_MAX_CONCURRENT", "user_max_concurrent", DEFAULT_USER_MAX_CONCURRENT, 20),
    ("GLOBAL_DAILY_LIMIT", "global_daily_limit", DEFAULT_GLOBAL_DAILY_LIMIT, 100_000),
    ("MAX_FILE_SIZE_MB", "max_file_size_mb", DEFAULT_MAX_FILE_SIZE_MB, 200),
    ("MAX_PAGES", "max_pages", DEFAULT_MAX_PAGES, 5_000),
    ("MAX_LLM_CALLS", "max_llm_calls", DEFAULT_MAX_LLM_CALLS, 100),
)


class SettingsError(RuntimeError):
    """The configuration is unusable. Messages name variables, never their values."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(
            "Invalid configuration:\n" + "\n".join(f"- {problem}" for problem in problems)
        )


def parse_cors_origins(raw: str) -> list[str]:
    """Split a comma-separated list of origins.

    Entries are trimmed, empty ones dropped, and a trailing slash removed because
    browsers never send one in the Origin header, so it would never match.
    """
    origins = (origin.strip().rstrip("/") for origin in raw.split(","))
    return [origin for origin in origins if origin]


def parse_positive_int(name: str, default: int) -> int | None:
    """Integer from the environment, or None when it is set but is not an integer.

    None is not replaced by the default: validate_settings reports it at startup, so a
    typo is an error rather than a silently different limit.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return None


def parse_bool(name: str, default: bool) -> bool | None:
    """Boolean from the environment, or None when the value is not recognised."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return None


def resolve_log_level(name: str) -> int:
    """Numeric level for a LOG_LEVEL name; unknown names fall back to INFO."""
    return logging.getLevelNamesMapping().get(name.upper(), logging.INFO)


class settings:
    greenpt_api_url = os.getenv("GREENPT_API_URL", "https://api.greenpt.ai/v1")
    api_key = os.getenv("GREENPT_API_KEY", "").strip()
    sso_salt_documents = os.getenv("SSO_SALT_DOCUMENTS", "").strip()
    mongo_uri = os.getenv("MONGO_URI", "").strip()
    mongo_password = os.getenv("MONGO_APP_PASSWORD", "").strip()
    mongo_username = os.getenv("MONGO_APP_USERNAME", "").strip()
    mongo_db_name = os.getenv("MONGO_DB_NAME", "").strip()
    cors_origins = parse_cors_origins(os.getenv("CORS_ORIGINS", ""))
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    analyze_enabled = parse_bool("ANALYZE_ENABLED", True)
    user_daily_limit = parse_positive_int("USER_DAILY_LIMIT", DEFAULT_USER_DAILY_LIMIT)
    user_max_concurrent = parse_positive_int(
        "USER_MAX_CONCURRENT", DEFAULT_USER_MAX_CONCURRENT
    )
    global_daily_limit = parse_positive_int(
        "GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT
    )
    max_file_size_mb = parse_positive_int("MAX_FILE_SIZE_MB", DEFAULT_MAX_FILE_SIZE_MB)
    max_pages = parse_positive_int("MAX_PAGES", DEFAULT_MAX_PAGES)
    max_llm_calls = parse_positive_int("MAX_LLM_CALLS", DEFAULT_MAX_LLM_CALLS)


@dataclass(frozen=True)
class UsageLimits:
    """The cost and abuse limits, read once from a configuration object.

    Missing attributes fall back to the defaults, so a minimal configuration (as the
    tests build) is still complete.
    """

    analyze_enabled: bool = True
    user_daily_limit: int = DEFAULT_USER_DAILY_LIMIT
    user_max_concurrent: int = DEFAULT_USER_MAX_CONCURRENT
    global_daily_limit: int = DEFAULT_GLOBAL_DAILY_LIMIT
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB
    max_pages: int = DEFAULT_MAX_PAGES
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @classmethod
    def from_config(cls, config=settings) -> "UsageLimits":
        defaults = cls()
        return cls(
            **{
                name: getattr(config, name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


def validate_settings(config=settings) -> list[str]:
    """Return every configuration problem, so they can be fixed in one go.

    Messages only name the variables. They never include a value, because the
    result ends up in the startup log.
    """
    problems = []

    for variable, attribute in (
        ("MONGO_URI", "mongo_uri"),
        ("MONGO_DB_NAME", "mongo_db_name"),
        ("GREENPT_API_KEY", "api_key"),
    ):
        if not getattr(config, attribute, ""):
            problems.append(f"{variable} is required")

    sso_secret = getattr(config, "sso_salt_documents", "")
    if not sso_secret:
        problems.append("SSO_SALT_DOCUMENTS is required")
    elif len(sso_secret.encode("utf-8")) < MIN_SSO_SECRET_BYTES:
        problems.append(
            f"SSO_SALT_DOCUMENTS must be at least {MIN_SSO_SECRET_BYTES} bytes"
        )

    if "*" in getattr(config, "cors_origins", []):
        problems.append(
            "CORS_ORIGINS must not contain '*': list the allowed origins explicitly"
        )

    if getattr(config, "log_level", "INFO") not in LOG_LEVELS:
        problems.append(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")

    if not isinstance(getattr(config, "analyze_enabled", True), bool):
        problems.append("ANALYZE_ENABLED must be true or false")

    for variable, attribute, default, maximum in INTEGER_SETTINGS:
        value = getattr(config, attribute, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            problems.append(f"{variable} must be an integer between 1 and {maximum}")

    return problems
