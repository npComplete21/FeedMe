import json
import socket

import httpx
import pytest

from app.ingestion import website
from app.ingestion.website import (
    WebsiteFetchError,
    fetch_page,
    fetch_website_recipe,
    iso_duration_minutes,
    read_recipe_page,
)

URL = "https://blog.example/gochujang-chicken/"

# A synthetic page shaped like what WordPress recipe plugins (WP Recipe Maker,
# Tasty Recipes) emit: a long story, then a Yoast-style @graph whose Recipe node
# has HowToSection-grouped steps and ISO-8601 durations.
_RECIPE_NODE = {
    "@type": "Recipe",
    "name": "Sticky Gochujang Chicken",
    "description": "Sweet, spicy &amp; <em>sticky</em> chicken.",
    "image": ["https://blog.example/img/chicken.jpg"],
    "recipeYield": ["4", "4 servings"],
    "prepTime": "PT10M",
    "cookTime": "PT20M",
    "totalTime": "PT30M",
    "recipeCuisine": ["Korean"],
    "recipeCategory": ["Main Course"],
    "recipeIngredient": [
        "1 1/2 pounds boneless chicken thighs",
        "3 tablespoons gochujang",
        "2 cloves garlic, minced",
    ],
    "recipeInstructions": [
        {
            "@type": "HowToSection",
            "name": "Sauce",
            "itemListElement": [
                {"@type": "HowToStep", "text": "Whisk the gochujang and garlic."}
            ],
        },
        {
            "@type": "HowToSection",
            "name": "Chicken",
            "itemListElement": [
                {"@type": "HowToStep", "text": "Sear the chicken &amp; toss in sauce."},
                {"@type": "HowToStep", "text": "Serve over rice."},
            ],
        },
    ],
}
_GRAPH = {
    "@context": "https://schema.org",
    "@graph": [{"@type": "WebPage", "name": "page"}, {"@type": ["Article"]}, _RECIPE_NODE],
}


def _page(json_ld: str | None = None, body: str = "") -> str:
    script = f'<script type="application/ld+json">{json_ld}</script>' if json_ld else ""
    return (
        f"<html><head><title>Gochujang Chicken | A Blog</title>{script}</head>"
        f"<body><nav>Home Recipes About</nav>{body}<footer>Copyright</footer></body></html>"
    )


@pytest.fixture
def public_dns(monkeypatch):
    """Every hostname resolves to a public address unless a test says otherwise."""
    answers = {}

    def fake_getaddrinfo(host, port, *args, **kwargs):
        ip = answers.get(host, "93.184.215.14")
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(website.socket, "getaddrinfo", fake_getaddrinfo)
    return answers


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _html_response(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"content-type": "text/html; charset=utf-8"})


# --- reading the page --------------------------------------------------------------


def test_reads_schema_org_recipe_from_a_graph():
    title, text, image = read_recipe_page(_page(json.dumps(_GRAPH), body="<p>My life story...</p>"))

    assert title == "Sticky Gochujang Chicken"
    assert image == "https://blog.example/img/chicken.jpg"
    assert text.splitlines() == [
        "Recipe: Sticky Gochujang Chicken",
        "Description: Sweet, spicy & sticky chicken.",
        "Cuisine: Korean",
        "Category: Main Course",
        "Prep time: 10 minutes",
        "Cook time: 20 minutes",
        "Total time: 30 minutes",
        "Servings: 4",
        "Ingredients:",
        "- 1 1/2 pounds boneless chicken thighs",
        "- 3 tablespoons gochujang",
        "- 2 cloves garlic, minced",
        "Instructions:",
        "[Sauce]",
        "1. Whisk the gochujang and garlic.",
        "[Chicken]",
        "2. Sear the chicken & toss in sauce.",
        "3. Serve over rice.",
    ]
    # The story isn't sent to the parser when structured data exists.
    assert "life story" not in text


def test_reads_top_level_recipe_with_plain_string_instructions():
    recipe = {"@context": "https://schema.org", "@type": "Recipe", "name": "Toast",
              "recipeIngredient": ["bread"], "recipeInstructions": "Toast the bread.\nButter it."}

    _, text, _ = read_recipe_page(_page(json.dumps(recipe)))

    assert text.endswith("Instructions:\n1. Toast the bread.\n2. Butter it.")


