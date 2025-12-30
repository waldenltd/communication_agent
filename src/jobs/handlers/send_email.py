from src.providers.messaging import send_email_via_sendgrid


def handle_send_email(job, context):
    """Handle send_email job type."""
    payload = job['payload']

    if not payload.get('to'):
        raise Exception('Email payload missing "to"')

    if not payload.get('subject'):
        raise Exception('Email payload missing "subject"')

    if not payload.get('body'):
        raise Exception('Email payload missing "body"')

    send_email_via_sendgrid(
        tenant_config=context['tenant_config'],
        to=payload['to'],
        subject=payload['subject'],
        body=payload['body'],
        from_email=payload.get('from')
    )
