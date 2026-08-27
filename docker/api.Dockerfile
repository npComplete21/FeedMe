FROM python:3.13-slim

# Explicit uid rather than letting useradd pick one, so the Phase 3 Kubernetes
# manifests can pin the same number in `runAsUser`. --create-home because
# several libraries expect a writable HOME and fail at runtime, not build time,
# without one.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# Installed as root on purpose: this writes to /usr/local/.../site-packages,
# which the unprivileged app user has no business owning.
RUN pip install --no-cache-dir ".[api]"

# /app has to be writable by appuser so CPython can write __pycache__ alongside
# the source. Left root-owned, that write fails silently - no error, just a cold
# bytecode cache on every single start.
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Apply any pending migrations before serving. Safe for a single-instance
# stack because every migration in this project is additive/backward-
# compatible by convention - see ADR-0012 for the reasoning and its limits
# once there's more than one API replica.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
