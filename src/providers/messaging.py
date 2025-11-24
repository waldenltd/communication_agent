"""
Messaging module - Provides SMS and Email sending functionality.

This module now uses the Adapter Pattern for email sending,
making it easy to switch between providers (SendGrid, Resend, etc.)
"""

from twilio.rest import Client as TwilioClient
from src import logger
from src.providers.email_service import create_email_service


def send_sms_via_twilio(tenant_config, to, body, from_number=None):
    """Send SMS via Twilio."""
    if not tenant_config.get('twilio_sid') or not tenant_config.get('twilio_auth_token'):
        raise Exception('Missing Twilio credentials')

    if not to:
        raise Exception('SMS requires a destination phone number')

    from_num = from_number or tenant_config.get('twilio_from_number')
    if not from_num:
        raise Exception('Missing Twilio "from" number')

    logger.debug('Sending SMS via Twilio', to=to)

    client = TwilioClient(
        tenant_config['twilio_sid'],
        tenant_config['twilio_auth_token']
    )

    try:
        message = client.messages.create(
            to=to,
            from_=from_num,
            body=body
        )
        return message.sid
    except Exception as e:
        raise Exception(f'Failed to send SMS: {str(e)}')


def send_email_via_sendgrid(tenant_config, to, subject, body, from_email=None):
    """
    Send email using the adapter pattern.

    This function now uses the EmailService with adapters, which automatically
    selects the appropriate email provider based on tenant configuration.

    Supported providers:
    - SendGrid (default): Requires 'sendgrid_key' in config
    - Resend: Requires 'resend_key' in config

    To explicitly set provider, add 'email_provider': 'sendgrid' or 'resend' to config.

    Args:
        tenant_config: Tenant configuration dict
        to: Recipient email address
        subject: Email subject
        body: Plain text body
        from_email: Optional sender email (overrides config default)

    Raises:
        Exception: If email send fails
    """
    # Create email service (automatically detects provider from config)
    email_service = create_email_service(tenant_config)

    # Send email using the service
    response = email_service.send_email(
        to=to,
        subject=subject,
        body=body,
        config=tenant_config,
        from_email=from_email
    )

    # Raise exception if send failed (for backward compatibility)
    if not response.success:
        raise Exception(response.error)

    return response
