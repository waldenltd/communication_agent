"""
Post-Service Survey Job Handler

Sends a survey/follow-up email to customers 48-72 hours after service pickup.
"""

from src import logger
from src.db.tenant_data_gateway import find_post_service_survey_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_post_service_survey_jobs(tenant_id):
    """
    Find work orders picked up 48-72 hours ago and create survey email jobs.

    Args:
        tenant_id: The tenant ID to process

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_post_service_survey_candidates(tenant_id)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Service Team')

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            service_record_id = candidate.get('service_record_id')
            customer_id = candidate.get('customer_id')
            work_order_number = candidate.get('work_order_number', '')

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'work_order_number': work_order_number,
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='post_service_survey',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            source_reference = f'post_service_survey_{tenant_id}_{service_record_id}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'work_order_id': service_record_id,
                    'work_order_number': work_order_number,
                    'event_type': 'post_service_survey'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created post-service survey job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    work_order_number=work_order_number
                )

    except Exception as e:
        logger.error(
            'Post-service survey job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
