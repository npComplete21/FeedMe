from sqlalchemy.orm import Session

from app.ingestion.manual import save_manual_caption
from app.ingestion.youtube import fetch_youtube_transcript, save_youtube_source
from app.models import Recipe
from app.parsing.recipe_parser import parse_recipe
from app.persistence.recipe_store import persist_recipe


def ingest_youtube(session: Session, user_id: int, url: str) -> Recipe:
    source = fetch_youtube_transcript(url)
    raw_source = save_youtube_source(session, user_id, source)
    parsed = parse_recipe(raw_source.raw_text)
    return persist_recipe(session, raw_source, parsed)


def ingest_manual_caption(
    session: Session,
    user_id: int,
    url: str,
    caption_text: str,
    source_platform: str = "instagram",
) -> Recipe:
    raw_source = save_manual_caption(
        session,
        user_id=user_id,
        source_url=url,
        caption_text=caption_text,
        source_platform=source_platform,
    )
    parsed = parse_recipe(raw_source.raw_text)
    return persist_recipe(session, raw_source, parsed)
