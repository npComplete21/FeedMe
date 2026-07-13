# ADR 0006: A separate `raw_sources` staging table, not a "draft" Recipe

Status: Accepted

## Context

Content arrives from two ingestion paths (YouTube transcript fetch, manually pasted Instagram
captions) before it's been through LLM parsing (Phase 0.5) into a structured `Recipe` (title,
ingredients, steps). Two ways to model the in-between state:

1. Write directly into `Recipe`, with `title`/`steps` nullable and a `status` column
   distinguishing "raw" from "parsed"
2. A separate `RawSource` table that gets read by the parsing step and turned into a `Recipe`
   row, independent of it

Option 1 avoids a second table, but it means `Recipe`'s columns are conditionally meaningful
depending on status, and every query against `Recipe` has to remember to filter or account for
half-populated rows. It also conflates two different concerns — "content we ingested" and "a
structured recipe" — into one table.

## Decision

Use a separate `RawSource` table (`app/models.py`) holding `source_url`, `source_platform`,
`raw_text`, and whatever metadata the ingestion step already knows (`title`, `thumbnail_url`).
Both the YouTube pipeline (0.3) and the manual-paste path (0.4) write into it. The LLM parsing
step (0.5) will read a `RawSource` row and produce a `Recipe`.

## Consequences

- `Recipe` stays fully "real" — every row has a title, steps, ingredients. No conditional/nullable
  fields whose meaning depends on a status flag, no query needing to filter out unparsed rows
- Ingestion and parsing are decoupled: re-running the LLM parse on a `RawSource` (e.g. after
  improving the prompt) doesn't require mutating an existing `Recipe` in place
- Cost: one extra table and an extra migration up front, and 0.5/0.6 will need to decide how a
  `RawSource` links to the `Recipe` it produces (a FK from `Recipe` back to its `RawSource`, or
  no link at all if we don't need traceability) — deferred until we build that step
