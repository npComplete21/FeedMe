from unittest.mock import MagicMock

import pytest
import yt_dlp

from app.ingestion.youtube import (
    NoCaptionsAvailableError,
    YouTubeFetchError,
    extract_info,
    fetch_youtube_transcript,
    select_caption_url,
    vtt_to_text,
)

# --- vtt_to_text -------------------------------------------------------------


def test_vtt_to_text_strips_header_and_timestamps():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.560 --> 00:00:03.070
hey guys welcome back to my channel

00:00:03.070 --> 00:00:05.000
today we're making fried rice
"""
    assert vtt_to_text(vtt) == "hey guys welcome back to my channel today we're making fried rice"


def test_vtt_to_text_dedupes_consecutive_identical_cues():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
first step

00:00:01.000 --> 00:00:02.000
first step

00:00:02.000 --> 00:00:03.000
second step
"""
    assert vtt_to_text(vtt) == "first step second step"


def test_vtt_to_text_strips_inline_word_timing_tags():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
chop the<00:00:00.500><c> onions</c><00:00:01.000><c> finely</c>
"""
    assert vtt_to_text(vtt) == "chop the onions finely"


# --- select_caption_url -------------------------------------------------------


def test_select_caption_url_prefers_manual_subtitles_over_automatic():
    info = {
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/manual.vtt"}]},
        "automatic_captions": {"en": [{"ext": "vtt", "url": "https://example.com/auto.vtt"}]},
    }
    assert select_caption_url(info) == "https://example.com/manual.vtt"


def test_select_caption_url_falls_back_to_automatic_captions():
    info = {
        "subtitles": {},
        "automatic_captions": {"en": [{"ext": "vtt", "url": "https://example.com/auto.vtt"}]},
    }
    assert select_caption_url(info) == "https://example.com/auto.vtt"


def test_select_caption_url_prefers_vtt_format_among_options():
    info = {
        "subtitles": {
            "en": [
                {"ext": "json3", "url": "https://example.com/subs.json3"},
                {"ext": "vtt", "url": "https://example.com/subs.vtt"},
            ]
        },
        "automatic_captions": {},
    }
    assert select_caption_url(info) == "https://example.com/subs.vtt"


def test_select_caption_url_raises_when_no_captions_present():
    with pytest.raises(NoCaptionsAvailableError):
        select_caption_url({"subtitles": {}, "automatic_captions": {}})


# --- extract_info --------------------------------------------------------------


def test_extract_info_wraps_download_error(monkeypatch):
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.side_effect = yt_dlp.utils.DownloadError(
        "video unavailable"
    )
    monkeypatch.setattr(
        "app.ingestion.youtube.yt_dlp.YoutubeDL", lambda opts: mock_ydl
    )

    with pytest.raises(YouTubeFetchError):
        extract_info("https://youtube.com/watch?v=bad")


# --- fetch_youtube_transcript (orchestration) -----------------------------------


def test_fetch_youtube_transcript_orchestrates_the_pipeline(monkeypatch):
    fake_info = {
        "title": "Weeknight Fried Rice",
        "uploader": "Some Cooking Channel",
        "thumbnail": "https://example.com/thumb.jpg",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/captions.vtt"}]},
        "automatic_captions": {},
    }
    fake_vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nchop the onions\n"

    monkeypatch.setattr("app.ingestion.youtube.extract_info", lambda url: fake_info)

    fake_response = MagicMock()
    fake_response.text = fake_vtt
    fake_response.raise_for_status = MagicMock()
    monkeypatch.setattr(
        "app.ingestion.youtube.httpx.get", lambda url, timeout: fake_response
    )

    result = fetch_youtube_transcript("https://youtube.com/watch?v=abc")

    assert result.source_url == "https://youtube.com/watch?v=abc"
    assert result.title == "Weeknight Fried Rice"
    assert result.channel == "Some Cooking Channel"
    assert result.thumbnail_url == "https://example.com/thumb.jpg"
    assert result.transcript_text == "chop the onions"


# --- integration (real network call, run manually via `pytest -m integration`) --


@pytest.mark.integration
def test_fetch_real_youtube_video():
    # "Me at the zoo" - the first video ever uploaded to YouTube. Stable and
    # unlikely to be removed, used only to sanity-check the pipeline against
    # a real video with real auto-generated captions.
    result = fetch_youtube_transcript("https://www.youtube.com/watch?v=jNQXAC9IVRw")

    assert result.title
    assert result.transcript_text
