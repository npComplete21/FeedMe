# ADR 0030: Fetch Instagram captions through Meta's oEmbed API, with paste as the fallback

Status: Accepted - **not yet verified against the live API** (see Consequences)

## Context

Instagram ingestion was paste-only ([ADR-0006](0006-raw-source-staging-table.md)): the user copied
a Reel's caption into a text box. YouTube is fetched automatically. The backlog asked whether
Instagram could be automated cleanly, and if not, whether to drop it as a source.

Options researched (2026-10-04):

1. **yt-dlp's Instagram extractor.** Unauthenticated requests are routinely refused ("Requested
   content is not available, rate-limit reached or login required"), including reports from June
   2026. It works reliably only with a logged-in account's cookies - which puts that account at
   risk of being flagged - and, like YouTube ([ADR-0024](0024-youtube-anti-bot-check.md)), the
   cluster's datacenter IP makes refusals more likely.
2. **Link-preview scraping** (requesting the page as Facebook's crawler to read `og:description`).
   No login, but it impersonates Meta's own user agent - fragile and against the spirit of the
   platform's terms.
3. **Audio transcription** (download the Reel, run Whisper). The download hits the same login
   wall as (1), and transcription is heavy for a 2-OCPU node.
4. **Meta's official oEmbed endpoint**, `graph.facebook.com/v25.0/instagram_oembed`. Returns the
   embed HTML for a public post, which includes the caption. It needed App Review until Meta
   reverted that on 2026-06-15: it can now be called without a token (at lower rate limits), and
   the app-token route still works. There is no other official way to read a caption from an
   account you don't own - the Graph API's Business Discovery can't fetch arbitrary media.

## Decision

**Option 4, falling back to paste.** `app/ingestion/instagram.py` calls oEmbed (with
`INSTAGRAM_OEMBED_TOKEN` if set, tokenless otherwise), extracts the caption from the embed HTML's
paragraphs while dropping Instagram's own "View this post" / "A post shared by" chrome, and feeds
it into the same parse → persist pipeline as everything else. `POST /recipes/ingest` with
`source_platform: "instagram"` and no `caption_text` now enqueues `ingest_instagram_task` instead of
returning 422.

Errors are split by whether a retry could help: a 4xx from Meta (private, deleted, not a post,
rate-limited), an unexpected body, or a post with no caption raise `InstagramFetchError`, which the
worker does **not** retry - failing fast gets the user to the paste box sooner. Network errors and
5xx are ordinary `httpx` errors and are retried as before.

The UI treats both platforms the same: the paste box is an optional "Paste the caption instead"
expander, opened automatically - with the error and the URL kept - after a failed fetch of that
URL. Instagram stays a source; pasting remains for whatever oEmbed can't reach.

## Consequences

- Gain: pasting a Reel URL is now usually enough, using only an official, documented endpoint -
  no account at risk, no scraping.
- Gain: one fallback flow for both platforms in the UI.
- **Unverified:** the development sandbox couldn't reach Meta, so the caption extraction is tested
  against the embed shape as documented and observed in public examples, not a live response. The
  first real Instagram ingest after deploy is the test; if it fails, users get the paste box, not
  an error page. `tests/ingestion/test_instagram.py::test_fetch_real_public_post` is a
  `@pytest.mark.integration` test to run from a machine with access
  (`INSTAGRAM_TEST_URL=... pytest -m integration -k instagram`).
- Cost: the tokenless rate limit is unpublished. If it bites, create a Meta app and set
  `INSTAGRAM_OEMBED_TOKEN` (`{app_id}|{app_secret}`) in `feedme-secrets` - the worker reads it as an
  optional key, so it can be added without touching the manifests.
- Cost: dependent on Meta keeping the endpoint open; it was gated behind App Review for most of
  2021-2026. If that returns, the paste fallback still works and the app token is the next step.
