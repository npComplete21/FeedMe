from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass

import httpx
import yt_dlp
from sqlalchemy.orm import Session

from app.models import RawSource

_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_TAG = re.compile(r"<[^>]+>")


class YouTubeFetchError(Exception):
    """Raised when yt-dlp can't extract video info (private, deleted, invalid URL, ...)."""


class YouTubeBlockedError(Exception):
    """Raised when YouTube refuses the request with its anti-bot check.

    Deliberately NOT a subclass of YouTubeFetchError: the worker treats
    YouTubeFetchError as retryable, and retrying this is pointless. YouTube gates
    specific videos behind this check when the request comes from a datacenter
    IP, and it is not probabilistic - the same video was refused 6/6 times from
    the cluster while succeeding first try from a residential connection.
    """


# yt-dlp surfaces the anti-bot refusal as an ordinary DownloadError whose message
# contains this phrase, so matching on it is the only way to tell it apart from a
# private or deleted video.
_BOT_CHECK_MARKER = "Sign in to confirm"

# Cookies let yt-dlp authenticate and sidestep the check. Optional: without them
# most videos still work, and the failure is a clean YouTubeBlockedError rather
# than a crash. Mounted from the feedme-secrets Secret in the cluster.
_COOKIES_PATH = os.environ.get("YTDLP_COOKIES_FILE", "/etc/yt-dlp/cookies.txt")


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
    opts: dict = {"quiet": True, "skip_download": True, "noplaylist": True}
    scratch_cookies: str | None = None

    # Only pass cookiefile when the file actually exists - yt-dlp errors out on a
    # missing one, which would turn "no cookies configured" into a hard failure
    # for the many videos that need no authentication at all.
    if _COOKIES_PATH and os.path.isfile(_COOKIES_PATH):
        # yt-dlp rewrites the cookie jar when the YoutubeDL context closes, and
        # the file is mounted from a Kubernetes Secret, which is always read-only.
        # Pointing it straight at the mount raises OSError: [Errno 30] Read-only
        # file system on every call - i.e. supplying cookies would make things
        # strictly worse than having none. Work from a disposable copy instead;
        # discarding yt-dlp's updates is fine, since the Secret is the source of
        # truth and refreshing it is a deliberate act.
        fd, scratch_cookies = tempfile.mkstemp(prefix="ytdlp-cookies-", suffix=".txt")
        os.close(fd)  # mkstemp creates it 0600, which is what we want for cookies
        shutil.copyfile(_COOKIES_PATH, scratch_cookies)
        opts["cookiefile"] = scratch_cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        if _BOT_CHECK_MARKER in str(exc):
            raise YouTubeBlockedError(
                "YouTube blocked this request with its anti-bot check. This affects some "
                "videos when the request comes from a server rather than a home connection. "
                "Paste the video's transcript in manually, or refresh the server's YouTube "
                "cookies if this is happening often."
            ) from exc
        raise YouTubeFetchError(f"Could not fetch video info for {url}: {exc}") from exc
    finally:
        if scratch_cookies:
            # Best effort: a leftover temp file is untidy, not a failure worth
            # masking the real result over.
            try:
                os.unlink(scratch_cookies)
            except OSError:
                pass


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


def save_youtube_source(session: Session, user_id: int, source: YouTubeSource) -> RawSource:
    raw_source = RawSource(
        user_id=user_id,
        source_url=source.source_url,
        source_platform="youtube",
        raw_text=source.transcript_text,
        title=source.title,
        thumbnail_url=source.thumbnail_url,
    )
    session.add(raw_source)
    session.flush()
    return raw_source
