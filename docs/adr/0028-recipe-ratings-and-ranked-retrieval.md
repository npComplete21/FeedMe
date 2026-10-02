# ADR 0028: Recipe ratings - a column, one shared ranked query, and a chat tool

Status: Accepted

## Context

The roadmap's Phase 4 lists "recipe photos, ratings, 'cooked this' tracking"; the backlog sharpened
the ratings part: rate recipes, then pull a ranked list filterable by ingredient and cuisine, and
make that reachable from the chat so "give me my 5 best chicken recipes" resolves to a real query
rather than the model guessing ([ADR-0011](0011-chat-uses-tool-use-not-free-text-reasoning.md)
already settled that chat answers come from tools, not free-text recall).

Three design questions:

1. **Where the rating lives.** A `rating` column on `recipes`, or a `ratings` table.
2. **How it's written.** Through the existing `PUT /recipes/{id}` edit, or separately.
3. **How "ranked + filtered" is shared** between the recipe list and the chat.

## Decision

- **A nullable `recipes.rating SMALLINT`** with `CHECK (rating BETWEEN 1 AND 5)` (migration `0007`).
  Recipes are single-owner ([ADR-0002](0002-user-id-scoping-from-day-one.md)), so there is exactly
  one person who can rate a given recipe - a table keyed by `(user_id, recipe_id)` would model a
  many-raters case that can't happen. NULL means "not rated", which sorts last.
- **Its own endpoint, `PUT /recipes/{id}/rating`** (`{"rating": 1-5 | null}`). The recipe edit
  endpoint is full-replace ([ADR-0010](0010-recipe-edit-full-replace.md)); folding rating into it
  would mean every content fix has to resend the rating or silently clear it.
- **One query, `find_recipes()`** in `app/persistence/recipe_queries.py`, used by both
  `GET /recipes` (new `sort=newest|rating`, `ingredient=`, `limit=` params) and the chat's new
  `top_rated_recipes` tool. The ingredient filter normalizes the input the same way saved
  ingredients are normalized ([ADR-0008](0008-ingredient-normalization-alias-map.md)) and matches
  whole words, so "chicken" finds "chicken thighs" but not "chickpea".
- **The chat tool reports unrated recipes as unrated** rather than hiding them, and says so when
  nothing matching has a rating yet - otherwise "your best chicken recipes" would answer with
  whatever happened to sort first.
- **UI:** a 5-star `st.feedback` widget inside each recipe (saves on click) and a "Sort by:
  Newest / Highest rated" control.

## Consequences

- Gain: the list view and the chat agree on what "best" means because they run the same SQL.
- Gain: ratings survive recipe edits, and the database rejects out-of-range values regardless of
  which code path writes them.
- Cost: no rating history and no "cooked this" count - a single current rating only. If shared or
  public recipes ever happen, ratings move to their own table; that is a straightforward migration
  from one column.
- Cost: the whole-word ingredient match uses a Postgres regex (`~ '\mchicken\M'`), which can't use
  an index. Fine at personal-collection scale; revisit only if collections get large.
