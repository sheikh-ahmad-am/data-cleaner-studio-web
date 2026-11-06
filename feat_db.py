"""Data Cleaner Studio — live database connections (v1.4, Group A).

MySQL + PostgreSQL + SQL Server (best-effort) against the portable build's
embedded Windows Python 3.12.7. Drivers are wheels in
hidden_files/wheels/ — install them into the embedded site-packages and
db_driver_status() flips to True.

  mysql-connector-python 26.10.0  (pure Python, py2.py3-none-any)
  psycopg2-binary 2.9.13          (cp312-win_amd64, precompiled)
  pymssql 2.4.6                   (cp312-win_amd64, precompiled, FreeTDS
                                   statically linked into the .pyd files)

No passwords are saved anywhere: connection params arrive as a plain dict
and live only for the duration of one call.

What was NOT live-tested (no database server exists on this machine):
connecting to a real MySQL / PostgreSQL / SQL Server. What WAS tested:
driver import/content checks, refused-connection handling against a closed
local port, and the full connect -> list-tables -> load-table path against
a mock DBAPI connector object (see tests/test_feat_db.py).
"""

import importlib.util

import numpy as np
import pandas as pd

# engine key -> (importable module, pip package, default port)
DRIVERS = {
    "mysql": ("mysql.connector", "mysql-connector-python", 3306),
    "postgres": ("psycopg2", "psycopg2-binary", 5432),
    "sqlserver": ("pymssql", "pymssql", 1433),
}

# Friendly aliases the UI / callers may use.
_ALIASES = {
    "mysql": "mysql",
    "mariadb": "mysql",
    "postgresql": "postgres",
    "postgres": "postgres",
    "psql": "postgres",
    "sqlserver": "sqlserver",
    "sql server": "sqlserver",
    "mssql": "sqlserver",
}

_DISPLAY = {"mysql": "MySQL", "postgres": "PostgreSQL", "sqlserver": "SQL Server"}

CONNECT_TIMEOUT = 10  # seconds; a dead host must fail fast, not hang the UI


def normalize_engine(engine: str) -> str:
    """'PostgreSQL' / 'sql server' / 'mssql' -> canonical key, or ''."""
    if not engine:
        return ""
    return _ALIASES.get(str(engine).strip().lower(), "")


def db_driver_status() -> dict:
    """{"mysql": bool, "postgres": bool, "sqlserver": bool} — import probes.

    True means the driver module imports in THIS Python. In the portable
    build that is the embedded 3.12.7 once the wheels are installed.
    """
    status = {}
    for key, (module, _pkg, _port) in DRIVERS.items():
        try:
            status[key] = importlib.util.find_spec(module) is not None
        except (ModuleNotFoundError, ValueError):
            status[key] = False
    return status


def _friendly_error(engine_key: str, params: dict, exc: Exception) -> str:
    """One plain line for the user — never a traceback, never credentials."""
    host = params.get("host") or "localhost"
    port = params.get("port") or DRIVERS[engine_key][2]
    detail = str(exc).strip().splitlines()
    detail = detail[0] if detail else exc.__class__.__name__
    if len(detail) > 200:
        detail = detail[:197] + "..."
    return (f"Could not connect to {_DISPLAY[engine_key]} at {host}:{port} — "
            f"{detail}")


def _connect(engine_key: str, params: dict):
    """Open a DBAPI connection. Raises on failure (callers turn it into a
    plain message). Params: host, port, user, password, database."""
    host = (params.get("host") or "localhost").strip()
    port = int(params.get("port") or DRIVERS[engine_key][2])
    user = params.get("user") or params.get("username") or ""
    password = params.get("password") or ""
    database = (params.get("database") or "").strip()

    if engine_key == "mysql":
        import mysql.connector
        return mysql.connector.connect(
            host=host, port=port, user=user, password=password,
            database=database or None,
            connection_timeout=CONNECT_TIMEOUT)
    if engine_key == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=host, port=port, user=user, password=password,
            dbname=database or None,
            connect_timeout=CONNECT_TIMEOUT)
    if engine_key == "sqlserver":
        import pymssql
        return pymssql.connect(
            server=host, port=port, user=user, password=password,
            database=database or None,
            timeout=CONNECT_TIMEOUT, login_timeout=CONNECT_TIMEOUT)
    raise ValueError(f"Unknown database engine: {engine_key!r}")


