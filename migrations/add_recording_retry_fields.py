"""Add retry fields to Recording model

This migration adds the following fields to the Recording model:
- finish_time: DateTime field to store the calculated end time
- retry_count: Integer field to track retry attempts
- partial_files: Text field to store JSON list of partial file paths

For existing records, it calculates and populates finish_time based on start_time + duration.
"""

from datetime import timedelta
import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, DateTime, Text

# Define the Recording table for use in this migration
recordings = table('recording',
    column('id', Integer),
    column('start_time', DateTime),
    column('duration', Integer),
    column('finish_time', DateTime),
    column('retry_count', Integer),
    column('partial_files', Text)
)

def upgrade():
    # Add new columns
    op.add_column('recording', sa.Column('finish_time', sa.DateTime(), nullable=True))
    op.add_column('recording', sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('recording', sa.Column('partial_files', sa.Text(), nullable=True))
    
    # Get all existing recordings
    connection = op.get_bind()
    results = connection.execute(sa.select([recordings.c.id, recordings.c.start_time, recordings.c.duration]))
    
    # Update finish_time for existing recordings
    for id, start_time, duration in results:
        if start_time:
            finish_time = start_time + timedelta(minutes=duration)
            connection.execute(
                recordings.update().
                where(recordings.c.id == id).
                values(finish_time=finish_time)
            )

def downgrade():
    # Remove the columns if needed
    op.drop_column('recording', 'finish_time')
    op.drop_column('recording', 'retry_count')
    op.drop_column('recording', 'partial_files')
