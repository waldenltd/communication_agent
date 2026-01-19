"""
Gmail Inbox Polling Handler

Polls Gmail inbox for contact form emails and creates auto-response jobs.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from src.db.central_db import query
from src.jobs.job_repository import create_job
from src.providers.gmail_adapter import (
    GmailAdapter,
    GmailMessage,
    GmailApiError,
    GmailAuthenticationError,
    GmailQuotaExceededError
)
from src.providers.contact_form_parser import (
    ContactFormParser,
    ContactFormData,
    ContactFormParseError
)
from src.observability import info, warning, error as log_error
from src import config


def poll_gmail_inbox(tenant_id: str, tenant_config: Dict[str, Any]) -> int:
    """
    Poll Gmail inbox for new contact form emails.

    Args:
        tenant_id: Tenant identifier
        tenant_config: Tenant configuration with Gmail credentials

    Returns:
        Number of emails processed
    """
    if not tenant_config.get('gmail_enabled'):
        return 0

    try:
        # Initialize Gmail adapter
        gmail = GmailAdapter(tenant_config)
        gmail.authenticate()

        # Build query to find contact form emails
        # Filter by sender if configured
        query_parts = []
        contact_form_sender = tenant_config.get('gmail_contact_form_sender')
        if contact_form_sender:
            query_parts.append(f'from:{contact_form_sender}')

        # Add subject filter
        subject_filter = getattr(config, 'GMAIL_CONTACT_FORM_SUBJECT_FILTER', 'Contact')
        if subject_filter:
            query_parts.append(f'subject:{subject_filter}')

        # Exclude already-processed emails
        processed_label = getattr(config, 'GMAIL_PROCESSED_LABEL', 'yrp/processed')
        query_parts.append(f'-label:{processed_label}')

        gmail_query = ' '.join(query_parts) if query_parts else None
        max_messages = getattr(config, 'GMAIL_MAX_MESSAGES_PER_POLL', 10)

        # Fetch unread messages
        messages = gmail.fetch_unread_messages(
            query=gmail_query,
            max_results=max_messages
        )

        if not messages:
            return 0

        # Process each message
        processed_count = 0
        parser = ContactFormParser()

        for message in messages:
            try:
                # Check if already processed (database check as backup)
                if is_email_already_processed(tenant_id, message.message_id):
                    info(f"Skipping already-processed email: {message.message_id}")
                    continue

                # Check if it's a contact form email
                body = message.body_text or message.body_html or ''
                if not parser.is_contact_form_email(message.subject, body):
                    info(f"Skipping non-contact-form email: {message.subject}")
                    # Still mark as read to avoid re-checking
                    gmail.mark_as_read(message.message_id)
                    continue

                # Process the contact form email
                success = process_contact_form_email(
                    tenant_id=tenant_id,
                    message=message,
                    tenant_config=tenant_config,
                    parser=parser,
                    gmail=gmail
                )

                if success:
                    processed_count += 1

                # Mark as processed in Gmail (label + mark read)
                gmail.add_label(message.message_id, processed_label)
                gmail.mark_as_read(message.message_id)

            except Exception as e:
                log_error(
                    f"Error processing email {message.message_id}",
                    err=str(e),
                    subject=message.subject
                )
                # Record the error but continue with other messages
                record_processed_email(
                    tenant_id=tenant_id,
                    message=message,
                    was_valid=False,
                    parse_error=str(e)
                )
                # Still mark as processed to avoid infinite retries
                try:
                    gmail.add_label(message.message_id, processed_label)
                    gmail.mark_as_read(message.message_id)
                except Exception:
                    pass

        info(f"Gmail poll complete: {processed_count} emails processed for tenant {tenant_id}")
        return processed_count

    except GmailAuthenticationError as e:
        log_error(f"Gmail authentication failed for tenant {tenant_id}", err=str(e))
        return 0

    except GmailQuotaExceededError as e:
        warning(f"Gmail quota exceeded for tenant {tenant_id}", err=str(e))
        return 0

    except GmailApiError as e:
        log_error(f"Gmail API error for tenant {tenant_id}", err=str(e))
        return 0


def process_contact_form_email(
    tenant_id: str,
    message: GmailMessage,
    tenant_config: Dict[str, Any],
    parser: ContactFormParser,
    gmail: GmailAdapter
) -> bool:
    """
    Process a single contact form email.

    1. Parse the email content
    2. Create a send_email job for the auto-response
    3. Record in database

    Returns:
        True if successfully processed
    """
    try:
        # Parse the contact form
        body = message.body_text or message.body_html or ''
        contact_data = parser.parse(body, message.message_id)

        # Validate parsed data
        is_valid, errors = parser.is_valid_contact_form(contact_data)
        if not is_valid:
            warning(
                f"Invalid contact form data: {errors}",
                message_id=message.message_id
            )
            record_processed_email(
                tenant_id=tenant_id,
                message=message,
                contact_data=contact_data,
                was_valid=False,
                parse_error='; '.join(errors)
            )
            return False

        # Create auto-response job
        job_id = create_auto_response_job(
            tenant_id=tenant_id,
            contact_data=contact_data,
            tenant_config=tenant_config
        )

        # Record in database
        record_processed_email(
            tenant_id=tenant_id,
            message=message,
            contact_data=contact_data,
            response_job_id=job_id,
            was_valid=True
        )

        info(
            f"Created auto-response job for {contact_data.email}",
            job_id=job_id,
            inquiry_type=contact_data.inquiry_type
        )
        return True

    except ContactFormParseError as e:
        warning(f"Failed to parse contact form: {str(e)}", message_id=message.message_id)
        record_processed_email(
            tenant_id=tenant_id,
            message=message,
            was_valid=False,
            parse_error=str(e)
        )
        return False


def create_auto_response_job(
    tenant_id: str,
    contact_data: ContactFormData,
    tenant_config: Dict[str, Any]
) -> Optional[int]:
    """
    Create a communication_job for the auto-response email.

    Uses templates based on inquiry type (buying vs repairing).
    """
    # Get company info from config
    company_name = tenant_config.get('company_name', 'Year Round Power')
    company_phone = tenant_config.get('company_phone', '860-953-9421')
    signature_name = tenant_config.get('default_signature', 'Kathy Braga')

    # Build response based on inquiry type
    if contact_data.inquiry_type == 'buying':
        subject = f"Thank You for Your Interest - {contact_data.equipment_type}"
        body = generate_buying_response(
            contact_data=contact_data,
            company_name=company_name,
            company_phone=company_phone,
            signature_name=signature_name
        )
    else:  # repairing
        subject = f"Re: {contact_data.equipment_type} Repair Inquiry - {company_name}"
        body = generate_repairing_response(
            contact_data=contact_data,
            company_name=company_name,
            company_phone=company_phone,
            signature_name=signature_name
        )

    # Create the job
    payload = {
        'to': contact_data.email,
        'subject': subject,
        'body': body,
        'contact_form_data': {
            'first_name': contact_data.first_name,
            'last_name': contact_data.last_name,
            'phone': contact_data.phone,
            'inquiry_type': contact_data.inquiry_type,
            'equipment_type': contact_data.equipment_type,
            'message': contact_data.message,
            'location': contact_data.location
        }
    }

    # Use gmail message ID as source reference to prevent duplicates
    source_reference = f"gmail_contact_form:{contact_data.raw_email_id}"

    job_id = create_job(
        tenant_id=tenant_id,
        job_type='send_email',
        payload=payload,
        source_reference=source_reference
    )

    return job_id


def generate_buying_response(
    contact_data: ContactFormData,
    company_name: str,
    company_phone: str,
    signature_name: str
) -> str:
    """Generate response email for buying inquiries."""
    equipment = contact_data.equipment_type.lower()

    return f"""Hi {contact_data.first_name},

