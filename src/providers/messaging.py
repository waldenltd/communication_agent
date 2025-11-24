import base64
from twilio.rest import Client as TwilioClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from src import logger


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
    """Send email via SendGrid."""
    if not tenant_config.get('sendgrid_key'):
        raise Exception('Missing SendGrid API key')

    from_addr = from_email or tenant_config.get('sendgrid_from') or 'no-reply@example.com'

    message = Mail(
        from_email=from_addr,
        to_emails=to,
        subject=subject,
        plain_text_content=body
    )

    try:
        sg = SendGridAPIClient(tenant_config['sendgrid_key'])
        response = sg.send(message)

        if response.status_code >= 400:
            raise Exception(
                f'SendGrid returned status {response.status_code}: {response.body}'
            )

        return response
    except Exception as e:
        raise Exception(f'Failed to send email: {str(e)}')
