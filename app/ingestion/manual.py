from sqlalchemy.orm import Session

from app.models import RawSource


class EmptyCaptionError(ValueError):
    """Raised when the pasted caption text is empty or whitespace-only."""


class EmptySourceUrlError(ValueError):
    """Raised when the source URL is empty or whitespace-only."""


def save_manual_caption(
    session: Session,
    *,
    user_id: int,
    source_url: str,
    caption_text: str,
    source_platform: str = "instagram",
) -> RawSource:
    url = source_url.strip()
    if not url:
        raise EmptySourceUrlError("Source URL cannot be empty")

    text = caption_text.strip()
    if not text:
        raise EmptyCaptionError("Caption text cannot be empty")

    raw_source = RawSource(
        user_id=user_id,
        source_url=url,
        source_platform=source_platform,
        raw_text=text,
    )
    session.add(raw_source)
    session.flush()
    return raw_source
