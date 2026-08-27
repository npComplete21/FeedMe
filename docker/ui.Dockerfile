FROM python:3.13-slim

# See docker/api.Dockerfile for why the uid is pinned. Streamlit writes config
# and usage state under ~/.streamlit, so --create-home is what keeps it from
# failing on startup as a non-root user.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir ".[ui]"

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
