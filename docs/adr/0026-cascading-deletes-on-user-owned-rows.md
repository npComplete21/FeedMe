# ADR 0026: Cascading deletes on user-owned rows, enforced by the database

Status: Accepted

## Context

Every foreign key was a plain `ForeignKey(...)`, which Postgres treats as `NO ACTION`. The
`cascade="all, delete-orphan"` on `Recipe.ingredients` is ORM-only - it does nothing for a SQL
`DELETE`. Deleting a user meant deleting child-first by hand (`recipe_ingredients` → `recipes` →
`raw_sources` → `users`), which is how the Phase 3.9 test accounts were removed, and the obvious
"delete my account" implementation (`db.delete(user)`) raised an `IntegrityError` instead.

Each foreign key needed a deliberate answer, because the tables don't all have the same owner.

## Decision

Migration `0006` recreates the foreign keys with explicit `ondelete` behavior:

| Foreign key | `ondelete` | Why |
|---|---|---|
| `recipes.user_id` | `CASCADE` | A user's recipes belong to them |
| `raw_sources.user_id` | `CASCADE` | Same |
| `recipe_ingredients.recipe_id` | `CASCADE` | Link rows mean nothing without their recipe |
| `recipes.raw_source_id` | `SET NULL` | The recipe keeps its own copy (`raw_source_text`), so losing the staging row shouldn't take the recipe with it |
| `recipe_ingredients.ingredient_id` | unchanged (`NO ACTION`) | `ingredients` is a shared lookup table with no owner; deleting one still in use is a bug and should keep failing |

`User.recipes` gains `passive_deletes=True`. Without it, SQLAlchemy's default for a deleted parent
is to `UPDATE recipes SET user_id = NULL` before the `DELETE`, which violates `NOT NULL` before the
database's cascade ever runs.

## Consequences

- Gain: deleting a user is one statement, from SQL or the ORM - a "delete my account" feature no
  longer has a trap waiting in it. `tests/test_models.py` covers both paths.
- Gain: the rule lives in the schema, so manual cleanup with `psql` gets the same behavior as code.
- Cost: a mistaken `DELETE FROM users` now takes that user's data with it instead of failing.
  Acceptable - the nightly off-node backups ([ADR-0023](0023-postgres-backups-to-object-storage.md))
  are the recovery path, not a constraint violation.
- Orphaned `ingredients` rows (used by no recipe) are never cleaned up automatically. Harmless -
  they're a few bytes each and are reused if the ingredient shows up again.
