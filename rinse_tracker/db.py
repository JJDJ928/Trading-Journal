"""SQLite connection handling and schema.

Money is stored as integer cents to keep totals exact. Screenshots are stored
as files on disk; the database only keeps their file names.
"""
import sqlite3

from flask import current_app, g

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY,
    firm          TEXT    NOT NULL,
    account_ref   TEXT,
    size_cents    INTEGER NOT NULL,
    type          TEXT    NOT NULL CHECK (type IN ('evaluation', 'funded')),
    cost_cents    INTEGER NOT NULL DEFAULT 0,
    purchase_date TEXT    NOT NULL,
    status        TEXT    NOT NULL
                  CHECK (status IN ('active', 'passed', 'funded', 'failed', 'closed')),
    pass_date     TEXT,
    end_date      TEXT,
    -- A funded account created from a passed evaluation points at it.
    -- UNIQUE: one evaluation can only ever produce one funded account.
    parent_id     INTEGER UNIQUE REFERENCES accounts(id) ON DELETE RESTRICT,
    notes         TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS account_status_history (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status   TEXT    NOT NULL,
    changed_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    traded_at   TEXT    NOT NULL,
    instrument  TEXT,
    result      TEXT    NOT NULL CHECK (result IN ('win', 'loss', 'breakeven')),
    pnl_cents   INTEGER,
    summary     TEXT,
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS screenshots (
    id            INTEGER PRIMARY KEY,
    trade_id      INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL UNIQUE,
    original_name TEXT,
    content_type  TEXT,
    size_bytes    INTEGER,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payouts (
    id              INTEGER PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    requested_cents INTEGER NOT NULL,
    received_cents  INTEGER,
    request_date    TEXT    NOT NULL,
    payment_date    TEXT,
    status          TEXT    NOT NULL
                    CHECK (status IN ('requested', 'approved', 'rejected', 'paid')),
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- AI coach conversations (added in schema v2). Messages are append-only and
-- store the exact content blocks sent to / returned by the API.
CREATE TABLE IF NOT EXISTS coach_threads (
    id          INTEGER PRIMARY KEY,
    title       TEXT    NOT NULL,
    trade_id    INTEGER REFERENCES trades(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coach_messages (
    id           INTEGER PRIMARY KEY,
    thread_id    INTEGER NOT NULL REFERENCES coach_threads(id) ON DELETE CASCADE,
    role         TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content      TEXT    NOT NULL,  -- JSON list of content blocks
    display_text TEXT,              -- what the conversation view shows
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_coach_messages ON coach_messages(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id, traded_at);
CREATE INDEX IF NOT EXISTS idx_screens_trade ON screenshots(trade_id);
CREATE INDEX IF NOT EXISTS idx_payouts_account ON payouts(account_id);
CREATE INDEX IF NOT EXISTS idx_history_account ON account_status_history(account_id);
"""

REQUIRED_TABLES = {"accounts", "account_status_history", "trades", "screenshots", "payouts"}


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    """Create tables if needed and run migrations. Safe to call on every start."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        migrate(conn)
        conn.commit()
    finally:
        conn.close()


def migrate(conn):
    """Bring an older database up to SCHEMA_VERSION.

    Future schema changes go here as `if version < N:` steps so existing
    records (and restored backups) keep working.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    # v2: coach tables, created by SCHEMA above (CREATE TABLE IF NOT EXISTS).
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}
