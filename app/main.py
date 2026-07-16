from dotenv import load_dotenv

# Must run before any app.* import - those modules read env vars (DATABASE_URL,
# ANTHROPIC_API_KEY, RECIPE_PARSER_MODEL) at import time.
load_dotenv()

from fastapi import FastAPI  # noqa: E402

from app.api.routes import router  # noqa: E402

app = FastAPI(title="FeedMe")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
