"""Tests for feat_db.py — live database drivers (v1.4, Group A).

Run: .test-venv-db/bin/python tests/test_feat_db.py   (from the project root)
Also pytest-collectable (plain asserts, no fixtures). No Streamlit needed.

What is live-tested here:
  * wheel files on disk: filename tags + .pyd PE32+ x86-64 check (pure
    Python, no `file` binary needed) + mysql-connector-python import.
  * refused-connection handling against a closed local port (MySQL driver
    is installed in the venv, so the driver actually attempts the TCP
    connect and fails cleanly — no traceback in the message).
  * the full connect -> list-tables -> load-table path against a mock
    DBAPI connector (no database server exists on this machine).
What is NOT tested here: a real MySQL / PostgreSQL / SQL Server login.
psycopg2-binary and pymssql cannot even import on Linux (Windows .pyd),
so their checks are wheel-content + PE-format only, by design.
"""

import importlib.util
import socket
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import feat_db

WHEELS = Path(__file__).resolve().parent.parent / "hidden_files" / "wheels"

EXPECTED_WHEELS = {
    "mysql": "mysql_connector_python-26.10.0-py2.py3-none-any.whl",
    "postgres": "psycopg2_binary-2.9.13-cp312-cp312-win_amd64.whl",
    "sqlserver": "pymssql-2.4.6-cp312-cp312-win_amd64.whl",
}


def _pe_machine(data: bytes):
    """Machine type of a Windows PE file (0x8664 = x86-64), or None."""
    if data[:2] != b"MZ":
        return None
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\x00\x00":
        return None
    return struct.unpack_from("<H", data, pe_off + 4)[0]


