"""add old_price and remove check constraint

Revision ID: c1234567890a
Revises: b35f2b432cf9
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1234567890a'
down_revision = 'b35f2b432cf9'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('old_price_stars', sa.Integer(), nullable=True))
        batch_op.drop_constraint('ck_price_positive', type_='check')
        batch_op.create_check_constraint('ck_price_positive', 'price_stars >= 0')

def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('old_price_stars')
        batch_op.drop_constraint('ck_price_positive', type_='check')
        batch_op.create_check_constraint('ck_price_positive', 'price_stars >= 1')
