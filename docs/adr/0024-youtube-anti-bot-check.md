# ADR 0024: Handling YouTube's anti-bot check from a datacenter IP

Status: Accepted

## Context

A real ingestion from the live site failed with yt-dlp's raw output rendered into the UI - including
its suggestions about exporting cookies. Two separate problems: the error handling leaked internals,
and YouTube was refusing the request at all.

The refusal was investigated rather than assumed, and the assumption that would have been wrong was
tested first:

| Test | Result |
|---|---|
| Same video from a residential IP, **older** yt-dlp (2026.07.04) | works |
| Same video from the cluster, newer yt-dlp (2026.08.19) | blocked |
| Alternative player clients (`android`, `ios`, `tv`, `mweb`) | all blocked |
| Installing Deno, the JS runtime yt-dlp warns is now required | still blocked *(see correction below)* |
| `youtube-transcript-api` - a different request path entirely | also blocked |
| Same video retried 6 times from the cluster | 0/6 |
| A different video (`dQw4w9WgXcQ`) from the same cluster | works |

So it is the **IP**, not the yt-dlp version, not the video being unavailable, and not probabilistic.
YouTube gates *specific* videos behind an anti-bot check when the request originates from a
datacenter range, and Oracle Cloud is heavily flagged. The JS-runtime theory was the most plausible
explanation and it was wrong - worth recording, because it is the first thing anyone will try again.

## Correction: three gates, not one

The table above is what was observable at the time, and one row of it is misleading. Installing Deno
appeared to make no difference — but at that point every request was still being refused at the
anti-bot check, so the JS runtime was never actually exercised. **Each gate only becomes visible
once the previous one is passed:**

1. **Anti-bot check** — refused outright without cookies. Passing it revealed…
2. **The "n" challenge** — `n challenge solving failed: Ensure you have a supported JavaScript
   runtime *and challenge solver script distribution* installed`, then a fatal
   `The page needs to be reloaded.` A runtime alone is not enough…
3. **The solver scripts** — `yt-dlp-ejs`, a separate pip package.

With all three in place the originally-reported video resolves completely: title, channel, a
3000-character transcript, and an LLM parse producing 13 ingredients and 11 steps.

The general lesson is worth more than the specific fix: when a dependency reports several plausible
causes, ruling one out while another is still active proves nothing about it.

## Decision

**All three of cookies, a JS runtime and the solver scripts — plus an honest error when it still
fails.** `yt-dlp-ejs` is a dependency in `pyproject.toml`; Deno is copied into the worker image from
its official binary-only image, pinned by version, so the build contains no download logic to go
stale. `DENO_DIR` is set explicitly because Deno writes a module cache on first run and the
container runs as non-root.

`YouTubeBlockedError` is raised when yt-dlp's message contains `Sign in to confirm`, carrying a
short actionable message instead of yt-dlp's output. It is **deliberately not a subclass of
`YouTubeFetchError`**, because `app/worker.py` treats that as retryable and retrying this can never
succeed - the 0/6 result is the evidence. A test guards the inheritance so a future refactor can't
quietly reintroduce three wasted retries.

**Cookies are passed only when the file exists.** yt-dlp errors out on a missing `cookiefile`, so
unconditionally setting it would turn "no cookies configured" into a hard failure for the majority
of videos that need no authentication.

**The cookie file comes from a separate, optional Secret** (`feedme-youtube-cookies`), not a key in
`feedme-secrets`. A missing Secret leaves the volume empty and the worker starts normally; a missing
*key* inside an existing Secret would block the pod from starting - a bad trade for an optional
feature. Verified: the worker runs 1/1 with no such Secret present.

Rejected alternatives: a residential proxy (~$5-15/mo, against the $0/mo goal of
[ADR-0016](0016-oracle-cloud-k3s-over-aws.md)), and a home Tailscale exit node (free, but makes a
user-facing feature depend on a home internet connection).

## Consequences

- Gain: gated videos work. Without cookies, most videos still work and the failure is a clear,
  actionable message rather than a wall of yt-dlp diagnostics.
- **Cost: a second read-only trap.** yt-dlp rewrites the cookie jar when its context closes, and a
  Kubernetes Secret mount is always read-only — so pointing `cookiefile` at the mount made *every*
  fetch fail with `OSError: [Errno 30]`, including videos that had worked before cookies existed.
  `extract_info` now copies to a 0600 temp file and unlinks it in a `finally`. The unit test had
  asserted only that `cookiefile` was passed, which it was; it now asserts it is a *copy*.
- Cost: the worker image grows by roughly 80MB for the Deno binary, which compounds with the
  per-deploy image accumulation already tracked in the backlog.
- **Cost: cookies expire**, after weeks to months, and ingestion then silently reverts to failing on
  gated videos. This is a third instance of the "no alerting on silent failures" backlog item.
- Cost: cookies tie the server to a Google account. Use a throwaway - YouTube does sometimes flag
  accounts used for automated access, and the blast radius should not include a real account.
- The error tells users to paste the transcript, but the only manual path is the `instagram` source,
  so they must mislabel a YouTube video to use it. Filed in the backlog.
- Revisit when: cookie refresh becomes annoying enough to justify paying for residential egress, or
  if YouTube starts gating enough videos that server-side fetching stops being worth it at all.
