"""
Seven Day Check-In Job Handler

Sends a friendly check-in email to customers 7 days after equipment purchase.
"""

from src import logger
from src.db.tenant_data_gateway import find_seven_day_checkin_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_seven_day_checkin_jobs(tenant_id):
    """
    Find equipment sold 7 days ago and create check-in email jobs.

    Args:
        tenant_id: The tenant ID to process

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_seven_day_checkin_candidates(tenant_id)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Equipment Team')

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            equipment_id = candidate.get('equipment_id')
            customer_id = candidate.get('customer_id')

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='seven_day_checkin',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            source_reference = f'seven_day_checkin_{tenant_id}_{equipment_id}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'equipment_id': equipment_id,
                    'event_type': 'seven_day_checkin'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created seven day check-in job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    equipment_id=equipment_id
                )

    except Exception as e:
        logger.error(
            'Seven day check-in job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
