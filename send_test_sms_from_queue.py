#!/usr/bin/env python3
"""
Send a test SMS from the communication_queue table.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv('.env.local')

os.environ['CENTRAL_DB_URL'] = os.getenv('CENTRAL_DB_URL')

from src.db.tenant_data_gateway import get_tenant_config
from src.providers.messaging import send_sms_via_twilio
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("📱 Test SMS Send from Communication Queue")
print("=" * 70)

# Get the first pending SMS from the queue
cur.execute("""
    SELECT *
    FROM communication_queue
    WHERE communication_type = 'sms'
      AND status = 'pending'
    ORDER BY created_at ASC
    LIMIT 1
""")

queue_item = cur.fetchone()

if not queue_item:
    print("❌ No pending SMS found in communication_queue")
    cur.close()
    conn.close()
    exit(1)

print(f"Found pending SMS:")
print("-" * 70)
print(f"  ID:              {queue_item['id']}")
print(f"  Event Type:      {queue_item['event_type']}")
print(f"  Recipient:       {queue_item['recipient_address']}")
print(f"  Message Params:  {queue_item['message_params']}")
print(f"  Tenant ID:       {queue_item['tenant_id']}")
print()

# Extract recipient phone
recipient_data = queue_item['recipient_address']
if isinstance(recipient_data, str):
    recipient_data = json.loads(recipient_data)

to_phone = recipient_data.get('phone')

if not to_phone:
    print("❌ No phone number found in recipient_address")
    cur.close()
    conn.close()
    exit(1)

# Format phone number (add +1 if needed)
if not to_phone.startswith('+'):
    # Remove any non-digit characters
    digits = ''.join(filter(str.isdigit, to_phone))
    if len(digits) == 10:
        to_phone = '+1' + digits
    elif len(digits) == 11 and digits.startswith('1'):
        to_phone = '+' + digits
    else:
        to_phone = '+' + digits

print(f"Formatted phone: {to_phone}")

# Get tenant configuration
print(f"Loading configuration for tenant...")

tenant_id = 'yearround'

try:
    config = get_tenant_config(tenant_id)
    print(f"✅ Configuration loaded")
    print(f"  Twilio SID:      {config.get('twilio_sid', 'NOT SET')[:20]}...")
    print(f"  From Number:     {config.get('twilio_from_number', 'NOT SET')}")
    print()

    # Build SMS body from message params
    params = queue_item['message_params']
    customer_name = params.get('customer_name', 'Customer')
    work_order_number = params.get('work_order_number', 'N/A')
    total = params.get('total', '0.00')
    equipment_type = params.get('equipment_type', 'equipment')

    sms_body = f"Hi {customer_name}, your {equipment_type} work order #{work_order_number} is ready. Total: ${total}. Thank you!"

    print(f"Sending SMS to: {to_phone}")
    print(f"Message: {sms_body}")
    print()

    # Send the SMS
    message_sid = send_sms_via_twilio(
        tenant_config=config,
        to=to_phone,
        body=sms_body
    )

    print("=" * 70)
    print("✅ SMS SENT SUCCESSFULLY!")
    print("=" * 70)
    print(f"  Message SID:     {message_sid}")
    print()

    # Update the queue item status
    cur.execute("""
        UPDATE communication_queue
        SET status = 'sent',
            sent_at = NOW(),
            external_message_id = %s,
            external_status = %s::jsonb,
            updated_at = NOW()
        WHERE id = %s
    """, (message_sid, json.dumps({'status': 'sent'}), queue_item['id']))
    conn.commit()

    print("✅ Queue item updated to 'sent' status")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

    # Update the queue item with error
    cur.execute("""
        UPDATE communication_queue
        SET status = 'failed',
            error_details = %s::jsonb,
            retry_count = retry_count + 1,
            last_retry_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """, (json.dumps({'error': str(e)}), queue_item['id']))
    conn.commit()

finally:
    cur.close()
    conn.close()
