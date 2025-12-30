#!/usr/bin/env python3
"""
Setup Resend configuration in development database.

This script adds the Resend API key to your tenant_configs table.
"""

import sys
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables from .env.local
load_dotenv('.env.local')

# Database connection from environment
DB_URL = os.getenv('CENTRAL_DB_URL', 'postgres://postgres:0Griswold@localhost:5432/dms_admin_db')

# Resend configuration
RESEND_KEY = 're_Qo2uF8Lz_NQHAuasWTXN9z8FkZW5veKhC'
RESEND_FROM = 'noreply@example.com'  # Change this to your domain

print("🔧 Setting up Resend configuration...")
print(f"Database: {DB_URL}")
print(f"Resend Key: {RESEND_KEY}")
print()

try:
    # Connect to database
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Add columns if they don't exist
    print("Step 1: Adding Resend columns to tenant_configs...")
    cur.execute("""
        ALTER TABLE tenant_configs
        ADD COLUMN IF NOT EXISTS email_provider VARCHAR(50),
        ADD COLUMN IF NOT EXISTS resend_key VARCHAR(255),
        ADD COLUMN IF NOT EXISTS resend_from VARCHAR(255)
    """)
    conn.commit()
    print("✓ Columns added/verified")
    print()

    # Step 2: Check existing tenants
    print("Step 2: Checking existing tenants...")
    cur.execute("SELECT tenant_id FROM tenant_configs")
    tenants = cur.fetchall()

    if not tenants:
        print("⚠️  No tenants found in tenant_configs table!")
        print("Would you like to create a test tenant? (y/n): ", end='')
        response = input().strip().lower()

        if response == 'y':
            tenant_id = input("Enter tenant ID (e.g., 'test_tenant'): ").strip()
            print(f"\nCreating tenant: {tenant_id}")
            cur.execute("""
                INSERT INTO tenant_configs (
                    tenant_id,
                    email_provider,
                    resend_key,
                    resend_from,
                    quiet_hours_start,
                    quiet_hours_end,
                    dms_connection_string
                ) VALUES (%s, 'resend', %s, %s, '21:00', '08:00', 'postgres://localhost/test')
            """, (tenant_id, RESEND_KEY, RESEND_FROM))
            conn.commit()
            print(f"✓ Created tenant '{tenant_id}' with Resend configuration")
        else:
            print("Exiting without changes.")
            sys.exit(0)
    else:
        print(f"Found {len(tenants)} tenant(s):")
        for i, tenant in enumerate(tenants, 1):
            print(f"  {i}. {tenant['tenant_id']}")
        print()

        # Step 3: Update tenants with Resend
        print("Step 3: Updating tenants with Resend configuration...")
        for tenant in tenants:
            tenant_id = tenant['tenant_id']
            cur.execute("""
                UPDATE tenant_configs
                SET email_provider = 'resend',
                    resend_key = %s,
                    resend_from = %s
                WHERE tenant_id = %s
            """, (RESEND_KEY, RESEND_FROM, tenant_id))
            print(f"  ✓ Updated tenant: {tenant_id}")

        conn.commit()

    # Step 4: Verify configuration
    print()
    print("Step 4: Verifying configuration...")
    cur.execute("""
        SELECT
            tenant_id,
            email_provider,
            CASE
                WHEN resend_key IS NOT NULL THEN 'Configured ✓'
                ELSE 'Not configured ✗'
            END as resend_status,
            resend_from,
            CASE
                WHEN sendgrid_key IS NOT NULL THEN 'Available'
                ELSE 'Not configured'
            END as sendgrid_status
        FROM tenant_configs
    """)

    results = cur.fetchall()
    print()
    print("=" * 80)
    print("TENANT CONFIGURATION SUMMARY")
    print("=" * 80)
    for row in results:
        print(f"Tenant ID:      {row['tenant_id']}")
        print(f"Email Provider: {row['email_provider']}")
        print(f"Resend:         {row['resend_status']}")
        print(f"Resend From:    {row['resend_from']}")
        print(f"SendGrid:       {row['sendgrid_status']}")
        print("-" * 80)

    print()
    print("✅ Setup complete! All tenants now configured to use Resend.")
    print()
    print("Next steps:")
    print("1. Test sending an email using the Resend adapter")
    print("2. Check logs to confirm Resend is being used")
    print()

    cur.close()
    conn.close()

except psycopg2.OperationalError as e:
    print(f"❌ Database connection failed: {e}")
    print()
    print("Possible issues:")
    print("1. PostgreSQL is not running")
    print("2. Database 'dms_communications' doesn't exist")
    print("3. User 'dms_agent' doesn't have permissions")
    print()
    print("To create the database:")
    print("  createdb dms_communications")
    print()
    sys.exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
