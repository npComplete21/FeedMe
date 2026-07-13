# ADR 0007: `messages.parse()` + Pydantic schema for recipe extraction, model swappable via env var

Status: Accepted

## Context

Turning a noisy caption/transcript into a structured `Recipe` (title, ingredients, steps) needs
the LLM's output to reliably match a schema — a hand-written prompt asking for JSON risks
wrapped prose, missing fields, or invalid JSON that then needs defensive parsing and retries.

Separately, Anthropic's current guidance defaults to their most capable model (Opus-tier) for
any task unless a cheaper model is explicitly requested — cost is meant to be the caller's
decision, not silently applied by tooling. For a personal project doing many small, fairly
mechanical extraction calls (one per saved recipe), that default has a real cost implication
worth being able to tune without touching code.

## Decision

Use the Anthropic SDK's `client.messages.parse()` with a Pydantic `ParsedRecipe` model passed as
`output_format` (`app/parsing/recipe_parser.py`) — the SDK validates the response against the
schema automatically, rather than hand-rolling tool-use forcing or raw-prompt JSON parsing.

For the model, default to `claude-opus-4-8` (Anthropic's current recommended default), but read
it from a `RECIPE_PARSER_MODEL` environment variable so it can be swapped (e.g. to
`claude-haiku-4-5`) without a code change once real usage cost is observed.

## Consequences

- Gain: no hand-written JSON schema for tool-use, no manual retry-on-malformed-JSON logic — the
  SDK guarantees `parsed_output` matches `ParsedRecipe` or raises
- Gain: model choice is a config change (env var), not a code change, so cost-tuning later is cheap
- Cost now: Opus-tier pricing on every ingested recipe is meaningfully higher per-call than
  Haiku — worth watching actual spend once ingestion volume is real, and switching the env var
  down if extraction quality holds up on a cheaper model. `RecipeParseError` is raised on a
  `stop_reason: "refusal"` so callers can distinguish "model declined" from a normal result