def _free_closed_port() -> int:
    """A port that is definitely closed right now (bound, then released)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_wheels_present_and_tagged():
    for key, name in EXPECTED_WHEELS.items():
        path = WHEELS / name
        assert path.is_file(), f"missing wheel: {name}"
        assert path.stat().st_size > 0, f"empty wheel: {name}"
        print(f"wheel {key}: {name} ({path.stat().st_size:,} bytes)")
    print("wheels present OK")


def test_wheel_contents_pe64():
    """Every .pyd/.dll inside the Windows wheels is PE32+ x86-64; the pure
    Python MySQL wheel has no native code at all."""
    for key, name in EXPECTED_WHEELS.items():
        with zipfile.ZipFile(WHEELS / name) as z:
            natives = [n for n in z.namelist()
                       if n.endswith((".pyd", ".dll"))]
            if key == "mysql":
                assert not natives, f"pure-Python wheel should have no .pyd: {natives}"
                assert "mysql/connector/__init__.py" in z.namelist() or any(
                    n.startswith("mysql/") for n in z.namelist()), "no mysql package in wheel"
                print("wheel mysql: pure Python, no native code — OK")
                continue
            assert natives, f"{name} has no .pyd/.dll — not a precompiled wheel"
            for n in natives:
                machine = _pe_machine(z.read(n))
                assert machine == 0x8664, f"{n} in {name}: machine={machine:#x}, not x86-64"
                print(f"wheel {key}: {n} -> PE32+ x86-64 OK")
    print("wheel contents OK")


def test_mysql_connector_imports():
    import mysql.connector
    assert mysql.connector.__version__.startswith("26.")
    print("mysql.connector imports OK:", mysql.connector.__version__)


def test_driver_status_shape():
    status = feat_db.db_driver_status()
    assert set(status) == {"mysql", "postgres", "sqlserver"}, status
    assert all(isinstance(v, bool) for v in status.values()), status
    # Status must agree with what actually imports in THIS Python.
    for key, (module, _pkg, _port) in feat_db.DRIVERS.items():
        expected = importlib.util.find_spec(module) is not None
        assert status[key] == expected, f"{key}: status {status[key]} != importable {expected}"
    print("driver status OK:", status)


def test_refused_connection_clean_error():
    """MySQL driver installed -> real TCP attempt to a closed port -> a
    plain one-line message, never a traceback, never an exception."""
    assert feat_db.db_driver_status()["mysql"], "MySQL driver not installed in venv"
    port = _free_closed_port()
    ok, msg = feat_db.test_connection(
        "mysql", host="127.0.0.1", port=port,
        user="nobody", password="wrong", database="nodb")
    assert ok is False, f"expected failure, got ok with {msg!r}"
    assert "Traceback" not in msg and "Traceback" not in str(type(msg))
    assert "127.0.0.1" in msg and str(port) in msg
    assert len(msg) < 500, f"message suspiciously long: {msg!r}"
    print("refused-connection OK:", msg)


def test_unknown_engine_and_missing_driver():
    ok, msg = feat_db.test_connection("oracle", host="127.0.0.1")
    assert ok is False and "Unknown database engine" in msg
    # psycopg2 / pymssql are Windows-only wheels: not importable on Linux,
    # so test_connection must report "not installed", not crash.
    for eng in ("postgres", "sqlserver"):
        if not feat_db.db_driver_status()[eng]:
            ok, msg = feat_db.test_connection(eng, host="127.0.0.1")
            assert ok is False and "not installed" in msg.lower(), (eng, msg)
            print(f"missing-driver message OK ({eng}): {msg[:90]}...")
    print("unknown-engine / missing-driver OK")


# ------------------------------------------------------- mock DBAPI -----
class _FakeCursor:
    """Minimal DBAPI cursor: canned tables + rows, records the SQL run."""

    def __init__(self, tables, rows_by_table):
        self.tables = tables
        self.rows_by_table = rows_by_table
        self.description = None
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "information_schema" in sql or "pg_tables" in sql or "sys.tables" in sql:
            self._rows = [(t,) for t in self.tables]
            self.description = [("table_name",)]
        else:
            # SELECT * FROM <quoted table> — find which table was asked for.
            table = next(t for t in self.rows_by_table if t in sql)
            cols, rows = self.rows_by_table[table]
            self.description = [(c,) for c in cols]
            self._rows = rows
        return self

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, tables, rows_by_table):
        self.cursor_obj = _FakeCursor(tables, rows_by_table)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _mock():
    return _FakeConnection(
        ["customers", "orders"],
        {"customers": (["id", "name", "city"],
                       [("C1", "Aarav", "Delhi"),
                        ("C2", "  ", "Patna"),      # blank -> NaN
                        ("C3", "Priya", "")]),     # blank -> NaN
         "orders": (["id", "total"], [("O1", 99.5)])})


def test_mock_list_tables():
    for engine_name in ("mysql", "postgres", "sqlserver", "PostgreSQL", "sql server"):
        mock = _mock()
        tables = feat_db.list_tables(engine_name, database="shop", connector=mock)
        assert tables == ["customers", "orders"], (engine_name, tables)
        sql = mock.cursor_obj.executed[0][0]
        print(f"list_tables {engine_name}: {sql[:70]}...")
    print("mock list_tables OK (all three engines)")


def test_mock_load_table():
    mock = _mock()
    df = feat_db.load_table("mysql", database="shop", table="customers",
                            connector=mock)
    assert list(df.columns) == ["id", "name", "city"]
    assert len(df) == 3
    # Same empty-string -> NaN normalisation as engine.load_file.
    assert pd.isna(df.loc[1, "name"]), df
    assert pd.isna(df.loc[2, "city"]), df
    assert df.loc[0, "name"] == "Aarav"
    # Quoting differs per engine and must not break the query.
    mock_pg = _mock()
    feat_db.load_table("postgres", database="shop", table="customers",
                       connector=mock_pg)
    assert '"' in mock_pg.cursor_obj.executed[0][0]
    mock_ms = _mock()
    feat_db.load_table("sqlserver", database="shop", table="customers",
                       connector=mock_ms)
    assert "[" in mock_ms.cursor_obj.executed[0][0]
    mock_ms2 = _mock()
    df_lim = feat_db.load_table("sqlserver", database="shop", table="orders",
                                connector=mock_ms2, limit=10)
    assert "TOP 10" in mock_ms2.cursor_obj.executed[0][0]
    assert len(df_lim) == 1
    print("mock load_table OK (normalisation + quoting + TOP limit)")


def test_load_table_errors():
    try:
        feat_db.load_table("mysql", database="shop", table=None, connector=_mock())
    except ValueError as e:
        assert "No table name" in str(e)
    else:
        raise AssertionError("expected ValueError for missing table")
    try:
        feat_db.list_tables("oracle", connector=_mock())
    except ValueError as e:
        assert "Unknown database engine" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown engine")
    print("load_table error paths OK")


if __name__ == "__main__":
    test_wheels_present_and_tagged()
    test_wheel_contents_pe64()
    test_mysql_connector_imports()
    test_driver_status_shape()
    test_refused_connection_clean_error()
    test_unknown_engine_and_missing_driver()
    test_mock_list_tables()
    test_mock_load_table()
    test_load_table_errors()
    print("ALL FEAT_DB TESTS PASSED")
