import os
import queue
import sqlite3
import threading
from urllib.parse import parse_qsl, unquote, urlsplit


def _normalize_backend(backend):
    backend = str(backend).lower()
    aliases = {
        "sqlite3": "sqlite",
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "psycopg": "postgresql",
        "mysql.connector": "mysql",
        "mariadb": "mysql"
    }
    if backend not in aliases and backend not in ("sqlite", "mysql"):
        raise ValueError(
            "backend must be sqlite, postgresql, or mysql"
        )
    return aliases.get(backend, backend)


def _row_as_dict(row, description):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return {
        column[0]: value
        for column, value in zip(description or (), row)
    }


def _database_errors():
    error_types = [sqlite3.Error, OSError]
    try:
        import psycopg

        error_types.append(psycopg.Error)
    except ImportError:
        pass
    try:
        import mysql.connector

        error_types.append(mysql.connector.Error)
    except ImportError:
        pass
    try:
        import pymysql

        error_types.append(pymysql.MySQLError)
    except ImportError:
        pass
    return tuple(error_types)


class QueryResult:
    def __init__(self, cursor):
        self._cursor = cursor
        self._description = cursor.description
        self.columns = [column[0] for column in self._description or ()]
        self.rowcount = cursor.rowcount
        self.lastrowid = getattr(cursor, "lastrowid", None)

    def fetchone(self):
        return _row_as_dict(self._cursor.fetchone(), self._description)

    def fetchmany(self, size=1):
        return [
            _row_as_dict(row, self._description)
            for row in self._cursor.fetchmany(size)
        ]

    def fetchall(self):
        return [
            _row_as_dict(row, self._description)
            for row in self._cursor.fetchall()
        ]

    def scalar(self, default=None):
        row = self.fetchone()
        if row is None:
            return default
        if isinstance(row, dict):
            return next(iter(row.values()), default)
        return row[0] if row else default

    def close(self):
        self._cursor.close()

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class Database:
    def __init__(
            self,
            backend="sqlite",
            database=":memory:",
            host=None,
            port=None,
            user=None,
            password=None,
            timeout=10,
            autocommit=False,
            connect_now=True,
            **options
    ):
        self.backend = _normalize_backend(backend)
        self.database = database
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.autocommit = autocommit
        self.options = dict(options)
        self.connection = None
        self._lock = threading.RLock()
        self._transactions = []
        self._savepoint_number = 0
        if connect_now:
            self.connect()

    @classmethod
    def from_url(cls, url, **options):
        return open_database_url(url, **options)

    @property
    def is_connected(self):
        return self.connection is not None

    def connect(self):
        if self.connection is not None:
            return self

        if self.backend == "sqlite":
            database = self.database or ":memory:"
            if database != ":memory:" and not str(database).startswith("file:"):
                directory = os.path.dirname(os.path.abspath(database))
                os.makedirs(directory, exist_ok=True)
            self.connection = sqlite3.connect(
                database,
                timeout=self.timeout,
                isolation_level=None if self.autocommit else "DEFERRED",
                **self.options
            )
            self.connection.row_factory = sqlite3.Row
            return self

        if self.backend == "postgresql":
            parameters = {
                "dbname": self.database,
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "password": self.password,
                "connect_timeout": max(1, int(self.timeout)),
                "autocommit": self.autocommit
            }
            parameters.update(self.options)
            parameters = {
                name: value
                for name, value in parameters.items()
                if value is not None
            }
            try:
                import psycopg

                self.connection = psycopg.connect(**parameters)
            except ImportError:
                try:
                    import psycopg2
                except ImportError as error:
                    raise ImportError(
                        "PostgreSQL requires psycopg or psycopg2"
                    ) from error
                parameters.pop("autocommit", None)
                self.connection = psycopg2.connect(**parameters)
                self.connection.autocommit = self.autocommit
            return self

        parameters = {
            "host": self.host or "localhost",
            "port": self.port or 3306,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "connection_timeout": max(1, int(self.timeout)),
            "autocommit": self.autocommit
        }
        parameters.update(self.options)
        parameters = {
            name: value
            for name, value in parameters.items()
            if value is not None
        }
        try:
            import mysql.connector

            self.connection = mysql.connector.connect(**parameters)
        except ImportError:
            try:
                import pymysql
            except ImportError as error:
                raise ImportError(
                    "MySQL requires mysql-connector-python or PyMySQL"
                ) from error
            if "connection_timeout" in parameters:
                parameters["connect_timeout"] = parameters.pop(
                    "connection_timeout"
                )
            parameters.setdefault("charset", "utf8mb4")
            self.connection = pymysql.connect(**parameters)
        return self

    def _ensure_connected(self):
        if self.connection is None:
            raise RuntimeError("Database is not connected; call connect()")

    def execute(self, sql, parameters=None):
        self._ensure_connected()
        cursor = self.connection.cursor()
        try:
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            return QueryResult(cursor)
        except BaseException:
            cursor.close()
            raise

    def executemany(self, sql, parameter_sets):
        self._ensure_connected()
        cursor = self.connection.cursor()
        try:
            cursor.executemany(sql, parameter_sets)
            return QueryResult(cursor)
        except BaseException:
            cursor.close()
            raise

    def executescript(self, sql_script):
        if self.backend != "sqlite":
            raise NotImplementedError(
                "executescript is SQLite-only; use execute for other backends"
            )
        self._ensure_connected()
        cursor = self.connection.cursor()
        try:
            cursor.executescript(sql_script)
            return QueryResult(cursor)
        except BaseException:
            cursor.close()
            raise

    def query(self, sql, parameters=None):
        result = self.execute(sql, parameters)
        try:
            return result.fetchall()
        finally:
            result.close()

    def query_one(self, sql, parameters=None):
        result = self.execute(sql, parameters)
        try:
            return result.fetchone()
        finally:
            result.close()

    def scalar(self, sql, parameters=None, default=None):
        result = self.execute(sql, parameters)
        try:
            return result.scalar(default)
        finally:
            result.close()

    def begin(self):
        self._ensure_connected()
        with self._lock:
            active = self._has_active_transaction()
            if active:
                self._savepoint_number += 1
                name = f"facoh_savepoint_{self._savepoint_number}"
                cursor = self.connection.cursor()
                try:
                    cursor.execute(f"SAVEPOINT {name}")
                finally:
                    cursor.close()
            else:
                name = None
                cursor = self.connection.cursor()
                try:
                    statement = (
                        "START TRANSACTION"
                        if self.backend == "mysql"
                        else "BEGIN"
                    )
                    cursor.execute(statement)
                finally:
                    cursor.close()
            self._transactions.append(name)
        return self

    def _has_active_transaction(self):
        if self.backend == "sqlite":
            return self.connection.in_transaction
        if self.backend == "postgresql":
            status = getattr(
                getattr(getattr(self.connection, "info", None),
                        "transaction_status", None),
                "name",
                "IDLE"
            )
            return status not in ("IDLE", "UNKNOWN")
        return bool(getattr(self.connection, "in_transaction", False))

    def commit(self):
        self._ensure_connected()
        with self._lock:
            if not self._transactions:
                self.connection.commit()
                return
            savepoint = self._transactions.pop()
            if savepoint is None:
                self.connection.commit()
            else:
                cursor = self.connection.cursor()
                try:
                    cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
                finally:
                    cursor.close()

    def rollback(self):
        self._ensure_connected()
        with self._lock:
            if not self._transactions:
                self.connection.rollback()
                return
            savepoint = self._transactions.pop()
            if savepoint is None:
                self.connection.rollback()
            else:
                cursor = self.connection.cursor()
                try:
                    cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
                finally:
                    cursor.close()

    def transaction(self):
        return _Transaction(self)

    def tables(self, schema=None):
        if self.backend == "sqlite":
            return [
                row["name"]
                for row in self.query(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = ? AND name NOT LIKE ? ORDER BY name",
                    ("table", "sqlite_%")
                )
            ]
        if self.backend == "postgresql":
            return [
                row["table_name"]
                for row in self.query(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type = %s "
                    "ORDER BY table_name",
                    (schema or "public", "BASE TABLE")
                )
            ]
        schema = schema or self.database
        return [
            row["table_name"]
            for row in self.query(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = %s "
                "ORDER BY table_name",
                (schema, "BASE TABLE")
            )
        ]

    def columns(self, table, schema=None):
        if self.backend == "sqlite":
            escaped_table = str(table).replace('"', '""')
            return self.query(f'PRAGMA table_info("{escaped_table}")')
        if self.backend == "postgresql":
            return self.query(
                "SELECT column_name, data_type, is_nullable, "
                "column_default FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema or "public", table)
            )
        return self.query(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (schema or self.database, table)
        )

    def ping(self):
        return self.scalar("SELECT 1") == 1

    def backup(self, destination):
        if self.backend != "sqlite":
            raise NotImplementedError("backup is SQLite-only")
        self._ensure_connected()
        destination_connection = sqlite3.connect(destination)
        try:
            self.connection.backup(destination_connection)
        finally:
            destination_connection.close()
        return destination

    def close(self):
        if self.connection is None:
            return False
        try:
            self.connection.close()
        finally:
            self.connection = None
            self._transactions.clear()
        return True

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


