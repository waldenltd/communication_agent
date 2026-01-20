#!/usr/bin/env python3
"""
Send a direct test SMS to a specific phone number.

Usage: python send_direct_test_sms.py
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env')

os.environ['CENTRAL_DB_URL'] = os.getenv('CENTRAL_DB_URL', '')

from src.db.tenant_data_gateway import get_tenant_config
from src.providers.messaging import send_sms_via_twilio

# Configuration
TO_PHONE = '+18606803763'  # Target phone number
FROM_NUMBER = '+18445262128'  # Override from number
TENANT_ID = 'yearround'     # Tenant with Twilio credentials
MESSAGE = 'Test message from Communication Agent. If you received this, SMS is working!'

print("=" * 60)
print("Direct SMS Test")
print("=" * 60)
print(f"To:      {TO_PHONE}")
print(f"Tenant:  {TENANT_ID}")
print(f"Message: {MESSAGE}")
print()

try:
    # Load tenant config with Twilio credentials
    config = get_tenant_config(TENANT_ID)

    twilio_sid = config.get('twilio_sid')
    twilio_from = config.get('twilio_from_number')

    if not twilio_sid:
        print("ERROR: No twilio_sid found in tenant config")
        print("Available config keys:", list(config.keys()))
        exit(1)

    if not twilio_from:
        print("ERROR: No twilio_from_number found in tenant config")
        exit(1)

    print(f"Twilio SID: {twilio_sid[:10]}...")
    print(f"Config From: {twilio_from}")
    print(f"Using From:  {FROM_NUMBER}")
    print()
    print("Sending...")

    # Override the from number
    config['twilio_from_number'] = FROM_NUMBER

    # Send the SMS
    message_sid = send_sms_via_twilio(
        tenant_config=config,
        to=TO_PHONE,
        body=MESSAGE
    )

    print()
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"Message SID: {message_sid}")
    print()
    print("Check your phone for the test message.")

except Exception as e:
    print()
    print("=" * 60)
    print("FAILED")
    print("=" * 60)
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
