#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Check tenants table structure
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'tenants'
    ORDER BY ordinal_position
""")

print("Tenants table columns:")
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

print()

# Check communication_queue table structure
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'communication_queue'
    ORDER BY ordinal_position
""")

print("Communication_queue table columns:")
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

cur.close()
conn.close()
