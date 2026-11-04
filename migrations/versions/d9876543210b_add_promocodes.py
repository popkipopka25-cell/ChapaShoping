"""add promocodes

Revision ID: d9876543210b
Revises: c1234567890a
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9876543210b'
down_revision = 'c1234567890a'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('promo_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('discount_percent', sa.Integer(), nullable=False),
    sa.Column('uses_count', sa.Integer(), nullable=False),
    sa.Column('max_uses', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('promo_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_promo_codes_code'), ['code'], unique=True)

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('promo_code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('discount_percent', sa.Integer(), nullable=False, server_default='0'))

def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('discount_percent')
        batch_op.drop_column('promo_code')
    op.drop_table('promo_codes')
