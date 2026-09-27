FROM python:3.13-slim

# YouTube requires solving a JavaScript "n" challenge to hand over caption URLs.
# yt-dlp needs BOTH a JS runtime (this) and the solver scripts (yt-dlp-ejs, a
# pip dependency) - either alone fails with "n challenge solving failed", and
# the request never gets that far without cookies either. All three are needed
# together; see ADR-0024.
#
# Copied from Deno's official binary-only image rather than downloaded, so the
# build has no network fetch logic to go stale and the version is pinned.
COPY --from=denoland/deno:bin-2.9.7 /deno /usr/local/bin/deno

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

# Deno writes a module cache on first run and fails if it cannot. appuser has a
# writable home (--create-home above), but be explicit rather than relying on
# HOME being set the way we expect inside Kubernetes.
ENV DENO_DIR=/home/appuser/.cache/deno

# No migrations here - only the api container's entrypoint runs
# `alembic upgrade head` (ADR-0012), so there's a single owner of schema
# changes regardless of how many worker replicas are running.
CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info"]
