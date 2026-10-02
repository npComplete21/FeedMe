# ADR 0027: Duplicate ingredients are merged on every deploy, not by a one-off script

Status: Accepted

## Context

[ADR-0008](0008-ingredient-normalization-alias-map.md)'s normalization only applies to ingredient
names as they're saved. Rows created before it existed stayed split - the real `"onions"` /
`"onion (for cooking)"` / `"onion (for blender)"` duplicates from live testing are three
`Ingredient` rows, so pantry matching treats them as three different things.

The backlog asked for a one-off script. But this isn't a one-off problem: every new entry in the
synonym map (which ADR-0008 says to extend "as real mismatches turn up") creates the same split
for whatever already exists under the old spelling. A script someone has to remember to run after
each synonym change will eventually be forgotten.

## Decision

`merge_duplicate_ingredients()` in `app/ingredients/dedup.py` groups every `Ingredient` row by its
normalized name and collapses each group into one row with the canonical spelling:

- The row already spelled canonically is kept if there is one, else the oldest, renamed.
- `RecipeIngredient` links are repointed to it. A recipe that linked two spellings (it listed both
  "onion" and "onions") keeps one link, with both quantities joined (`"1; 2 more"`) rather than
  silently dropping one - the unique `(recipe_id, ingredient_id)` constraint allows only one.
- The now-unused duplicate rows are deleted.

It is idempotent and cheap (one pass over a small lookup table), so it runs as
`python -m app.ingredients.dedup` right after `alembic upgrade head`, in both the API pod's
`migrate` init container and the Dockerfile `CMD` used by docker compose. `--dry-run` reports
without committing.

## Consequences

- Gain: existing duplicates are fixed on the next deploy, and adding a synonym is now a complete
  change by itself - the next deploy merges the old rows too.
- Gain: tested against real Postgres (`tests/ingredients/test_dedup.py`), including the
  both-spellings-in-one-recipe case that would otherwise violate the unique constraint.
- Cost: a data rewrite runs at every API start. Acceptable because it is a no-op once the data is
  clean, and it touches only the shared lookup table, never a user's recipe content beyond which
  ingredient row a line points at.
- Cost: merging is one-way. If a synonym turns out to be wrong (two genuinely different
  ingredients mapped together), removing it from the map won't split them again - the recipes'
  `raw_text` still has the original wording if that ever needs reconstructing by hand.