def test_skips_malformed_json_ld_and_uses_the_next_block():
    page = _page("{not json").replace(
        "</head>", f'<script type="application/ld+json">{json.dumps([_RECIPE_NODE])}</script></head>'
    )

    title, _, _ = read_recipe_page(page)

    assert title == "Sticky Gochujang Chicken"


def test_falls_back_to_visible_text_without_page_chrome():
    body = "<article><h1>Chicken</h1><p>" + "Mix the chicken with the sauce. " * 10 + "</p></article>"

    title, text, image = read_recipe_page(_page(body=body))

    assert title == "Gochujang Chicken | A Blog"
    assert text.startswith("Chicken\nMix the chicken")
    assert "Home Recipes" not in text and "Copyright" not in text
    assert image is None


def test_page_with_no_recipe_is_rejected():
    with pytest.raises(WebsiteFetchError, match="Couldn't find a recipe"):
        read_recipe_page(_page(body="<p>Subscribe!</p>"))


@pytest.mark.parametrize(
    "value,minutes",
    [("PT20M", 20), ("PT1H30M", 90), ("P0DT2H", 120), ("PT0M", None), ("20 min", None), (None, None)],
)
def test_iso_duration_minutes(value, minutes):
    assert iso_duration_minutes(value) == minutes


# --- fetching safely ---------------------------------------------------------------


def test_fetch_website_recipe_end_to_end(public_dns):
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return _html_response(_page(json.dumps(_GRAPH)))

    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": website.USER_AGENT})
    source = fetch_website_recipe(URL, client=client)

    assert source.source_url == URL
    assert source.title == "Sticky Gochujang Chicken"
    assert "- 3 tablespoons gochujang" in source.text
    assert "FeedMe" in seen["ua"]


@pytest.mark.parametrize(
    "url",
    ["ftp://blog.example/x", "file:///etc/passwd", "https://blog.example:8443/x", "not a url"],
)
def test_rejects_non_web_urls(public_dns, url):
    with pytest.raises(WebsiteFetchError):
        fetch_page(url, client=_client(lambda r: _html_response("x")))


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.43.0.10", "192.168.1.5", "169.254.169.254", "::1", "fd00::1"]
)
def test_rejects_hosts_resolving_to_private_addresses(public_dns, ip):
    public_dns["db"] = ip
    requests = []

    with pytest.raises(WebsiteFetchError, match="public website"):
        fetch_page("http://db/", client=_client(lambda r: requests.append(r)))
    assert requests == []  # refused before any connection


def test_rechecks_every_redirect_hop(public_dns):
    public_dns["internal"] = "10.42.0.7"

    def handler(request):
        return httpx.Response(302, headers={"location": "http://internal/admin"})

    with pytest.raises(WebsiteFetchError, match="public website"):
        fetch_page(URL, client=_client(handler))


def test_follows_public_redirects(public_dns):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return _html_response("<p>ok</p>")

    final_url, page = fetch_page("https://blog.example/old", client=_client(handler))

    assert final_url == "https://blog.example/new"
    assert page == "<p>ok</p>"


def test_4xx_is_terminal_and_5xx_is_retryable(public_dns):
    with pytest.raises(WebsiteFetchError, match="403"):
        fetch_page(URL, client=_client(lambda r: _html_response("no", 403)))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_page(URL, client=_client(lambda r: _html_response("down", 503)))


def test_rejects_non_html_and_oversized_pages(public_dns, monkeypatch):
    pdf = lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    with pytest.raises(WebsiteFetchError, match="isn't a web page"):
        fetch_page(URL, client=_client(pdf))

    monkeypatch.setattr(website, "MAX_BYTES", 10)
    with pytest.raises(WebsiteFetchError, match="too large"):
        fetch_page(URL, client=_client(lambda r: _html_response("x" * 100)))


def test_redirect_loops_are_cut_off(public_dns):
    with pytest.raises(WebsiteFetchError, match="redirects"):
        fetch_page(URL, client=_client(lambda r: httpx.Response(302, headers={"location": URL})))


def test_website_fetch_error_is_not_retried_by_the_worker():
    from app.worker import _RETRYABLE_ERRORS

    assert not issubclass(WebsiteFetchError, _RETRYABLE_ERRORS)


@pytest.mark.integration
def test_fetch_real_recipe_site():
    # Needs outbound access to the site: pytest -m integration -k real_recipe_site
    source = fetch_website_recipe("https://www.littlespicejar.com/gochujang-chicken/")
    assert "Ingredients:" in source.text and "gochujang" in source.text.lower()
