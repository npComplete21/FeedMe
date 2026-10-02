"""add recipe rating

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('recipes', sa.Column('rating', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('ck_recipes_rating_range', 'recipes', 'rating BETWEEN 1 AND 5')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_recipes_rating_range', 'recipes', type_='check')
    op.drop_column('recipes', 'rating')