class _Transaction:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self.database.begin()

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.database.commit()
        else:
            self.database.rollback()


def open_database_url(url, **options):
    parsed = urlsplit(url)
    query_options = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_options.update(options)
    scheme = parsed.scheme.lower()

    if scheme in ("sqlite", "sqlite3"):
        if parsed.netloc and parsed.netloc != "localhost":
            database = f"//{parsed.netloc}{unquote(parsed.path)}"
        elif url.startswith(("sqlite:////", "sqlite3:////")):
            database = unquote(parsed.path[1:])
        elif parsed.path in ("", "/", "/:memory:"):
            database = ":memory:"
        else:
            database = unquote(parsed.path.lstrip("/"))
        return Database(
            "sqlite",
            database,
            **query_options
        )

    backend = _normalize_backend(scheme)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Invalid database URL port") from error
    parameters = {
        "backend": backend,
        "database": unquote(parsed.path.lstrip("/")),
        "host": parsed.hostname,
        "port": port,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None
    }
    parameters.update(query_options)
    return Database(**parameters)


def open_sqlite(database=":memory:", **options):
    return Database("sqlite", database, **options)


def open_postgresql(database, host="localhost", user=None, password=None,
                    port=5432, **options):
    return Database(
        "postgresql", database, host, port, user, password, **options
    )


