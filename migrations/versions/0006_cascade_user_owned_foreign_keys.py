"""cascade deletes on user-owned foreign keys

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 00:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (constraint name, table, column, referenced table, ondelete). Names are the
# ones Postgres/0003 actually created, so the drop/recreate targets real objects.
# recipe_ingredients.ingredient_id is deliberately absent: ingredients is a shared
# lookup table, so deleting one still in use by any recipe should keep failing.
_FKS = [
    ("recipes_user_id_fkey", "recipes", "user_id", "users", "CASCADE"),
    ("raw_sources_user_id_fkey", "raw_sources", "user_id", "users", "CASCADE"),
    ("recipe_ingredients_recipe_id_fkey", "recipe_ingredients", "recipe_id", "recipes", "CASCADE"),
    # SET NULL rather than CASCADE: a recipe keeps its own copy of the source text
    # (raw_source_text), so losing the staging row shouldn't take the recipe with it.
    ("fk_recipes_raw_source_id_raw_sources", "recipes", "raw_source_id", "raw_sources", "SET NULL"),
]


def _recreate(ondelete_for: dict[str, str | None]) -> None:
    for name, table, column, referred, _ in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, referred, [column], ["id"], ondelete=ondelete_for[name]
        )


def upgrade() -> None:
    """Upgrade schema."""
    _recreate({name: ondelete for name, *_, ondelete in _FKS})


def downgrade() -> None:
    """Downgrade schema."""
    _recreate({name: None for name, *_ in _FKS})
