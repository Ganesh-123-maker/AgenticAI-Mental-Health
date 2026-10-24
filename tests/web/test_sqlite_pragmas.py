"""SQLite pragma tests (Item 3b, 2026-10-24).

The production engine previously used SQLite defaults (no WAL, the
5-second lock timeout), so concurrent writes such as auth-token
inserts at login could fail with "database is locked" as a transient
500. apply_sqlite_pragmas enables WAL mode plus a 30-second busy
timeout. Tests run against a temp file database outside the repo.
"""

import pathlib
import sys
import threading

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from web.backend.sqlite_pragmas import apply_sqlite_pragmas


@pytest.fixture()
def db_file(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    apply_sqlite_pragmas(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE authtoken (id INTEGER PRIMARY KEY, token TEXT)"))
    return engine


def test_pragmas_are_set_on_file_database(db_file):
    with db_file.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert journal_mode == "wal"
    assert busy_timeout == 30000


def test_concurrent_inserts_do_not_hit_database_locked(db_file):
    errors = []

    def insert_rows(worker):
        try:
            with db_file.begin() as conn:
                for i in range(25):
                    conn.execute(
                        text("INSERT INTO authtoken (token) VALUES (:token)"),
                        {"token": f"w{worker}-{i}"},
                    )
        except Exception as exc:  # noqa: BLE001 - collected, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=insert_rows, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"concurrent inserts failed: {errors[:3]}"
    with db_file.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM authtoken")).scalar()
    assert count == 200
