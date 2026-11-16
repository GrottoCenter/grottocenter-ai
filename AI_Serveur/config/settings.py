import logging
import os

# PyJWT warns on HMAC keys shorter than the hash output (RFC 7518, section 3.2).
MIN_SSO_SECRET_BYTES = 32
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


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

    return problems
