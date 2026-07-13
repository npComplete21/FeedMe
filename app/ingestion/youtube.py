from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import yt_dlp

_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_TAG = re.compile(r"<[^>]+>")


class YouTubeFetchError(Exception):
    """Raised when yt-dlp can't extract video info (private, deleted, invalid URL, ...)."""


class NoCaptionsAvailableError(Exception):
    """Raised when a video has no subtitles or automatic captions in the requested language."""


@dataclass
class YouTubeSource:
    source_url: str
    title: str
    channel: str | None
    thumbnail_url: str | None
    transcript_text: str


def extract_info(url: str) -> dict:
    opts = {"quiet": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeFetchError(f"Could not fetch video info for {url}: {exc}") from exc


def select_caption_url(info: dict, language: str = "en") -> str:
    """Prefer manually-created subtitles over auto-generated captions, and a .vtt
    track over other formats since it's the simplest to parse into plain text."""
    for track_key in ("subtitles", "automatic_captions"):
        entries = (info.get(track_key) or {}).get(language)
        if not entries:
            continue
        for entry in entries:
            if entry.get("ext") == "vtt":
                return entry["url"]
        return entries[0]["url"]

    raise NoCaptionsAvailableError(
        f"No '{language}' subtitles or automatic captions available for this video"
    )


def vtt_to_text(vtt_content: str) -> str:
    lines: list[str] = []
    for raw_line in vtt_content.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT":
            continue
        if line.startswith(("Kind:", "Language:", "NOTE", "STYLE")):
            continue
        if _TIMESTAMP_LINE.match(line):
            continue
        if line.isdigit():
            continue

        text = _TAG.sub("", line).strip()
        if not text:
            continue
        # YouTube auto-captions render as growing "rolling" cues, so consecutive
        # cues often repeat the previous line verbatim before adding new words.
        if lines and lines[-1] == text:
            continue
        lines.append(text)

    return " ".join(lines)


def fetch_youtube_transcript(url: str) -> YouTubeSource:
    info = extract_info(url)
    caption_url = select_caption_url(info)

    response = httpx.get(caption_url, timeout=10)
    response.raise_for_status()

    return YouTubeSource(
        source_url=url,
        title=info.get("title", ""),
        channel=info.get("uploader"),
        thumbnail_url=info.get("thumbnail"),
        transcript_text=vtt_to_text(response.text),
    )
