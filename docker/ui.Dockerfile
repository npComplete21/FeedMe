FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir ".[ui]"

EXPOSE 8501

CMD ["streamlit", "run", "app/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
