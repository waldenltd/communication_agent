#!/usr/bin/env python3
"""
Send a test email from the communication_queue table.

This script reads a pending communication from the queue and sends it via Resend.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv('.env.local')

os.environ['CENTRAL_DB_URL'] = os.getenv('CENTRAL_DB_URL')

from src.db.tenant_data_gateway import get_tenant_config
from src.providers.email_service import create_email_service
from src.providers.email_adapter import EmailAttachment
from src.utils.pdf_fetcher import fetch_work_order_pdf
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to database
DB_URL = os.getenv('CENTRAL_DB_URL')
conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("📧 Test Email Send from Communication Queue")
print("=" * 70)

# Get the first pending email from the queue
cur.execute("""
    SELECT *
    FROM communication_queue
    WHERE communication_type = 'email'
      AND status = 'pending'
    ORDER BY created_at ASC
    LIMIT 1
""")

queue_item = cur.fetchone()

if not queue_item:
    print("❌ No pending emails found in communication_queue")
    cur.close()
    conn.close()
    exit(1)

print(f"Found pending email:")
print("-" * 70)
print(f"  ID:              {queue_item['id']}")
print(f"  Event Type:      {queue_item['event_type']}")
print(f"  Recipient:       {queue_item['recipient_address']}")
print(f"  Subject:         {queue_item['subject']}")
print(f"  Message Params:  {queue_item['message_params']}")
print(f"  Tenant ID:       {queue_item['tenant_id']}")
print()

# Extract recipient email
recipient_data = queue_item['recipient_address']
if isinstance(recipient_data, str):
    recipient_data = json.loads(recipient_data)

to_email = recipient_data.get('email')

if not to_email:
    print("❌ No email address found in recipient_address")
    cur.close()
    conn.close()
    exit(1)

# Get tenant configuration
print(f"Loading configuration for tenant: {queue_item['tenant_id']}...")

# Map UUID tenant_id to our known tenant_id
# For now, we'll use 'yearround' as the tenant
tenant_id = 'yearround'

try:
    config = get_tenant_config(tenant_id)
    print(f"✅ Configuration loaded")
    print(f"  Email Provider:  {config.get('email_provider', 'auto-detect')}")
    print()

    # Create email service
    service = create_email_service(config)
    print(f"Using provider: {service.adapter.get_provider_name()}")
    print()

    # Build email body from template
    params = queue_item['message_params']
    customer_name = params.get('customer_name', 'Customer')
    work_order_number = params.get('work_order_number', 'N/A')

    email_body = f"""
Hello {customer_name},

This is a confirmation that we have received your work order.

Work Order Number: {work_order_number}

Thank you for your business!

---
This is a test email from the Communication Agent
"""

    # Fetch PDF attachment for work_order_receipt events
    attachments = None
    if queue_item['event_type'] == 'work_order_receipt':
        # Use work_order_number as the ID for the API call
        work_order_id = params.get('work_order_number')
        api_base_url = config.get('api_base_url')

        if work_order_id and api_base_url:
            print(f"Fetching PDF for work order: {work_order_id}...")
            pdf_content = fetch_work_order_pdf(work_order_id, api_base_url)

            if pdf_content:
                print(f"✅ PDF fetched successfully ({len(pdf_content)} bytes)")
                attachments = [EmailAttachment(
                    filename=f"work_order_{work_order_number}.pdf",
                    content=pdf_content,
                    content_type='application/pdf'
                )]
            else:
                print("⚠️  PDF fetch failed, sending email without attachment")
        else:
            if not work_order_id:
                print("⚠️  No work_order_number in message_params")
            if not api_base_url:
                print("⚠️  No api_base_url in tenant config")

    # Send the email
    print(f"Sending email to: {to_email}...")
    print(f"Subject: {queue_item['subject']}")
    if attachments:
        print(f"Attachments: {len(attachments)} file(s)")
    print()

    response = service.send_email(
        to=to_email,
        subject=queue_item['subject'],
        body=email_body,
        config=config,
        attachments=attachments
    )

    if response.success:
        print("=" * 70)
        print("✅ EMAIL SENT SUCCESSFULLY!")
        print("=" * 70)
        print(f"  Message ID:      {response.message_id}")
        print(f"  Status Code:     {response.status_code}")
        print(f"  Provider:        {service.adapter.get_provider_name()}")
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
        """, (response.message_id, json.dumps({'status': 'sent'}), queue_item['id']))
        conn.commit()

        print("✅ Queue item updated to 'sent' status")
        print()
        print("Check your inbox at:", to_email)

    else:
        print("=" * 70)
        print("❌ EMAIL SEND FAILED")
        print("=" * 70)
        print(f"  Error:           {response.error}")
        print()

        # Update the queue item with error
        cur.execute("""
            UPDATE communication_queue
            SET status = 'failed',
                error_details = %s::jsonb,
                retry_count = retry_count + 1,
                last_retry_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """, (json.dumps({'error': response.error}), queue_item['id']))
        conn.commit()

        print("❌ Queue item updated to 'failed' status")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
