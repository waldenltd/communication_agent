from src.db.tenant_data_gateway import (
    fetch_tenant_customer_contact,
    get_contact_preference
)
from src.providers.messaging import send_sms_via_twilio, send_email_via_sendgrid


def handle_notify_customer(job, context):
    """Handle notify_customer job type."""
    payload = job['payload']

    if not payload.get('customer_id'):
        raise Exception('notify_customer job missing customer_id')

    if not payload.get('body'):
        raise Exception('notify_customer job missing body')

    customer = fetch_tenant_customer_contact(
        job['tenant_id'],
        payload['customer_id']
    )

    if not customer:
        raise Exception(
            f'Customer {payload["customer_id"]} not found for tenant {job["tenant_id"]}'
        )

    preference = get_contact_preference(
        job['tenant_id'],
        payload['customer_id']
    ) or payload.get('preferred_channel')

    if preference == 'do_not_contact':
        return {'skip': True, 'reason': 'Customer opted out of communications'}

    channel = preference or ('sms' if customer.get('phone') else 'email') or payload.get('fallback_channel')

    if channel == 'sms' and not customer.get('phone'):
        raise Exception('Customer is missing a phone number')

    if channel == 'email' and not customer.get('email'):
        raise Exception('Customer is missing an email address')

    if channel == 'sms':
        send_sms_via_twilio(
            tenant_config=context['tenant_config'],
            to=customer['phone'],
            body=payload['body'],
            from_number=payload.get('from')
        )
        return

    send_email_via_sendgrid(
        tenant_config=context['tenant_config'],
        to=customer['email'],
        subject=payload.get('subject', 'Notification'),
        body=payload['body']
    )
