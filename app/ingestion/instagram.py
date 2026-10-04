"""Fetch a public Instagram post's caption through Meta's official oEmbed API.

Chosen over yt-dlp (needs a logged-in account's cookies to work reliably, which
puts that account at risk) and over scraping - see ADR-0030. oEmbed returns the
post's embed HTML, whose paragraphs carry the caption. Any failure here is a
clean InstagramFetchError, and the UI then offers the paste box instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx
from sqlalchemy.orm import Session

from app.models import RawSource

OEMBED_URL = "https://graph.facebook.com/v25.0/instagram_oembed"

# Optional "{app_id}|{app_secret}" app token. Meta made the endpoint callable
# without one in June 2026, at lower rate limits; set this if those bite.
_ACCESS_TOKEN = os.environ.get("INSTAGRAM_OEMBED_TOKEN")

# Paragraphs of the embed HTML that are Instagram's own chrome, not the caption.
_BOILERPLATE_PREFIXES = ("A post shared by", "View this post on Instagram")


class InstagramFetchError(Exception):
    """The caption couldn't be fetched: a private or deleted post, a URL that
    isn't a post, a refused request, or an embed without a caption.

    Not retried by the worker (it isn't in app.worker's retryable list): none of
    these change on a retry, and failing fast gets the user to the paste box
    sooner. Plain network errors still surface as httpx errors and are retried.
    """


@dataclass
class InstagramSource:
    source_url: str
    caption: str


class _ParagraphText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._depth += 1
        elif tag == "br" and self._depth:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "p" and self._depth:
            self._depth -= 1
            if not self._depth:
                text = "".join(self._parts).strip()
                if text:
                    self.paragraphs.append(text)
                self._parts = []

    def handle_data(self, data):
        if self._depth:
            self._parts.append(data)


def caption_from_embed_html(embed_html: str) -> str:
    parser = _ParagraphText()
    parser.feed(embed_html)
    parser.close()
    return "\n\n".join(
        p for p in parser.paragraphs if not p.startswith(_BOILERPLATE_PREFIXES)
    )


def fetch_instagram_caption(url: str, *, client: httpx.Client | None = None) -> InstagramSource:
    params = {"url": url, "omitscript": "true"}
    if _ACCESS_TOKEN:
        params["access_token"] = _ACCESS_TOKEN

    http = client or httpx.Client(timeout=15)
    try:
        response = http.get(OEMBED_URL, params=params)
    finally:
        if client is None:
            http.close()

    # 4xx means Meta looked at this URL and said no - private, deleted, not a
    # post, or over the tokenless rate limit. 5xx propagates as retryable.
    if 400 <= response.status_code < 500:
        try:
            detail = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            detail = f"HTTP {response.status_code}"
        raise InstagramFetchError(f"Instagram wouldn't share this post's caption: {detail}")
    response.raise_for_status()

    try:
        embed_html = response.json()["html"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InstagramFetchError("Instagram returned an unexpected response") from exc

    caption = caption_from_embed_html(embed_html)
    if not caption:
        raise InstagramFetchError("This Instagram post has no caption to read a recipe from")
    return InstagramSource(source_url=url, caption=caption)


def save_instagram_source(session: Session, user_id: int, source: InstagramSource) -> RawSource:
    raw_source = RawSource(
        user_id=user_id,
        source_url=source.source_url,
        source_platform="instagram",
        raw_text=source.caption,
    )
    session.add(raw_source)
    session.flush()
    return raw_source
