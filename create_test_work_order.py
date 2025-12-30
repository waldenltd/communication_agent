#!/usr/bin/env python3
"""
Create a test work_order_receipt communication.
"""

import os
import json
import uuid
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("📧 Creating Test Work Order Receipt Communication")
print("=" * 70)

# Get tenant UUID from existing queue records
# (communication_queue uses UUID for tenant_id, not the string tenant_id)
cur.execute("""
    SELECT DISTINCT tenant_id
    FROM communication_queue
    LIMIT 1
""")

result = cur.fetchone()

if not result:
    print("❌ No existing queue records found to get tenant UUID")
    cur.close()
    conn.close()
    exit(1)

tenant_uuid = result['tenant_id']
print(f"Tenant UUID: {tenant_uuid}")
print()

# Test data
work_order_number = "12345"  # This is the work order number used in the API call
customer_name = "Test Customer"
customer_email = "scottgriswold@waldenltd.com"

# Build message params
message_params = {
    'work_order_number': work_order_number,
    'customer_name': customer_name
}

# Build recipient address
recipient_address = {
    'email': customer_email,
    'name': customer_name
}

print("Test Data:")
print("-" * 70)
print(f"  Event Type:       work_order_receipt")
print(f"  Recipient:        {customer_email}")
print(f"  Work Order #:     {work_order_number}")
print(f"  Customer:         {customer_name}")
print()

# Insert the communication record
event_id = str(uuid.uuid4())
recipient_id = str(uuid.uuid4())

cur.execute("""
    INSERT INTO communication_queue (
        tenant_id,
        event_id,
        event_type,
        event_timestamp,
        communication_type,
        template_id,
        recipient_type,
        recipient_id,
        recipient_address,
        subject,
        message_params,
        status,
        created_at,
        updated_at
    ) VALUES (
        %s,
        %s,
        'work_order_receipt',
        NOW(),
        'email',
        'work_order_receipt',
        'customer',
        %s,
        %s::jsonb,
        %s,
        %s::jsonb,
        'pending',
        NOW(),
        NOW()
    )
    RETURNING id, created_at
""", (
    tenant_uuid,
    event_id,
    recipient_id,
    json.dumps(recipient_address),
    f"Work Order #{work_order_number} Receipt",
    json.dumps(message_params)
))

result = cur.fetchone()
conn.commit()

print("=" * 70)
print("✅ TEST COMMUNICATION CREATED!")
print("=" * 70)
print(f"  Queue ID:         {result['id']}")
print(f"  Created:          {result['created_at']}")
print()
print("Next: Run python send_test_email_from_queue.py")
print()

cur.close()
conn.close()
