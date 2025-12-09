#!/usr/bin/env python3
"""
Test script for AI-generated email content.

This script tests the AI content generator without actually sending emails.
It shows what content would be generated for different event types.
"""

import os
from dotenv import load_dotenv
load_dotenv('.env.local')

# Verify DeepSeek API key is set
api_key = os.getenv('DEEPSEEK_API_KEY')
if not api_key:
    print("=" * 70)
    print("ERROR: DEEPSEEK_API_KEY not set")
    print("=" * 70)
    print()
    print("Please add your DeepSeek API key to .env.local:")
    print("  DEEPSEEK_API_KEY=your_api_key_here")
    print()
    print("Optional settings:")
    print("  DEEPSEEK_BASE_URL=https://api.deepseek.com  (default)")
    print("  DEEPSEEK_MODEL=deepseek-chat  (default)")
    exit(1)

from src.providers.ai_content_generator import generate_email_content, EVENT_TYPE_PROMPTS

print("=" * 70)
print("AI Email Content Generator Test")
print("=" * 70)
print()
print("Available event types:")
for i, event_type in enumerate(EVENT_TYPE_PROMPTS.keys(), 1):
    print(f"  {i}. {event_type}")
print()

# Test cases
test_cases = [
    {
        'event_type': 'work_order_receipt',
        'message_params': {
            'customer_name': 'John Smith',
            'work_order_number': 'WO-12345',
            'equipment_type': 'Central AC Unit',
            'total': '450.00'
        },
        'recipient_address': {
            'email': 'john@example.com',
            'name': 'John Smith'
        }
    },
    {
        'event_type': 'service_reminder',
        'message_params': {
            'customer_name': 'Sarah Johnson',
            'model': 'Carrier Infinity 24ACC636A003',
            'last_service_date': 'December 2022'
        },
        'recipient_address': {
            'email': 'sarah@example.com',
            'name': 'Sarah Johnson'
        }
    },
    {
        'event_type': 'invoice_reminder',
        'message_params': {
            'first_name': 'Michael',
            'customer_name': 'Michael Brown',
            'invoice_id': 'INV-2024-789',
            'balance': '1,250.00',
            'days_past_due': '45'
        },
        'recipient_address': {
            'email': 'michael@example.com',
            'name': 'Michael Brown'
        }
    }
]

print("Testing AI content generation...")
print()

for test in test_cases:
    event_type = test['event_type']
    print("-" * 70)
    print(f"Event Type: {event_type}")
    print("-" * 70)
    print(f"Input params: {test['message_params']}")
    print()

    try:
        result = generate_email_content(
            event_type=event_type,
            message_params=test['message_params'],
            recipient_address=test['recipient_address'],
            company_name='Year Round Comfort'
        )

        print(f"SUBJECT: {result['subject']}")
        print()
        print("BODY:")
        print(result['body'])
        print()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        print()

print("=" * 70)
print("Test completed!")
print("=" * 70)
