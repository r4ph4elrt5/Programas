"""Transactional SQLite storage with versioned schema and foreign keys."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS videos (
 id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL,
 sha256 TEXT NOT NULL UNIQUE, info TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 video_id TEXT NOT NULL REFERENCES videos(id), platform TEXT NOT NULL,
 title TEXT NOT NULL, caption TEXT NOT NULL, metadata TEXT NOT NULL,
 status TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
 scheduled_at TEXT, created_at TEXT NOT NULL, completed_at TEXT,
 remote_id TEXT, url TEXT, confirmation TEXT, export_dir TEXT,
 progress REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attempts (
 id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
 created_at TEXT NOT NULL, outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id),
 created_at TEXT NOT NULL, event TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status_schedule ON jobs(status,scheduled_at);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.engine = create_engine("sqlite:///" + str(path), connect_args={"timeout": 15})

        @event.listens_for(self.engine, "connect")
        def setup(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.row_factory = sqlite3.Row

        with self.connection() as connection:
            connection.executescript(SCHEMA)
            version = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            if version != 1:
                raise RuntimeError("Versão de banco incompatível. Atualize o MultiPost.")

    @contextmanager
    def connection(self):
        connection = self.engine.raw_connection()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rows(self, sql, args=()):
        with self.connection() as connection:
            return [dict(row) for row in connection.execute(sql, args).fetchall()]

    def setting(self, key, default=None):
        rows = self.rows("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def save_setting(self, key, value):
        with self.connection() as connection:
            connection.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def backup(self, destination: Path):
        if destination.resolve() == self.path.resolve() or destination.exists():
            raise ValueError("Escolha um novo arquivo para o backup.")
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)

    def close(self):
        self.engine.dispose()
