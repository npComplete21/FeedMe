import os

import httpx
import pytest

from app.ingestion.instagram import (
    OEMBED_URL,
    InstagramFetchError,
    caption_from_embed_html,
    fetch_instagram_caption,
)

REEL = "https://www.instagram.com/reel/C0abc123/"

# Shape of Meta's captioned embed: the caption paragraph, then Instagram's own
# "View this post" / "A post shared by" chrome, which must not reach the parser.
_EMBED = (
    '<blockquote class="instagram-media" data-instgrm-captioned '
    'data-instgrm-permalink="https://www.instagram.com/reel/C0abc123/" data-instgrm-version="14">'
    '<div style="padding:16px;"><a href="https://www.instagram.com/reel/C0abc123/">'
    "<div>View this post on Instagram</div></a>"
    '<p style="margin:8px 0 0 0;"><a href="https://www.instagram.com/reel/C0abc123/">'
    "Kimchi fried rice &amp; egg<br>2 cups rice<br>1 cup kimchi</a></p>"
    '<p style="color:#c9c8cd;"><a href="https://www.instagram.com/reel/C0abc123/">'
    "A post shared by Chef (@chef)</a></p></div></blockquote>"
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_caption_from_embed_html_keeps_caption_and_drops_instagram_chrome():
    assert caption_from_embed_html(_EMBED) == "Kimchi fried rice & egg\n2 cups rice\n1 cup kimchi"


def test_caption_from_embed_html_without_caption_is_empty():
    uncaptioned = _EMBED.replace(
        _EMBED[_EMBED.index('<p style="margin'):_EMBED.index('<p style="color')], ""
    )
    assert caption_from_embed_html(uncaptioned) == ""


def test_fetch_calls_oembed_and_returns_caption():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json={"html": _EMBED, "provider_name": "Instagram"})

    source = fetch_instagram_caption(REEL, client=_client(handler))

    assert source.source_url == REEL
    assert source.caption.startswith("Kimchi fried rice & egg")
    assert str(seen["url"]).startswith(OEMBED_URL)
    assert seen["url"].params["url"] == REEL
    assert seen["url"].params["omitscript"] == "true"


def test_fetch_turns_meta_4xx_into_terminal_error_with_its_message():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "The URL is not a valid post"}})

    with pytest.raises(InstagramFetchError, match="not a valid post"):
        fetch_instagram_caption(REEL, client=_client(handler))


def test_fetch_raises_terminal_error_when_post_has_no_caption():
    def handler(request):
        return httpx.Response(200, json={"html": "<blockquote><p>A post shared by x</p></blockquote>"})

    with pytest.raises(InstagramFetchError, match="no caption"):
        fetch_instagram_caption(REEL, client=_client(handler))


def test_fetch_raises_terminal_error_on_unexpected_body():
    def handler(request):
        return httpx.Response(200, content=b"<html>login</html>")

    with pytest.raises(InstagramFetchError, match="unexpected"):
        fetch_instagram_caption(REEL, client=_client(handler))


def test_fetch_lets_server_errors_propagate_as_retryable_http_errors():
    def handler(request):
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_instagram_caption(REEL, client=_client(handler))


def test_instagram_fetch_error_is_not_retried_by_the_worker():
    from app.worker import _RETRYABLE_ERRORS

    assert not issubclass(InstagramFetchError, _RETRYABLE_ERRORS)


@pytest.mark.integration
def test_fetch_real_public_post():
    # Needs network access to graph.facebook.com and a real public post to read:
    #   INSTAGRAM_TEST_URL=https://www.instagram.com/reel/... pytest -m integration -k instagram
    url = os.environ.get("INSTAGRAM_TEST_URL")
    if not url:
        pytest.skip("set INSTAGRAM_TEST_URL to a public Instagram post with a caption")
    source = fetch_instagram_caption(url)
    assert source.caption
