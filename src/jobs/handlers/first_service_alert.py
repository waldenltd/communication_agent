"""
First Service Alert Job Handler

Sends first service reminder emails when equipment reaches the first service hours threshold.
"""

from src import logger, config
from src.db.tenant_data_gateway import find_first_service_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_first_service_alert_jobs(tenant_id, hours_threshold=None):
    """
    Find equipment that has reached first service hours and create reminder jobs.

    Args:
        tenant_id: The tenant ID to process
        hours_threshold: Machine hours threshold for first service (default from config)

    Returns:
        Number of jobs created
    """
    if hours_threshold is None:
        hours_threshold = config.SCHEDULER_CONFIG.get('first_service_hours_threshold', 20)

    jobs_created = 0

    try:
        candidates = find_first_service_candidates(tenant_id, hours_threshold)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Service Team')

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            equipment_id = candidate.get('equipment_id')
            customer_id = candidate.get('customer_id')
            machine_hours = candidate.get('machine_hours', hours_threshold)

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'machine_hours': machine_hours,
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='first_service_alert',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Only send once per equipment (first service is a one-time event)
            source_reference = f'first_service_{tenant_id}_{equipment_id}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'equipment_id': equipment_id,
                    'machine_hours': machine_hours,
                    'event_type': 'first_service_alert'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created first service alert job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    equipment_id=equipment_id,
                    machine_hours=machine_hours
                )

    except Exception as e:
        logger.error(
            'First service alert job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
