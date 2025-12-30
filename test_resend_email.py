#!/usr/bin/env python3
"""Test sending email via Resend."""

import os
from dotenv import load_dotenv
load_dotenv('.env.local')

# Set environment variable for the app
os.environ['CENTRAL_DB_URL'] = os.getenv('CENTRAL_DB_URL')

from src.db.tenant_data_gateway import get_tenant_config
from src.providers.email_service import create_email_service

print("🧪 Testing Resend Email Send")
print("=" * 60)

# Get tenant configuration
tenant_id = 'default_tenant'
config = get_tenant_config(tenant_id)

print(f"Tenant: {tenant_id}")
print(f"Provider: {config.get('email_provider', 'auto-detect')}")
print(f"Resend Key: {config.get('resend_key')[:20]}...")
print()

# Create email service
service = create_email_service(config)
print(f"Using Provider: {service.adapter.get_provider_name()}")
print()

# Test email
test_email = input("Enter your email address to test: ").strip()

if test_email:
    print(f"\nSending test email to {test_email}...")

    response = service.send_email(
        to=test_email,
        subject='Test Email from Communication Agent',
        body='Hello! This is a test email sent via Resend adapter.',
        config=config
    )

    print()
    if response.success:
        print(f"✅ Email sent successfully!")
        print(f"   Message ID: {response.message_id}")
    else:
        print(f"❌ Email failed: {response.error}")
else:
    print("No email address provided. Skipping test.")
