"""CacheIQ Database Connection & Pool Management.

Uses psycopg 3 with psycopg_pool and automatic pgvector registration.
"""

import atexit
from contextlib import contextmanager
from typing import Generator, Optional
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from backend.app import config

_pool: Optional[ConnectionPool] = None


def _configure_connection(conn: psycopg.Connection) -> None:
    """Register pgvector and set dictionary row factory on each connection."""
    conn.row_factory = dict_row
    register_vector(conn)


def get_pool() -> ConnectionPool:
    """Retrieve or initialize the global psycopg ConnectionPool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=config.DATABASE_URL,
            min_size=2,
            max_size=10,
            configure=_configure_connection,
            open=True,
        )
    return _pool


def close_pool() -> None:
    """Close the connection pool cleanly on shutdown."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:
            pass
        _pool = None


atexit.register(close_pool)


@contextmanager
def get_db() -> Generator[psycopg.Connection, None, None]:
    """Context manager acquiring a managed connection from the pool."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn

