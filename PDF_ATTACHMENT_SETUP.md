# PDF Attachment Setup Guide

This guide explains how to set up and test PDF attachments for work_order_receipt emails.

## Overview

The communication agent now supports attaching PDFs to emails. For `work_order_receipt` event types, the system will:

1. Extract the `work_order_id` from `message_params`
2. Call the API endpoint: `/api/serviceorder/{workOrderId}/pdf`
3. Attach the PDF to the email with filename: `work_order_{number}.pdf`
4. Send the email via Resend (or other configured provider)

## Architecture

### Components Added

1. **Email Attachment Support**
   - `src/providers/email_adapter.py` - Added `EmailAttachment` class
   - `src/providers/resend_adapter.py` - Added base64 attachment encoding
   - `src/providers/email_service.py` - Added `attachments` parameter

2. **PDF Fetcher**
   - `src/utils/pdf_fetcher.py` - Utility to fetch PDFs from API
   - Handles API calls, error handling, and logging

3. **Configuration**
   - `src/db/tenant_data_gateway.py` - Added `api_base_url` to tenant config
   - Stored in `tenants.settings` JSONB field as `api_base_url`

## Setup Instructions

### Step 1: Configure API Base URL

Run the configuration update script:

```bash
python update_tenant_api_config.py
```

When prompted, enter your API base URL (e.g., `https://api.example.com` or `http://localhost:3000`).

This will update the tenant configuration in the database.

### Step 2: Insert Test Data

Insert a test work_order_receipt communication:

```bash
python insert_work_order_receipt_test.py
```

Provide the following when prompted:
- **Work order ID**: The ID used in the API call (e.g., `12345`)
- **Work order number**: Display number for the customer (e.g., `WO-151371`)
- **Customer name**: Recipient name (e.g., `John Doe`)
- **Customer email**: Where to send the test email

### Step 3: Send the Test Email

Run the email sender:

```bash
python send_test_email_from_queue.py
```

This script will:
1. Find the pending work_order_receipt communication
2. Fetch the PDF from the API using the configured base URL
3. Attach the PDF to the email
4. Send via Resend
5. Update the queue status

## Database Configuration

### Tenant Settings Structure

The `tenants.settings` JSONB field should include:

```json
{
  "email_provider": "resend",
  "resend_key": "re_xxx...",
  "resend_from": "onboarding@resend.dev",
  "api_base_url": "https://api.example.com"
}
```

### Communication Queue Record

For work_order_receipt events, the `message_params` should include:

```json
{
  "work_order_id": "12345",
  "work_order_number": "WO-151371",
  "customer_name": "John Doe"
}
```

The `work_order_id` is used to fetch the PDF from:
```
{api_base_url}/api/serviceorder/{work_order_id}/pdf
```

## API Endpoint Requirements

The PDF endpoint should:

- **URL**: `/api/serviceorder/{workOrderId}/pdf`
- **Method**: GET
- **Authentication**: None (based on configuration)
- **Response**: PDF file (Content-Type: application/pdf)
- **Status Codes**:
  - 200: Success, returns PDF
  - 404: Work order not found
  - 500: Server error

## Error Handling

The system handles errors gracefully:

1. **Missing work_order_id**: Logs warning, sends email without attachment
2. **Missing api_base_url**: Logs warning, sends email without attachment
3. **PDF fetch fails**: Logs error, sends email without attachment
4. **PDF API returns 404**: Logs warning, sends email without attachment
5. **Network timeout**: Logs error (30s timeout), sends email without attachment

The email will always be sent, even if the PDF attachment fails.

## Logging

The system logs the following:

- PDF fetch attempts with work_order_id and URL
- Successful PDF fetches with size in bytes
- Failed PDF fetches with status codes and errors
- Email send operations with attachment count

## Testing Checklist

- [ ] Configure api_base_url in tenant settings
- [ ] Verify API endpoint is accessible
- [ ] Insert test work_order_receipt record
- [ ] Run send_test_email_from_queue.py
- [ ] Check logs for PDF fetch success
- [ ] Verify email received with PDF attachment
- [ ] Test with missing work_order_id (should send without attachment)
- [ ] Test with invalid work_order_id (should send without attachment)
- [ ] Test with API timeout (should send without attachment)

## Production Integration

To integrate with your production system:

1. **Update the scheduler/processor** to use the new email service
2. **Ensure api_base_url is set** for all tenants
3. **Monitor logs** for PDF fetch failures
4. **Set up alerts** for repeated PDF fetch failures

## Example: Production Use

```python
from src.providers.email_service import create_email_service
from src.providers.email_adapter import EmailAttachment
from src.utils.pdf_fetcher import fetch_work_order_pdf
from src.db.tenant_data_gateway import get_tenant_config

# Get tenant config
config = get_tenant_config('yearround')

# For work_order_receipt events
if event_type == 'work_order_receipt':
    work_order_id = message_params.get('work_order_id')
    api_base_url = config.get('api_base_url')

    attachments = None
    if work_order_id and api_base_url:
        pdf_content = fetch_work_order_pdf(work_order_id, api_base_url)
        if pdf_content:
            attachments = [EmailAttachment(
                filename=f"work_order_{work_order_number}.pdf",
                content=pdf_content,
                content_type='application/pdf'
            )]

    # Send email with attachment
    service = create_email_service(config)
    response = service.send_email(
        to=recipient_email,
        subject=subject,
        body=body,
        config=config,
        attachments=attachments
    )
```

## Troubleshooting

### PDF not attaching

1. Check api_base_url is configured: `SELECT settings->>'api_base_url' FROM tenants WHERE tenant_id = 'yearround'`
2. Check work_order_id is in message_params
3. Test the API endpoint directly: `curl {api_base_url}/api/serviceorder/{work_order_id}/pdf`
4. Check logs for error messages

### Email not sending

1. Verify email provider configuration (resend_key, etc.)
2. Check recipient email address
3. Review Resend dashboard for errors
4. Check application logs

## File Structure

```
src/
├── providers/
│   ├── email_adapter.py     # Added EmailAttachment class
│   ├── email_service.py     # Added attachments parameter
│   └── resend_adapter.py    # Added attachment encoding
├── utils/
│   └── pdf_fetcher.py       # New: PDF fetching utility
└── db/
    └── tenant_data_gateway.py  # Added api_base_url config

Scripts:
├── update_tenant_api_config.py     # Configure API base URL
├── insert_work_order_receipt_test.py  # Insert test data
└── send_test_email_from_queue.py   # Enhanced with PDF support
```
