# syntax=docker/dockerfile:1

# Build stage: install the dependencies into a virtualenv. Nothing from this stage
# except /opt/venv reaches the final image.
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt


# Runtime stage: the interpreter, the virtualenv and the application, run as an
# unprivileged user. No compiler and no package manager cache.
FROM python:3.13-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

USER app

EXPOSE 8000

# `python:slim` has no curl, so the probe uses the standard library. /ready also
# pings MongoDB, so the container turns unhealthy when the database is unreachable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]

# One worker. --proxy-headers makes the client address come from X-Forwarded-For
# behind Traefik, but only for peers listed in FORWARDED_ALLOW_IPS, which uvicorn
# reads from the environment (default 127.0.0.1,::1).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
