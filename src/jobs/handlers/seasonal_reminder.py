"""
Seasonal Reminder Job Handler

Sends seasonal preparation reminders (spring and fall) to equipment owners.
"""

from datetime import datetime
from src import logger
from src.db.tenant_data_gateway import find_seasonal_reminder_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_seasonal_reminder_jobs(tenant_id, season='spring'):
    """
    Find all equipment owners and create seasonal reminder jobs.

    Args:
        tenant_id: The tenant ID to process
        season: 'spring' or 'fall'

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_seasonal_reminder_candidates(tenant_id)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Service Team')

        # Determine event type based on season
        event_type = f'seasonal_reminder_{season}'
        current_year = datetime.now().year

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            customer_id = candidate.get('customer_id')

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'outdoor power equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'season': season,
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type=event_type,
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Include year and season to allow once per season per year
            source_reference = f'seasonal_{season}_{tenant_id}_{customer_id}_{current_year}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'season': season,
                    'event_type': event_type
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created seasonal reminder job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    season=season
                )

    except Exception as e:
        logger.error(
            'Seasonal reminder job creation failed',
            tenant_id=tenant_id,
            season=season,
            err=e
        )

    return jobs_created


def create_spring_reminder_jobs(tenant_id):
    """Create spring preparation reminder jobs."""
    return create_seasonal_reminder_jobs(tenant_id, season='spring')


def create_fall_reminder_jobs(tenant_id):
    """Create fall/winterization reminder jobs."""
    return create_seasonal_reminder_jobs(tenant_id, season='fall')


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
