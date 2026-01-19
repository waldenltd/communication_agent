"""
Trade-In Alert Job Handler

Sends trade-in suggestions to customers with old equipment and high repair history.
"""

from datetime import datetime
from src import logger
from src.db.tenant_data_gateway import find_trade_in_candidates, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_trade_in_alert_jobs(tenant_id, min_age_years=8, min_repair_count=3):
    """
    Find old equipment with high repair history and create trade-in alert jobs.

    Args:
        tenant_id: The tenant ID to process
        min_age_years: Minimum age of equipment in years (default 8)
        min_repair_count: Minimum number of repairs (default 3)

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_trade_in_candidates(tenant_id, min_age_years, min_repair_count)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Service Team')

        current_year = datetime.now().year

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            equipment_id = candidate.get('equipment_id')
            customer_id = candidate.get('customer_id')
            years_owned = candidate.get('years_owned', min_age_years)
            repair_count = candidate.get('repair_count', 0)

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'equipment_type': candidate.get('equipment_type', 'equipment'),
                'equipment_make': candidate.get('equipment_make', ''),
                'equipment_model': candidate.get('equipment_model', ''),
                'years_owned': years_owned,
                'repair_count': repair_count,
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='trade_in_alert',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Allow one trade-in alert per equipment per year
            source_reference = f'trade_in_{tenant_id}_{equipment_id}_{current_year}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'equipment_id': equipment_id,
                    'years_owned': years_owned,
                    'repair_count': repair_count,
                    'event_type': 'trade_in_alert'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created trade-in alert job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    equipment_id=equipment_id,
                    years_owned=years_owned,
                    repair_count=repair_count
                )

    except Exception as e:
        logger.error(
            'Trade-in alert job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
