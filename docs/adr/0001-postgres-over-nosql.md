# ADR 0001: PostgreSQL over a NoSQL store

Status: Accepted

## Context

FeedMe's core data is a `Recipe` made of a many-to-many relationship to `Ingredient` (via
`RecipeIngredient`, carrying quantity/unit), owned by a `User`. The main query the app exists to
serve — "given these ingredients, which recipes match?" — is a relational join-and-filter
operation, not a document lookup. We also want strong schema validation on write, since recipes
arrive via LLM parsing of noisy captions/transcripts and are prone to malformed output.

At the same time, some fields are genuinely unstructured (raw caption text, raw LLM output kept
for debugging/re-parsing) and don't benefit from a rigid column schema.

We're not expecting write volumes or schema volatility that would justify a document store's
main advantages (schema-less flexibility, horizontal write scale).

## Decision

Use PostgreSQL as the single datastore, with JSONB columns for the genuinely unstructured fields
(raw source text, raw LLM parse output), rather than a NoSQL document store (e.g. MongoDB) or a
polyglot split between relational + document DBs.

## Consequences

- Gain: relational integrity (foreign keys actually enforced), mature Python tooling
  (SQLAlchemy + Alembic), and SQL is a natural fit for the ingredient-matching query
- Gain: JSONB gives document-store flexibility for the specific fields that need it, without
  taking on a second database technology to operate/learn
- Give up: schema-less flexibility across the whole dataset — every structural change to
  `Recipe`/`Ingredient` needs a migration. Acceptable since the recipe domain model is fairly
  well understood upfront and migrations are cheap at this scale
- Revisit if: write volume or schema volatility grows dramatically (not expected for a
  personal/small-multi-user app) — e.g. if we ever ingest at a scale where Postgres write
  throughput becomes the bottleneck