def _get_connection(engine, params: dict, connector=None):
    """Real connection, or the injected mock connector (tests only)."""
    if connector is not None:
        return connector
    key = normalize_engine(engine)
    if not key:
        raise ValueError(
            f"Unknown database engine: {engine!r} "
            f"(use MySQL, PostgreSQL or SQL Server)")
    if not db_driver_status()[key]:
        _pkg = DRIVERS[key][1]
        raise ImportError(
            f"The {_DISPLAY[key]} driver ({_pkg}) is not installed in "
            f"this build — install hidden_files/wheels/ into the "
            f"embedded Python first.")
    return _connect(key, params or {})


def test_connection(engine, host=None, port=None, user=None, password=None,
                    database=None, params=None) -> tuple:
    """(ok, message). Refused / unreachable / wrong-password all come back
    as a plain one-line message — never a traceback."""
    params = dict(params or {})
    for k, v in (("host", host), ("port", port), ("user", user),
                 ("password", password), ("database", database)):
        if v is not None:
            params[k] = v
    key = normalize_engine(engine)
    if not key:
        return False, (f"Unknown database engine: {engine!r} "
                       f"(use MySQL, PostgreSQL or SQL Server)")
    if not db_driver_status()[key]:
        return False, (f"The {_DISPLAY[key]} driver "
                       f"({DRIVERS[key][1]}) is not installed in this "
                       f"portable build, so a live connection cannot be "
                       f"tested yet. Install the wheels from "
                       f"hidden_files/wheels/ into the embedded Python.")
    try:
        con = _connect(key, params)
    except Exception as exc:  # noqa: BLE001 - surfaced as a message, by design
        return False, _friendly_error(key, params, exc)
    try:
        con.close()
    except Exception:  # noqa: BLE001 - already connected; close failure is noise
        pass
    host = (params.get("host") or "localhost").strip()
    db = (params.get("database") or "").strip()
    where = f"{host} database {db!r}" if db else f"{host}"
    return True, f"Connected to {_DISPLAY[key]} at {where}."


def _list_tables_sql(engine_key: str, database: str) -> tuple:
    """(sql, params) returning one table-name column, per engine."""
    if engine_key == "mysql":
        return ("SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s ORDER BY table_name", (database,))
    if engine_key == "postgres":
        return ("SELECT tablename FROM pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY tablename", ())
    return ("SELECT name FROM sys.tables ORDER BY name", ())


def _quote_table(engine_key: str, table: str) -> str:
    if engine_key == "mysql":
        return f"`{table.replace('`', '``')}`"
    if engine_key == "postgres":
        return '"' + table.replace('"', '""') + '"'
    return "[" + table.replace("]", "]]") + "]"


def list_tables(engine, host=None, port=None, user=None, password=None,
                database=None, params=None, connector=None) -> list:
    """Table names in the database, sorted. Raises ValueError / ImportError /
    the driver's connection error on failure — callers show str(e)."""
    params = dict(params or {})
    for k, v in (("host", host), ("port", port), ("user", user),
                 ("password", password), ("database", database)):
        if v is not None:
            params[k] = v
    key = normalize_engine(engine)
    if not key:
        raise ValueError(f"Unknown database engine: {engine!r}")
    con = _get_connection(key, params, connector=connector)
    try:
        cur = con.cursor()
        try:
            sql, qparams = _list_tables_sql(key, params.get("database") or "")
            cur.execute(sql, qparams) if qparams else cur.execute(sql)
            return [str(r[0]) for r in cur.fetchall()]
        finally:
            cur.close()
    finally:
        if connector is None:
            con.close()


def load_table(engine, host=None, port=None, user=None, password=None,
               database=None, table=None, params=None, connector=None,
               limit: int | None = None) -> pd.DataFrame:
    """Load one whole table (or its first `limit` rows) into a DataFrame.

    Empty / whitespace-only strings become NaN, exactly like
    engine.load_file, so a database table behaves like a CSV.
    """
    params = dict(params or {})
    for k, v in (("host", host), ("port", port), ("user", user),
                 ("password", password), ("database", database)):
        if v is not None:
            params[k] = v
    if table is None:
        table = params.get("table")
    if not table:
        raise ValueError("No table name given.")
    key = normalize_engine(engine)
    if not key:
        raise ValueError(f"Unknown database engine: {engine!r}")
    con = _get_connection(key, params, connector=connector)
    try:
        cur = con.cursor()
        try:
            sql = f"SELECT * FROM {_quote_table(key, str(table))}"
            if limit:
                if key == "sqlserver":
                    sql = (f"SELECT TOP {int(limit)} * FROM "
                           f"{_quote_table(key, str(table))}")
                else:
                    sql += f" LIMIT {int(limit)}"
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
        finally:
            cur.close()
    finally:
        if connector is None:
            con.close()
    df = pd.DataFrame(rows, columns=cols)
    return df.replace(r"^\s*$", np.nan, regex=True)
