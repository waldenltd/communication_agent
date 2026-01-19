"""
Ghost Customer (Win-Back) Job Handler

Sends "we miss you" emails to customers who haven't visited in 12+ months.
"""

from datetime import datetime
from src import logger
from src.db.tenant_data_gateway import find_ghost_customers, get_tenant_config
from src.jobs.job_repository import insert_job
from src.providers.ai_content_generator import generate_email_content


def create_ghost_customer_jobs(tenant_id, months=12):
    """
    Find customers with no activity in N months and create win-back jobs.

    Args:
        tenant_id: The tenant ID to process
        months: Number of months of inactivity (default 12)

    Returns:
        Number of jobs created
    """
    jobs_created = 0

    try:
        candidates = find_ghost_customers(tenant_id, months)

        if not candidates:
            return 0

        tenant_config = get_tenant_config(tenant_id)
        company_name = tenant_config.get('company_name', 'Your Service Team')

        current_year = datetime.now().year
        current_quarter = (datetime.now().month - 1) // 3 + 1

        for candidate in candidates:
            email = candidate.get('email_address')
            if not email:
                continue

            customer_id = candidate.get('customer_id')
            last_order = candidate.get('last_order_date')

            # Calculate months since last visit
            months_inactive = 0
            if last_order:
                delta = datetime.now() - last_order
                months_inactive = delta.days // 30

            # Build message params for AI content generation
            message_params = {
                'customer_name': _format_name(candidate),
                'first_name': candidate.get('first_name', ''),
                'months_inactive': months_inactive,
                'lifetime_value': candidate.get('lifetime_value', 0),
                'total_orders': candidate.get('total_orders', 0),
                'company_name': company_name
            }

            # Generate personalized content
            content = generate_email_content(
                event_type='winback_missed_you',
                message_params=message_params,
                recipient_address={'email': email, 'name': message_params['customer_name']},
                company_name=company_name
            )

            # Create the email job with deduplication reference
            # Allow one win-back per customer per quarter
            source_reference = f'winback_{tenant_id}_{customer_id}_{current_year}_Q{current_quarter}'

            result = insert_job(
                tenant_id=tenant_id,
                job_type='send_email',
                payload={
                    'to': email,
                    'subject': content['subject'],
                    'body': content['body'],
                    'customer_id': customer_id,
                    'months_inactive': months_inactive,
                    'event_type': 'winback_missed_you'
                },
                source_reference=source_reference
            )

            if result:
                jobs_created += 1
                logger.info(
                    'Created ghost customer win-back job',
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    months_inactive=months_inactive
                )

    except Exception as e:
        logger.error(
            'Ghost customer job creation failed',
            tenant_id=tenant_id,
            err=e
        )

    return jobs_created


def _format_name(candidate):
    """Format customer name from candidate record."""
    first = candidate.get('first_name', '')
    last = candidate.get('last_name', '')
    return ' '.join(filter(None, [first, last])) or 'Valued Customer'
