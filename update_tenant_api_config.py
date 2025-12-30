#!/usr/bin/env python3
"""
Update tenant configuration with API base URL.

This script updates the tenants.settings JSONB field to include
the api_base_url needed for fetching PDFs.
"""

import os
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("🔧 Update Tenant API Configuration")
print("=" * 70)

# Configuration to add
tenant_id = 'yearround'
api_base_url = input("Enter the API base URL (e.g., https://api.example.com): ").strip()

if not api_base_url:
    print("❌ API base URL is required")
    cur.close()
    conn.close()
    exit(1)

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
    exit(1)

print(f"\nCurrent settings for tenant '{tenant_id}':")
print("-" * 70)

settings = tenant['settings'] if tenant['settings'] else {}
for key, value in settings.items():
    # Don't print sensitive values
    if 'key' in key.lower() or 'token' in key.lower() or 'password' in key.lower():
        print(f"  {key}: ***")
    else:
        print(f"  {key}: {value}")

# Add api_base_url to settings
settings['api_base_url'] = api_base_url

print(f"\nUpdating settings with:")
print(f"  api_base_url: {api_base_url}")
print()

# Confirm
confirm = input("Proceed with update? (yes/no): ").strip().lower()

if confirm != 'yes':
    print("❌ Update cancelled")
    cur.close()
    conn.close()
    exit(0)

# Update the settings
cur.execute("""
    UPDATE tenants
    SET settings = %s::jsonb,
        updated_at = NOW()
    WHERE tenant_id = %s
""", (psycopg2.extras.Json(settings), tenant_id))

conn.commit()

print("=" * 70)
print("✅ TENANT CONFIGURATION UPDATED!")
print("=" * 70)
print(f"  Tenant ID:     {tenant_id}")
print(f"  API Base URL:  {api_base_url}")
print()

# Verify the update
cur.execute("""
    SELECT settings
    FROM tenants
    WHERE tenant_id = %s
""", (tenant_id,))

updated = cur.fetchone()
print("Updated settings:")
print("-" * 70)
for key, value in updated['settings'].items():
    if 'key' in key.lower() or 'token' in key.lower() or 'password' in key.lower():
        print(f"  {key}: ***")
    else:
        print(f"  {key}: {value}")

print()
print("✅ Configuration ready for PDF attachments!")

cur.close()
conn.close()
