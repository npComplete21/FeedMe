"""Fetch a recipe from an ordinary web page - a food blog or recipe site.

Nearly every recipe site publishes a schema.org Recipe as JSON-LD (it's what
search engines read for recipe cards), so that is read first and turned into a
compact text the parser (ADR-0007) handles like a caption. Pages without one
fall back to their visible text. See ADR-0031.

The URL comes from a user and is fetched from inside the cluster, so every hop -
including redirects - must resolve only to public addresses; otherwise this
would be a way to make the worker call the database, Redis or other pods.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy.orm import Session

from app.models import RawSource

USER_AGENT = "Mozilla/5.0 (compatible; FeedMe/1.0; +https://feedmepls.xyz)"
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
# Keeps a recipe-less page from becoming a huge parse request.
MAX_FALLBACK_CHARS = 20_000
MIN_FALLBACK_CHARS = 200

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t\r\f\v]+")
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:\d+S)?)?$", re.IGNORECASE)


class WebsiteFetchError(Exception):
    """The page can't be used: not a public http(s) URL, refused (4xx), not
    HTML, too large, or no recipe on it. Not retried by the worker - none of
    these change on a retry - so the user reaches the paste box quickly.
    Network errors and 5xx stay httpx errors and are retried."""


@dataclass
class WebsiteSource:
    source_url: str
    title: str | None
    text: str
    image_url: str | None


# --- safety -------------------------------------------------------------------


def _check_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebsiteFetchError("Only http:// and https:// web page links are supported")
    if parts.port not in (None, 80, 443):
        raise WebsiteFetchError("Only standard web ports (80/443) are supported")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise WebsiteFetchError(f"Couldn't find the website {parts.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise WebsiteFetchError("That address isn't a public website")


def fetch_page(url: str, *, client: httpx.Client | None = None) -> tuple[str, str]:
    """Returns (final_url, html). Follows redirects itself so each hop is checked."""
    http = client or httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            _check_public_url(url)
            with http.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                if 400 <= response.status_code < 500:
                    raise WebsiteFetchError(
                        f"The website refused the request (HTTP {response.status_code})"
                    )
                response.raise_for_status()  # 5xx: retryable
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    raise WebsiteFetchError("That link isn't a web page")
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise WebsiteFetchError("That page is too large to read")
                return url, body.decode(response.encoding or "utf-8", errors="replace")
        raise WebsiteFetchError("Too many redirects")
    finally:
        if client is None:
            http.close()


# --- reading the page -----------------------------------------------------------


class _PageReader(HTMLParser):
    """Collects JSON-LD blocks, the <title>, and visible text outside page chrome."""

    _SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"}
    _BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}

    def __init__(self) -> None:
        super().__init__()
        self.json_ld: list[str] = []
        self.title = ""
        self.text: list[str] = []
        self._skip_depth = 0
        self._in_json_ld = False
        self._in_title = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._buffer = []
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_json_ld:
            self._buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.text.append(data)


def _types(node: dict) -> list[str]:
    value = node.get("@type", [])
    return [value] if isinstance(value, str) else [t for t in value if isinstance(t, str)]


def _find_recipe(data) -> dict | None:
    if isinstance(data, list):
        for item in data:
            if found := _find_recipe(item):
                return found
    elif isinstance(data, dict):
        if "Recipe" in _types(data):
            return data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data and (found := _find_recipe(data[key])):
                return found
    return None


def _clean(value) -> str:
    if not isinstance(value, str):
        return ""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def iso_duration_minutes(value) -> int | None:
    match = _DURATION.match(value.strip()) if isinstance(value, str) else None
    if not match or not any(match.groups()):
        return None
    days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    return days * 1440 + hours * 60 + minutes or None


def _instruction_lines(instructions) -> list[str]:
    lines: list[str] = []
    for item in _as_list(instructions):
        if isinstance(item, str):
            lines.extend(s for s in (_clean(p) for p in item.split("\n")) if s)
        elif isinstance(item, dict):
            if "HowToSection" in _types(item):
                if name := _clean(item.get("name")):
                    lines.append(f"[{name}]")
                lines.extend(_instruction_lines(item.get("itemListElement")))
            elif text := _clean(item.get("text") or item.get("name")):
                lines.append(text)
    return lines


def _image_url(image) -> str | None:
    for item in _as_list(image):
        if isinstance(item, str):
            return item
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            return item["url"]
    return None


def recipe_text_from_json_ld(recipe: dict) -> str:
    """Render a schema.org Recipe as plain labelled text for the parser."""
    out: list[str] = []
    if name := _clean(recipe.get("name")):
        out.append(f"Recipe: {name}")
    if description := _clean(recipe.get("description")):
        out.append(f"Description: {description}")
    for label, key in (("Cuisine", "recipeCuisine"), ("Category", "recipeCategory")):
        values = [_clean(v) for v in _as_list(recipe.get(key))]
        if values := [v for v in values if v]:
            out.append(f"{label}: {', '.join(values)}")
    for label, key in (("Prep time", "prepTime"), ("Cook time", "cookTime"), ("Total time", "totalTime")):
        if minutes := iso_duration_minutes(recipe.get(key)):
            out.append(f"{label}: {minutes} minutes")
    servings = [_clean(v) for v in _as_list(recipe.get("recipeYield")) if _clean(v)]
    if servings:
        out.append(f"Servings: {servings[0]}")

    ingredients = [_clean(i) for i in _as_list(recipe.get("recipeIngredient"))]
    out.append("Ingredients:")
    out.extend(f"- {i}" for i in ingredients if i)

    steps = _instruction_lines(recipe.get("recipeInstructions"))
    out.append("Instructions:")
    number = 0
    for step in steps:
        if step.startswith("[") and step.endswith("]"):
            out.append(step)
        else:
            number += 1
            out.append(f"{number}. {step}")
    return "\n".join(out)


def read_recipe_page(page_html: str) -> tuple[str | None, str, str | None]:
    """Returns (title, text for the parser, image url)."""
    reader = _PageReader()
    reader.feed(page_html)
    reader.close()

    for block in reader.json_ld:
        try:
            data = json.loads(block)
        except ValueError:
            continue  # sites ship malformed JSON-LD more often than you'd hope
        if recipe := _find_recipe(data):
            return (
                _clean(recipe.get("name")) or _clean(reader.title) or None,
                recipe_text_from_json_ld(recipe),
                _image_url(recipe.get("image")),
            )

    lines = (_SPACE.sub(" ", line).strip() for line in "".join(reader.text).split("\n"))
    text = "\n".join(line for line in lines if line)[:MAX_FALLBACK_CHARS]
    if len(text) < MIN_FALLBACK_CHARS:
        raise WebsiteFetchError("Couldn't find a recipe on that page")
    return _clean(reader.title) or None, text, None


def fetch_website_recipe(url: str, *, client: httpx.Client | None = None) -> WebsiteSource:
    _, page_html = fetch_page(url.strip(), client=client)
    title, text, image_url = read_recipe_page(page_html)
    # Keep the link the user gave rather than final_url: it's what they'll recognise.
    return WebsiteSource(source_url=url.strip(), title=title, text=text, image_url=image_url)


def save_website_source(session: Session, user_id: int, source: WebsiteSource) -> RawSource:
    raw_source = RawSource(
        user_id=user_id,
        source_url=source.source_url,
        source_platform="website",
        raw_text=source.text,
        title=source.title,
        thumbnail_url=source.image_url,
    )
    session.add(raw_source)
    session.flush()
    return raw_source
