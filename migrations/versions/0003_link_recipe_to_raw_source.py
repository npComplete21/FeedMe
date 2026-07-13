"""link recipe to raw source

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13 17:38:17.123052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "fk_recipes_raw_source_id_raw_sources"


def upgrade() -> None:
    op.add_column('recipes', sa.Column('raw_source_id', sa.Integer(), nullable=True))
    op.create_foreign_key(_FK_NAME, 'recipes', 'raw_sources', ['raw_source_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, 'recipes', type_='foreignkey')
    op.drop_column('recipes', 'raw_source_id')
