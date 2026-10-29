"""SQLite transactions fence concurrent coordinators; no timed ownership stealing."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .phases import SETTLED


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS dependencies(issue TEXT PRIMARY KEY, status TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(issue TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, issue TEXT NOT NULL,
                    revision TEXT NOT NULL, active INTEGER NOT NULL, data TEXT NOT NULL,
                    UNIQUE(issue, revision));
                CREATE UNIQUE INDEX IF NOT EXISTS active_issue ON tasks(issue) WHERE active=1;
                CREATE TABLE IF NOT EXISTS ownership(workspace TEXT PRIMARY KEY, task TEXT UNIQUE NOT NULL,
                    token TEXT UNIQUE NOT NULL, owner TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL, issue TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', receipt TEXT);
                CREATE TABLE IF NOT EXISTS handoffs(task TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turn_lease(id INTEGER PRIMARY KEY CHECK(id=1), lease TEXT NOT NULL,
                    expires REAL NOT NULL);
            ''')

        self.path.chmod(0o600)

    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def task(db, task_id):
        row = db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("Unknown task")
        return json.loads(row[0])

    @staticmethod
    def save(db, task):
        db.execute("UPDATE tasks SET data=?,active=? WHERE id=?",
                   (json.dumps(task), int(task['phase'] not in SETTLED), task['id']))

    @staticmethod
    def enqueue(db, key, issue, payload):
        db.execute("INSERT OR IGNORE INTO outbox(key,issue,payload) VALUES(?,?,?)",
                   (key, issue, json.dumps(payload)))
