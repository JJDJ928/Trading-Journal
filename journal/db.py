"""SQLite storage for Trading Journal.

Money is stored as integer cents so totals are exact. Screenshots are files on
disk; the database only keeps their names.
"""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    firm                TEXT,
    type                TEXT    NOT NULL CHECK (type IN ('evaluation', 'funded', 'personal')),
    status              TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'passed', 'breached', 'closed')),
    start_balance_cents INTEGER NOT NULL,
    profit_target_cents INTEGER,
    max_drawdown_cents  INTEGER,
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    traded_at   TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    side        TEXT    NOT NULL CHECK (side IN ('long', 'short')),
    contracts   REAL,
    setup       TEXT,
    entry       REAL,
    stop        REAL,
    exit        REAL,
    pnl_cents   INTEGER NOT NULL,
    notes       TEXT,
    tags        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS trades_account ON trades(account_id);
CREATE INDEX IF NOT EXISTS trades_time ON trades(traded_at);

CREATE TABLE IF NOT EXISTS screenshots (
    id            INTEGER PRIMARY KEY,
    trade_id      INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL UNIQUE,
    original_name TEXT,
    content_type  TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Daily habits tab: one row per calendar day, with the tasks ticked off and that day's journal entry.
CREATE TABLE IF NOT EXISTS days (
    date       TEXT PRIMARY KEY,
    done       TEXT NOT NULL DEFAULT '[]',
    journal    TEXT,
    mood       INTEGER CHECK (mood BETWEEN 1 AND 5),
    energy     INTEGER CHECK (energy BETWEEN 1 AND 5),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Reading: books, and one chapter recap per day.
CREATE TABLE IF NOT EXISTS books (
    id             INTEGER PRIMARY KEY,
    title          TEXT    NOT NULL,
    author         TEXT,
    total_chapters INTEGER,
    status         TEXT    NOT NULL DEFAULT 'reading' CHECK (status IN ('reading', 'finished')),
    finished_on    TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    date       TEXT PRIMARY KEY,
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter    INTEGER,
    learned    TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Wins wall: milestones with an optional photo (stored with the screenshots).
CREATE TABLE IF NOT EXISTS wins (
    id         INTEGER PRIMARY KEY,
    date       TEXT NOT NULL,
    title      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'personal' CHECK (category IN ('trading', 'fitness', 'reading', 'personal')),
    note       TEXT,
    photo      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after a table first shipped; older databases get them on start-up.
MIGRATIONS = (
    ("days", "mood", "INTEGER CHECK (mood BETWEEN 1 AND 5)"),
    ("days", "energy", "INTEGER CHECK (energy BETWEEN 1 AND 5)"),
)


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path):
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        conn.commit()
    finally:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
