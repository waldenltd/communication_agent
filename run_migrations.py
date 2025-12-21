#!/usr/bin/env python
"""
Simple migration runner for communication_agent database.

Usage:
    python migrations/run_migrations.py

Requires CENTRAL_DB_URL environment variable or .env.local file.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from dotenv import load_dotenv

# Load environment variables
env_local = Path(__file__).parent.parent / '.env.local'
if env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv()


def get_db_url():
    """Get database URL from environment."""
    url = os.getenv('CENTRAL_DB_URL')
    if not url:
        print("Error: CENTRAL_DB_URL environment variable not set")
        print("Set it in .env.local or as an environment variable")
        sys.exit(1)
    return url


def run_migration(cursor, migration_file: Path):
    """Run a single migration file."""
    print(f"Running migration: {migration_file.name}")

    sql = migration_file.read_text()
    cursor.execute(sql)

    print(f"  ✓ {migration_file.name} completed")


def main():
    """Run all migrations in order."""
    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("No migration files found")
        return

    print(f"Found {len(migration_files)} migration(s)")
    print("-" * 40)

    db_url = get_db_url()

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cursor = conn.cursor()

        for migration_file in migration_files:
            run_migration(cursor, migration_file)

        conn.commit()
        print("-" * 40)
        print("All migrations completed successfully!")

    except psycopg2.Error as e:
        print(f"\nError running migrations: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == '__main__':
    main()
