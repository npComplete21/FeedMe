# ADR 0008: Ingredient normalization via alias map + parenthetical stripping

Status: Accepted

## Context

Real usage surfaced a concrete bug: `"onions"`, `"onion (for cooking)"`, and `"onion (for blender)"` —
all from real LLM-parsed recipes — created three separate `Ingredient` rows instead of one, because
normalization was just `strip().lower()`. This breaks both ingredient dedup at persistence time and
pantry matching at query time, and the roadmap's Phase 1 item ("ingredient synonym handling, e.g.
`scallion` == `green onion`") anticipated exactly this class of problem.

Three approaches were considered:

1. **Blind pluralization/stemming** (strip a trailing `s`) — fails on words that end in `s`
   naturally (`hummus`, `asparagus`); a classic over-stemming trap that looks fine until it silently
   corrupts real data.
2. **Embeddings / fuzzy matching** — would generalize better, but the roadmap's own Phase 0 note
   said explicitly to defer this until naive matching actually proves insufficient. It hasn't yet
   — the two things that broke (parenthetical prep notes, a couple of known synonyms) don't need it.
3. **A small explicit alias map + regex-stripped parenthetical notes** — deterministic, fully unit
   testable, and directly matches the roadmap's own example.

Separately: normalization logic existed as two near-identical private functions, one in
`app/persistence/recipe_store.py` (used for ingredient dedup on save) and one in
`app/matching/ingredient_matcher.py` (used for pantry comparison). Two copies of "what makes two
ingredient names the same" is itself a latent bug — they can silently drift apart.

## Decision

Extract a single shared function, `normalize_ingredient_name()` in `app/ingredients/normalization.py`,
used by both persistence and matching. It: lowercases and strips whitespace, strips parenthetical
prep notes (`"onion (for cooking)"` → `"onion"`), then looks the result up in a small hand-curated
synonym dict (`"scallion"` → `"green onion"`, `"onions"` → `"onion"`, etc.).

## Consequences

- Gain: the concrete bug is fixed, and fixed identically everywhere ingredient names are compared —
  no more risk of persistence and matching disagreeing about what counts as "the same ingredient"
- Gain: fully deterministic and unit-testable; no model calls, no fuzzy-match tuning
- Cost: only catches variants explicitly listed in `_SYNONYMS` — a genuinely novel phrasing the LLM
  produces (that isn't a parenthetical note) won't be caught until someone adds it to the map
- Revisit if: the alias map grows unwieldy or misses often enough in practice that embeddings-based
  fuzzy matching becomes worth the added complexity — per the original Phase 0 guidance, that's a
  "wait until it hurts" call, not a default
