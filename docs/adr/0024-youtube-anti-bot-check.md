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
| Installing Deno, the JS runtime yt-dlp warns is now required | still blocked |
| `youtube-transcript-api` - a different request path entirely | also blocked |
| Same video retried 6 times from the cluster | 0/6 |
| A different video (`dQw4w9WgXcQ`) from the same cluster | works |

So it is the **IP**, not the yt-dlp version, not the video being unavailable, and not probabilistic.
YouTube gates *specific* videos behind an anti-bot check when the request originates from a
datacenter range, and Oracle Cloud is heavily flagged. The JS-runtime theory was the most plausible
explanation and it was wrong - worth recording, because it is the first thing anyone will try again.

## Decision

**Optional cookie authentication, plus an honest error when it still fails.**

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

- Gain: with cookies loaded, gated videos work. Without them, most videos still work and the failure
  is a clear, actionable message rather than a wall of yt-dlp diagnostics.
- **Cost: cookies expire**, after weeks to months, and ingestion then silently reverts to failing on
  gated videos. This is a third instance of the "no alerting on silent failures" backlog item.
- Cost: cookies tie the server to a Google account. Use a throwaway - YouTube does sometimes flag
  accounts used for automated access, and the blast radius should not include a real account.
- The error tells users to paste the transcript, but the only manual path is the `instagram` source,
  so they must mislabel a YouTube video to use it. Filed in the backlog.
- Revisit when: cookie refresh becomes annoying enough to justify paying for residential egress, or
  if YouTube starts gating enough videos that server-side fetching stops being worth it at all.
