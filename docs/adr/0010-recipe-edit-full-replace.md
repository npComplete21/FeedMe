# ADR 0010: Recipe editing replaces ingredients wholesale, not by diffing

Status: Accepted

## Context

Phase 1.3 needed a way to fix a bad LLM parse in-app. Every recipe field except ingredients is a
simple scalar column (title, steps, cuisine, meal_type, cook_time_minutes) — trivial to update.
Ingredients are a many-to-many relationship through `RecipeIngredient`, which raises a real
design choice: when the user submits an edited ingredient list, do we diff it against the existing
`RecipeIngredient` rows (matching by name, adding new ones, removing missing ones, updating
changed quantities), or do we throw away all existing links and recreate them from the submitted
list?

Diffing is more "surgical" but meaningfully more code: matching submitted items back to existing
rows requires a matching key (name? position? an id the client would need to track?), and every
edge case (renamed ingredient, reordered list, duplicate names) needs its own handling.

## Decision

Full replace: `update_recipe()` (`app/persistence/recipe_store.py`) clears a recipe's
`RecipeIngredient` rows and recreates them from the submitted list, reusing the exact same
`_get_or_create_ingredient()` / normalization logic that initial parsing uses (`_set_ingredients()`,
shared by both `persist_recipe()` and `update_recipe()`).

The practical effect: whether an ingredient list comes from a fresh LLM parse or a manual edit, the
recipe ends up in exactly the same state - same normalization, same dedup behavior. There's no
"edit-only" code path with its own subtly different rules.

## Consequences

- Gain: one code path for "these are this recipe's ingredients now," used by both creation and
  editing. No separate diffing logic to maintain or get subtly wrong.
- Gain: editing an ingredient automatically benefits from Phase 1.1's synonym/normalization
  handling - confirmed live: editing Bulgogi's ingredients and typing "scallion" landed as
  "green onion" in the DB, same as if the LLM had produced it directly.
- Cost: no per-ingredient history - if you fix a typo in one ingredient, there's no record of what
  it looked like before (acceptable; recipes aren't audited data, and the DB row's `id` for that
  ingredient does change since it's a delete+recreate, not an update-in-place). If this ever
  matters, RawSource still holds the original parse for reference.
- The UI form always submits the *complete* ingredient list (full `PUT` semantics), never a partial
  patch - consistent with treating the edit form as "here is the corrected state," not "here are
  the deltas."
