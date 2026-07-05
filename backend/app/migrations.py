"""Lightweight schema migrations for columns added to existing tables.

`Base.metadata.create_all()` only creates tables that don't exist yet —
it never adds a new column to a table that's already there. Since
`opportunities` already exists in production, adding `summary` or
`deadline_at` to the model does nothing there until we ALTER it
ourselves. This runs once at startup, is idempotent (skips columns that
already exist), and works on both SQLite (local dev) and Postgres
(production) since it only ever adds simple nullable columns.

Not a substitute for a real migration tool (Alembic) if this schema
keeps growing — but proportionate for the handful of additive columns
this project has needed so far.
"""

import logging

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

# (table, column, DDL type) — add a row here whenever a new column is
# added to an existing model's table.
_PENDING_COLUMNS: list[tuple[str, str, str]] = [
    ("opportunities", "summary", "VARCHAR(300)"),
    ("opportunities", "deadline_at", "DATE"),
    ("opportunities", "title_normalized", "VARCHAR(600)"),
    ("saved_opportunities", "reminder_sent_at", "TIMESTAMP"),
    # DEFAULT 'approved' means every row already live keeps showing —
    # only new inserts from opportunity_scraper.py explicitly override it.
    ("opportunities", "review_status", "VARCHAR(20) NOT NULL DEFAULT 'approved'"),
]


def run_pending_column_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table, column, ddl_type in _PENDING_COLUMNS:
        if table not in existing_tables:
            continue  # create_all() will create it with the new column already present
        existing_columns = {c["name"] for c in inspector.get_columns(table)}
        if column in existing_columns:
            continue

        logger.info("Migrating: adding %s.%s (%s)", table, column, ddl_type)
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
