"""SQLite pragmas for the web app's database engine.

The production engine previously used SQLite with default settings:
no WAL mode and the default 5-second lock timeout, so concurrent
writes (e.g. auth-token inserts at login) could fail with
``sqlite3.OperationalError: database is locked`` as a transient 500.

WAL mode lets readers proceed while one writer holds the database,
and a 30-second busy timeout makes writers wait instead of failing
immediately. Both are no-ops on in-memory databases, so test engines
are unaffected. No application query logic changes.
"""

from __future__ import annotations

from sqlalchemy import event


def apply_sqlite_pragmas(engine) -> None:
    """Attach WAL + busy_timeout pragmas to a SQLAlchemy engine.

    Safe to call on any engine: the listener only runs for SQLite
    DBAPI connections, and the pragmas are harmless on in-memory
    databases (journal_mode reports "memory" there).
    """
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()
