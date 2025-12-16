"""
Handler for processing items from the communication_queue table.

This handler:
1. Fetches pending items from communication_queue
2. Uses AI to generate email content based on event_type
3. Sends the email via the configured provider
4. Updates the queue item status
"""

import json
from src import logger
from src.db.central_db import query, execute
from src.db.tenant_data_gateway import get_tenant_config, fetch_work_order_equipment
from src.providers.email_service import create_email_service
from src.providers.email_adapter import EmailAttachment
from src.providers.ai_content_generator import generate_email_content
from src.utils.pdf_fetcher import fetch_work_order_pdf, fetch_sales_receipt_pdf


def process_communication_queue(tenant_id: str, limit: int = 10):
    """
    Process pending items from the communication_queue for a tenant.

    Args:
        tenant_id: The tenant ID string (e.g., 'yearround') to process
        limit: Maximum number of items to process in this batch
    """

    # Fetch pending email items from the queue
    # Match by tenant_id in message_params since queue.tenant_id is a UUID
    pending_items = query("""
        SELECT *
        FROM communication_queue
        WHERE message_params->>'tenant_id' = %s
          AND communication_type = 'email'
          AND status = 'pending'
        ORDER BY created_at ASC
        LIMIT %s
    """, (tenant_id, limit))

    if not pending_items:
        return 0

    logger.info(
        'Processing communication queue',
        tenant_id=tenant_id,
        item_count=len(pending_items)
    )

    processed = 0
    for item in pending_items:
        try:
            process_queue_item(item)
            processed += 1
        except Exception as e:
            logger.error(
                'Failed to process queue item',
                item_id=str(item['id']),
                error=str(e)
            )
            mark_item_failed(item['id'], str(e))

    return processed


def process_queue_item(item: dict):
    """Process a single queue item."""

    item_id = item['id']
    tenant_uuid = item['tenant_id']
    event_type = item['event_type']

    logger.info(
        'Processing queue item',
        item_id=str(item_id),
        event_type=event_type
    )

    # Parse recipient address
    recipient_address = item['recipient_address']
    if isinstance(recipient_address, str):
        recipient_address = json.loads(recipient_address)

    to_email = recipient_address.get('email')
    if not to_email:
        raise ValueError('No email address in recipient_address')

    # Parse message params
    message_params = item['message_params'] or {}
    if isinstance(message_params, str):
        message_params = json.loads(message_params)

    # Get tenant config
    # First check if tenant_id is in message_params (string like 'yearround')
    # Otherwise try to look up by UUID
    if message_params.get('tenant_id'):
        tenant_id = message_params['tenant_id']
    else:
        # Fallback: use the UUID directly as tenant_id string
        tenant_id = str(tenant_uuid)

    config = get_tenant_config(tenant_id)

    # Enrich message_params with equipment info if work_order_number is present
    if message_params.get('work_order_number'):
        try:
            equipment_info = fetch_work_order_equipment(
                tenant_id,
                message_params['work_order_number']
            )
            if equipment_info:
                message_params['equipment_model'] = equipment_info.get('equipment_model')
                message_params['serial_number'] = equipment_info.get('serial_number')
                message_params['manufacturer'] = equipment_info.get('manufacturer')
                message_params['year'] = equipment_info.get('year')
                message_params['service_description'] = equipment_info.get('service_description')
                logger.info(
                    'Enriched message with equipment info',
                    work_order_number=message_params['work_order_number'],
                    equipment_model=equipment_info.get('equipment_model')
                )
        except Exception as e:
            # Equipment lookup is optional - continue without it
            logger.warn(
                'Could not fetch equipment info, continuing without it',
                work_order_number=message_params['work_order_number'],
                error=str(e)
            )

    # Generate email content using AI
    company_name = config.get('company_name')
    subject_override = item.get('subject')  # Use provided subject if available

    email_content = generate_email_content(
        event_type=event_type,
        message_params=message_params,
        recipient_address=recipient_address,
        subject_override=subject_override,
        company_name=company_name
    )

    subject = email_content['subject']
    body = email_content['body']

    # Fetch attachments if applicable
    attachments = None
    if event_type == 'work_order_receipt':
        attachments = fetch_attachments_for_work_order(item, config, message_params)

    # Create email service and send
    service = create_email_service(config)

    logger.info(
        'Sending AI-generated email',
        to=to_email,
        event_type=event_type,
        provider=service.adapter.get_provider_name()
    )

    response = service.send_email(
        to=to_email,
        subject=subject,
        body=body,
        config=config,
        attachments=attachments
    )

    if response.success:
        mark_item_sent(item_id, response.message_id)
        logger.info(
            'Email sent successfully',
            item_id=str(item_id),
            message_id=response.message_id
        )
    else:
        raise Exception(f'Email send failed: {response.error}')


def fetch_attachments_for_work_order(item: dict, config: dict, message_params: dict) -> list:
    """Fetch PDF attachment for work order receipt emails."""

    work_order_number = message_params.get('work_order_number')
    api_base_url = config.get('api_base_url')

    if not work_order_number or not api_base_url:
        return None

    logger.info(
        'Fetching sales receipt PDF attachment',
        work_order_number=work_order_number
    )

    # Use sales receipt endpoint
    pdf_content = fetch_sales_receipt_pdf(work_order_number, api_base_url)

    if pdf_content:
        return [EmailAttachment(
            filename=f'sales_receipt_{work_order_number}.pdf',
            content=pdf_content,
            content_type='application/pdf'
        )]

    return None


def mark_item_sent(item_id, message_id: str):
    """Mark a queue item as sent."""
    execute("""
        UPDATE communication_queue
        SET status = 'sent',
            sent_at = NOW(),
            external_message_id = %s,
            external_status = %s::jsonb,
            updated_at = NOW()
        WHERE id = %s
    """, (message_id, json.dumps({'status': 'sent'}), str(item_id)))


def mark_item_failed(item_id, error: str):
    """Mark a queue item as failed."""
    execute("""
        UPDATE communication_queue
        SET status = 'failed',
            error_details = %s::jsonb,
            retry_count = retry_count + 1,
            last_retry_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """, (json.dumps({'error': error}), str(item_id)))
