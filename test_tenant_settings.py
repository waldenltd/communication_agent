#!/usr/bin/env python3
"""Test loading config from tenants table settings field."""

import os
from dotenv import load_dotenv
load_dotenv('.env.local')

os.environ['CENTRAL_DB_URL'] = os.getenv('CENTRAL_DB_URL')

from src.db.tenant_data_gateway import get_tenant_config
from src.providers.email_service import create_email_service

print("🧪 Testing Tenant Settings Configuration")
print("=" * 70)

# Test with the yearround tenant
tenant_id = 'yearround'

try:
    # Load config from tenants table
    config = get_tenant_config(tenant_id)

    print(f"✅ Loaded config for tenant: {tenant_id}")
    print()
    print("Configuration:")
    print("-" * 70)
    print(f"  Tenant ID:           {config['tenant_id']}")
    print(f"  Email Provider:      {config.get('email_provider', 'auto-detect')}")
    print(f"  Resend Key:          {config.get('resend_key', 'Not set')[:20]}...")
    print(f"  Resend From:         {config.get('resend_from', 'Not set')}")
    print(f"  SendGrid Key:        {config.get('sendgrid_key', 'Not set')}")
    print(f"  Quiet Hours:         {config.get('quiet_hours_start')} - {config.get('quiet_hours_end')}")
    print(f"  DMS Connection:      {config.get('dms_connection_string', 'Not set')[:50]}...")
    print()

    # Test email service creation
    service = create_email_service(config)
    print(f"✅ Email service created")
    print(f"  Provider:            {service.adapter.get_provider_name()}")
    print()

    print("=" * 70)
    print("✅ SUCCESS! Configuration is now loaded from tenants.settings")
    print()
    print("The Resend key is stored in:")
    print(f"  Table:  tenants")
    print(f"  Column: settings (JSONB)")
    print(f"  Path:   settings->>'resend_key'")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
