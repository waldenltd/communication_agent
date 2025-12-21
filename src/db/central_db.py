import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from src import config
from src import logger


# Create connection pool
connection_pool = ConnectionPool(
    conninfo=config.CENTRAL_DB_URL,
    min_size=1,
    max_size=25
)


def query(text, params=None):
    """Execute a query and return results as list of dicts."""
    with connection_pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cursor:
            cursor.execute(text, params or [])
            if cursor.description:
                return cursor.fetchall()
            conn.commit()
            return []


def execute(text, params=None):
    """Execute a statement (INSERT, UPDATE, DELETE) and commit."""
    with connection_pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(text, params or [])
            conn.commit()
            return cursor.rowcount


@contextmanager
def with_transaction():
    """Context manager for database transactions."""
    with connection_pool.connection() as conn:
        conn.row_factory = dict_row
        conn.autocommit = False
        cursor = conn.cursor()

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
        try:
            yield client
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()


def shutdown_pool():
    """Close all connections in the pool."""
    try:
        connection_pool.close()
    except Exception as e:
        logger.error('Failed to close central DB pool', err=e)
