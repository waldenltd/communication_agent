#!/usr/bin/env python3
"""
Set API base URL for tenant configuration.
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("🔧 Setting API Base URL for tenant")
print("=" * 70)

tenant_id = 'yearround'
api_base_url = 'http://localhost:5000'

# Get current tenant settings
cur.execute("""
    SELECT tenant_id, settings
    FROM tenants
    WHERE tenant_id = %s
""", (tenant_id,))

tenant = cur.fetchone()

if not tenant:
    print(f"❌ Tenant '{tenant_id}' not found")
    cur.close()
    conn.close()
    sys.exit(1)

settings = tenant['settings'] if tenant['settings'] else {}

print(f"Tenant: {tenant_id}")
print(f"Setting api_base_url to: {api_base_url}")
print()

# Add api_base_url to settings
settings['api_base_url'] = api_base_url

# Update the settings
cur.execute("""
    UPDATE tenants
    SET settings = %s::jsonb,
        updated_at = NOW()
    WHERE tenant_id = %s
""", (psycopg2.extras.Json(settings), tenant_id))

conn.commit()

print("✅ Configuration updated!")
print()

# Verify the update
cur.execute("""
    SELECT settings
    FROM tenants
    WHERE tenant_id = %s
""", (tenant_id,))

updated = cur.fetchone()
print("Current settings:")
print("-" * 70)
for key, value in updated['settings'].items():
    if 'key' in key.lower() or 'token' in key.lower() or 'password' in key.lower():
        print(f"  {key}: ***")
    else:
        print(f"  {key}: {value}")

cur.close()
conn.close()
