from src.providers.messaging import send_sms_via_twilio


def handle_send_sms(job, context):
    """Handle send_sms job type."""
    payload = job['payload']

    if not payload.get('to'):
        raise Exception('SMS payload missing "to"')

    if not payload.get('body'):
        raise Exception('SMS payload missing "body"')

    from_number = payload.get('from') or context['tenant_config'].get('twilio_from_number')
    if not from_number:
        raise Exception('SMS payload missing "from" and tenant has no default number')

    send_sms_via_twilio(
        tenant_config=context['tenant_config'],
        to=payload['to'],
        body=payload['body'],
        from_number=from_number
    )
