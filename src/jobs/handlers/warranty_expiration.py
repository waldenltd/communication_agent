"""
Warranty Expiration Job Handler

Sends warranty expiration warning emails to customers with warranties expiring soon.
"""

from src import logger
from src.db.tenant_data_gateway import find_warranty_expiration_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_warranty_expiration_jobs(tenant_id, days_until_expiration=30):
    """
    Find equipment with warranty expiring within N days and create reminder jobs.

    Args:
        tenant_id: The tenant ID to process
        days_until_expiration: Number of days before expiration to send warning

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_warranty_expiration_candidates(tenant_id, days_until_expiration)

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
            warranty_end_date = candidate.get('warranty_end_date')

            # Format warranty end date for display
            warranty_date_str = 'soon'
            if warranty_end_date:
                warranty_date_str = warranty_end_date.strftime('%B %d, %Y')

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'warranty_end_date': warranty_date_str,
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='warranty_expiration',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Include year and month to allow one reminder per warranty period
            warranty_key = warranty_end_date.strftime('%Y%m') if warranty_end_date else 'unknown'
            source_reference = f'warranty_exp_{tenant_id}_{equipment_id}_{warranty_key}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'equipment_id': equipment_id,
                    'warranty_end_date': warranty_date_str,
                    'event_type': 'warranty_expiration'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created warranty expiration job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    equipment_id=equipment_id,
                    warranty_expires=warranty_date_str
                )

    except Exception as e:
        logger.error(
            'Warranty expiration job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
