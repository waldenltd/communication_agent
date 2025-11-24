import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from src import config
from src import logger


# Create connection pool
connection_pool = pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=25,
    dsn=config.CENTRAL_DB_URL
)


def query(text, params=None):
    """Execute a query and return results as list of dicts."""
    conn = connection_pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(text, params or [])
            if cursor.description:
                return cursor.fetchall()
            conn.commit()
            return []
    finally:
        connection_pool.putconn(conn)


@contextmanager
def with_transaction():
    """Context manager for database transactions."""
    conn = connection_pool.getconn()
    try:
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        class TransactionClient:
            def __init__(self, cursor, conn):
                self.cursor = cursor
                self.conn = conn

            def query(self, text, params=None):
                self.cursor.execute(text, params or [])
                if self.cursor.description:
                    return self.cursor.fetchall()
                return []

        client = TransactionClient(cursor, conn)
        yield client

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        connection_pool.putconn(conn)


def shutdown_pool():
    """Close all connections in the pool."""
    try:
        connection_pool.closeall()
    except Exception as e:
        logger.error('Failed to close central DB pool', err=e)
