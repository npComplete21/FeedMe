FROM python:3.13-slim

# See docker/api.Dockerfile for why the uid is pinned. The writable HOME is
# load-bearing here in particular: yt-dlp caches under ~/.cache while fetching
# transcripts.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir ".[api]"

RUN chown -R appuser:appuser /app

USER appuser

# No migrations here - only the api container's entrypoint runs
# `alembic upgrade head` (ADR-0012), so there's a single owner of schema
# changes regardless of how many worker replicas are running.
CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info"]
