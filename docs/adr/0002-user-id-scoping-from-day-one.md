# ADR 0002: `user_id` scoping from day one, even as a single-user app

Status: Accepted

## Context

FeedMe starts as a single-user personal project but is explicitly intended to support multiple
users eventually (Phase 4). Retrofitting tenant isolation onto an existing schema and query
layer after the fact is expensive: every table needs a migration, every existing query needs an
audit, and it's easy to accidentally leave a query unscoped, leaking one user's data to another.

## Decision

Every user-owned table (`Recipe`, future `ChatMessage`, pantry data, etc.) carries a `user_id`
foreign key from the very first migration, and every query filters by it — even though Phase 0
has exactly one hardcoded user (`user_id=1`, no real auth yet).

## Consequences

- Gain: when real multi-user auth lands in Phase 4, it's a matter of deriving `user_id` from a
  session/token instead of hardcoding it — no schema migration, no query rewrite, no risk of
  missing a spot
- Cost now: a small amount of boilerplate (one extra FK column, always threading `user_id`
  through function calls) for a benefit that doesn't pay off until Phase 4
- Does not require building real auth early — auth and tenant-scoping are separate concerns;
  this ADR only commits to the schema/query shape, not to shipping login before it's needed
