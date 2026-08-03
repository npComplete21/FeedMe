FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN pip install --no-cache-dir ".[api]"

EXPOSE 8000

# Apply any pending migrations before serving. Safe for a single-instance
# stack because every migration in this project is additive/backward-
# compatible by convention - see ADR-0012 for the reasoning and its limits
# once there's more than one API replica.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
