"""
Usage-Based Service Alert Job Handler

Sends service reminder emails when equipment reaches service interval hours.
"""

from src import logger, config
from src.db.tenant_data_gateway import find_usage_service_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_usage_service_alert_jobs(tenant_id, hours_interval=None):
    """
    Find equipment due for service based on usage hours and create reminder jobs.

    Args:
        tenant_id: The tenant ID to process
        hours_interval: Service interval in machine hours (default from config)

    Returns:
        Number of jobs created
    """
    if hours_interval is None:
        hours_interval = config.SCHEDULER_CONFIG.get('usage_service_hours_interval', 100)

    jobs_created = 0

    try:
        candidates = find_usage_service_candidates(tenant_id, hours_interval)

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
            machine_hours = candidate.get('machine_hours', 0)
            last_service_hours = candidate.get('last_service_hours', 0)

            # Calculate which service interval this is
            service_number = int(machine_hours // hours_interval)

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'machine_hours': machine_hours,
                'service_interval': hours_interval,
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='usage_service_alert',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Allow one alert per service interval milestone
            source_reference = f'usage_service_{tenant_id}_{equipment_id}_{service_number}'

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
                    'service_interval': hours_interval,
                    'event_type': 'usage_service_alert'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created usage service alert job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    equipment_id=equipment_id,
                    machine_hours=machine_hours
                )

    except Exception as e:
        logger.error(
            'Usage service alert job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
