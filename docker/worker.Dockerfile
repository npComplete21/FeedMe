FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir ".[api]"

# No migrations here - only the api container's entrypoint runs
# `alembic upgrade head` (ADR-0012), so there's a single owner of schema
# changes regardless of how many worker replicas are running.
CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info"]