Thank you for your interest in {equipment} from {company_name}!

We'd love to help you find the right equipment for your needs. We carry a wide selection and our team can help you choose the best option.

Feel free to visit our showroom, give us a call at {company_phone}, or reply to this email with any questions.

Best regards,
{signature_name}
{company_name}"""


def generate_repairing_response(
    contact_data: ContactFormData,
    company_name: str,
    company_phone: str,
    signature_name: str
) -> str:
    """Generate response email for repair inquiries."""
    equipment = contact_data.equipment_type.lower()

    # Include location-specific info if available
    location_text = ""
    if contact_data.location:
        location_text = f" Yes, we do offer pickup and delivery service in {contact_data.location}."

    return f"""Hi {contact_data.first_name},

Thank you for reaching out to {company_name}!

We'd be happy to help with your {equipment} repair.{location_text}

To get started, could you let us know:
- The make and model of your {equipment}
- A brief description of the issue you're experiencing

Feel free to reply to this email or give us a call at {company_phone} to schedule service.

We look forward to helping you get your {equipment} running again!

Best regards,
{signature_name}
{company_name}"""


def record_processed_email(
    tenant_id: str,
    message: GmailMessage,
    contact_data: Optional[ContactFormData] = None,
    response_job_id: Optional[int] = None,
    was_valid: bool = True,
    parse_error: Optional[str] = None
) -> None:
    """Record processed email in the database."""
    try:
        query(
            """
            INSERT INTO gmail_processed_emails (
                tenant_id,
                gmail_message_id,
                gmail_thread_id,
                sender_email,
                sender_name,
                subject,
                inquiry_type,
                equipment_type,
                response_job_id,
                parse_error,
                was_valid,
                email_received_at,
                processed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, gmail_message_id) DO NOTHING
            """,
            [
                tenant_id,
                message.message_id,
                message.thread_id,
                message.sender_email,
                message.sender,
                message.subject,
                contact_data.inquiry_type if contact_data else None,
                contact_data.equipment_type if contact_data else None,
                response_job_id,
                parse_error,
                was_valid,
                message.received_at
            ]
        )
    except Exception as e:
        log_error(f"Failed to record processed email", err=str(e))


def is_email_already_processed(tenant_id: str, gmail_message_id: str) -> bool:
    """Check if an email has already been processed."""
    rows = query(
        """
        SELECT 1
        FROM gmail_processed_emails
        WHERE tenant_id = %s AND gmail_message_id = %s
        LIMIT 1
        """,
        [tenant_id, gmail_message_id]
    )
    return len(rows) > 0
