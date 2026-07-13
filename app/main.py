from fastapi import FastAPI

app = FastAPI(title="FeedMe")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
