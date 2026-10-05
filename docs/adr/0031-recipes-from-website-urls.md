# ADR 0031: Recipes from website URLs - schema.org data first, with SSRF guards

Status: Accepted

## Context

Recipes also live on ordinary websites - food blogs and recipe sites such as
`littlespicejar.com/gochujang-chicken/` - not just Instagram and YouTube. Two problems make "just
fetch the page and send it to Claude" a poor design:

1. **Recipe pages are mostly not recipe.** A typical food blog puts thousands of words of story,
   ads and comments before the recipe card. Sending all of it to the parser
   ([ADR-0007](0007-llm-structured-extraction.md)) is slow, costly, and gives the model more
   chances to pick up the wrong numbers.
2. **The worker would fetch arbitrary user-supplied URLs from inside the cluster.** Without
   guards, `http://db:5432`, `http://redis:6379`, a pod IP, or a public URL that redirects to one
   of those would make the worker probe internal services (server-side request forgery). The
   network policy only blocks the cloud metadata address
   ([ADR-0021](0021-block-pod-egress-to-cloud-metadata.md)).

## Decision

**A new `website` source** (`app/ingestion/website.py`), queued like the others
(`ingest_website_task`), with the same "paste it instead" fallback in the UI.

**Read schema.org `Recipe` JSON-LD first.** Nearly every recipe site publishes it (it's what search
engines use for recipe cards; WordPress plugins like WP Recipe Maker and Tasty Recipes emit it
automatically). The reader finds the `Recipe` node - top-level, in a list, or inside a Yoast-style
`@graph` - and renders name, description, cuisine/category, ISO-8601 times as minutes, servings,
ingredients and steps (including `HowToSection` groups) as short labelled text for the parser. The
page's story never reaches the model. Pages without that data fall back to their visible text,
minus scripts, nav, header, footer and asides, capped at 20,000 characters; a page with almost no
text is rejected as "no recipe".

The LLM parser still runs on the structured text, rather than mapping JSON-LD fields directly, so
cuisine and meal type land in the closed vocabulary ([ADR-0009](0009-tags-closed-vocabulary.md))
and ingredients are split into name and quantity exactly as for every other source.

**Fetch defensively:**
- only `http`/`https`, only ports 80/443;
- the hostname must resolve **only** to public addresses (`ipaddress.is_global`) - loopback,
  private, link-local, cluster and unique-local IPv6 ranges are refused before connecting;
- redirects are followed by hand (at most 5), re-checking every hop;
- `text/html` only, at most 5 MB, 15 s timeout, an honest `FeedMe/1.0` user agent.

As with Instagram ([ADR-0030](0030-instagram-captions-via-oembed.md)), anything that a retry
can't fix - a refused URL, a 4xx, a non-HTML response, no recipe - is a `WebsiteFetchError` that
the worker doesn't retry, so the user reaches the paste box quickly; network errors and 5xx retry.

## Consequences

- Gain: any recipe site works, usually with exact ingredient lists, and the parser sees a
  page's recipe, not its story.
- Gain: user-supplied URLs can't be used to reach anything a stranger on the internet couldn't.
- Cost: DNS is resolved once for the check and again by the HTTP client, so a hostile DNS server
  could in principle answer differently the second time ("DNS rebinding"). Accepted for a
  registration-gated app; closing it fully means pinning the connection to the checked address.
- Cost: some sites block non-browser user agents or sit behind bot challenges (Cloudflare); those
  fail with a clear message and the paste box. The user agent is deliberately honest rather than
  impersonating a browser.
- **Unverified against the example site:** the development sandbox couldn't reach
  littlespicejar.com, so the reader is tested against a synthetic page in the shape recipe
  plugins emit. `test_fetch_real_recipe_site` (`@pytest.mark.integration`) checks the real page
  from a machine with access.