def open_mysql(database, host="localhost", user=None, password=None,
               port=3306, **options):
    return Database("mysql", database, host, port, user, password, **options)


class DatabasePool:
    def __init__(self, configuration, max_size=5, timeout=30):
        if not isinstance(configuration, dict):
            raise TypeError("configuration must be a dictionary")
        if not isinstance(max_size, int) or max_size < 1:
            raise ValueError("max_size must be a positive integer")
        self.configuration = dict(configuration)
        self.max_size = max_size
        self.timeout = timeout
        self._available = queue.LifoQueue(maxsize=max_size)
        self._all = set()
        self._borrowed = set()
        self._lock = threading.RLock()
        self._closed = False

    def acquire(self, timeout=None):
        wait_timeout = self.timeout if timeout is None else timeout
        with self._lock:
            if self._closed:
                raise RuntimeError("Database pool is closed")
            try:
                database = self._available.get_nowait()
            except queue.Empty:
                database = None
            if database is not None:
                self._borrowed.add(database)
                return database
            if len(self._all) < self.max_size:
                database = Database(**self.configuration)
                self._all.add(database)
                self._borrowed.add(database)
                return database

        try:
            database = self._available.get(timeout=wait_timeout)
        except queue.Empty as error:
            raise TimeoutError(
                "Timed out waiting for a database connection") from error
        with self._lock:
            if self._closed:
                database.close()
                self._all.discard(database)
                raise RuntimeError("Database pool is closed")
            self._borrowed.add(database)
        return database

    def release(self, database):
        with self._lock:
            if database not in self._borrowed:
                raise ValueError("connection was not acquired from this pool")
            self._borrowed.remove(database)
            if self._closed:
                self._all.discard(database)
                database.close()
                return
            try:
                database.ping()
            except _database_errors():
                database.close()
                self._all.discard(database)
                return
            self._available.put_nowait(database)

    def connection(self, timeout=None):
        return _PooledConnection(self, timeout)

    def close(self):
        with self._lock:
            if self._closed:
                return False
            self._closed = True
            while True:
                try:
                    database = self._available.get_nowait()
                except queue.Empty:
                    break
                database.close()
                self._all.discard(database)
        return True


class _PooledConnection:
    def __init__(self, pool, timeout):
        self.pool = pool
        self.timeout = timeout
        self.database = None

    def __enter__(self):
        self.database = self.pool.acquire(self.timeout)
        return self.database

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.database.commit()
            else:
                self.database.rollback()
        finally:
            self.pool.release(self.database)


FUNCTIONS = {
    "open_database_url": open_database_url,
    "open_sqlite": open_sqlite,
    "open_postgresql": open_postgresql,
    "open_mysql": open_mysql
}

OBJECTS = {
    "Database": Database,
    "DatabasePool": DatabasePool,
    "QueryResult": QueryResult
}
