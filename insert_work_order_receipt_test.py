#!/usr/bin/env python3
"""
Insert a test work_order_receipt communication into the queue.

This script creates a test record with all the necessary fields for
testing PDF attachment functionality.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
from psycopg2.extras import RealDictCursor
import uuid

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("📧 Insert Work Order Receipt Test Communication")
print("=" * 70)

# Get tenant UUID
cur.execute("""
    SELECT id, tenant_id
    FROM tenants
    WHERE tenant_id = 'yearround'
""")

tenant = cur.fetchone()

if not tenant:
    print("❌ Tenant 'yearround' not found")
    cur.close()
    conn.close()
    exit(1)

tenant_uuid = tenant['id']
print(f"Found tenant: {tenant['tenant_id']} (UUID: {tenant_uuid})")
print()

# Test data
work_order_id = input("Enter work order ID (e.g., 12345): ").strip()
work_order_number = input("Enter work order number (e.g., WO-151371): ").strip()
customer_name = input("Enter customer name (e.g., John Doe): ").strip()
customer_email = input("Enter customer email: ").strip()

if not all([work_order_id, work_order_number, customer_name, customer_email]):
    print("❌ All fields are required")
    cur.close()
    conn.close()
    exit(1)

# Build message params
message_params = {
    'work_order_id': work_order_id,
    'work_order_number': work_order_number,
    'customer_name': customer_name
}

# Build recipient address
recipient_address = {
    'email': customer_email,
    'name': customer_name
}

# Insert the communication record
print()
print("Inserting communication record...")
print("-" * 70)
print(f"  Event Type:       work_order_receipt")
print(f"  Recipient:        {customer_email}")
print(f"  Work Order ID:    {work_order_id}")
print(f"  Work Order #:     {work_order_number}")
print(f"  Customer:         {customer_name}")
print()

cur.execute("""
    INSERT INTO communication_queue (
        tenant_id,
        event_type,
        communication_type,
        recipient_address,
        subject,
        message_params,
        status,
        created_at,
        updated_at
    ) VALUES (
        %s,
        'work_order_receipt',
        'email',
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
    json.dumps(recipient_address),
    f"Work Order #{work_order_number} Receipt",
    json.dumps(message_params)
))

result = cur.fetchone()
conn.commit()

print("=" * 70)
print("✅ TEST COMMUNICATION INSERTED!")
print("=" * 70)
print(f"  Queue ID:         {result['id']}")
print(f"  Created:          {result['created_at']}")
print()
print("Next steps:")
print("1. Make sure api_base_url is configured in tenant settings")
print("2. Run: python send_test_email_from_queue.py")
print()

cur.close()
conn.close()
