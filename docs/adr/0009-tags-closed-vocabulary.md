# ADR 0009: Cuisine/meal type as an LLM-constrained closed vocabulary, not free text

Status: Accepted

## Context

Phase 1.2 adds `cuisine`, `meal_type`, and `cook_time_minutes` so recipes can be tagged and
filtered. The ingredient-name problem solved in ADR-0008 looked superficially similar — "the LLM's
raw output doesn't reliably match itself across recipes" — but the two are structurally different:
ingredient names are an effectively unbounded vocabulary (can't enumerate every ingredient in the
world), while cuisine and meal type are naturally small, closed categories.

## Decision

Constrain `cuisine` and `meal_type` at the *generation* boundary using `typing.Literal` types on
`ParsedRecipe` (`app/parsing/recipe_parser.py`), so `client.messages.parse()` and Pydantic reject
any value outside the allowed set before it ever reaches the database. `cook_time_minutes` stays a
plain nullable integer — it's not a vocabulary problem, and inventing a time when the text doesn't
support one would be worse than leaving it null.

Storage stays a plain `String` column (not a Postgres `ENUM`) — the constraint already lives at the
one place that writes these values; a DB-level enum would mean a migration every time the allowed
list changes, for no added safety.

The Streamlit UI's filter dropdowns duplicate this list as a hardcoded Python list rather than
importing `Cuisine`/`MealType` from the backend module. This is deliberate, not an oversight: the UI
is a pure HTTP client of the API (ADR-0004), and once Phase 2 splits the backend and UI into
separate Docker images, an import would drag `anthropic`/`sqlalchemy`/etc. into the UI image just
to get two lists of strings.

## Consequences

- Gain: `cuisine`/`meal_type` values are guaranteed consistent by construction — no drift, no
  normalization step needed later, unlike the ingredient case
- Gain: filtering (`GET /recipes?cuisine=korean`) is a trivial exact-match query, not a fuzzy one
- Cost: the allowed list is a judgment call up front, and a genuinely novel cuisine gets bucketed
  into `"other"` rather than getting its own value, until someone extends the `Literal`
- Cost: the UI's hardcoded option list can drift from the backend's if one is edited without the
  other — accepted tradeoff, see rationale above; flagged as a watch item in
  [docs/backlog.md](../backlog.md) if it becomes an actual problem in practice
