import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from src.db.central_db import query as central_query
from src import logger

# Cache for tenant configurations
tenant_config_cache = {}

# Pool storage for tenant databases
tenant_db_pools = {}


def get_tenant_config(tenant_id):
    """
    Fetch tenant configuration from central DB with caching.

    Reads configuration from the tenants table's settings JSONB field.
    """
    if tenant_id in tenant_config_cache:
        return tenant_config_cache[tenant_id]

    query_text = """
        SELECT tenant_id,
               settings
        FROM tenants
        WHERE tenant_id = %s
    """

    rows = central_query(query_text, [tenant_id])

    if not rows:
        raise Exception(f'Missing tenant config for tenant {tenant_id}')

    row = rows[0]
    settings = row['settings'] if isinstance(row['settings'], dict) else {}

    # Build config from settings JSONB field
    config = {
        'tenant_id': tenant_id,

        # SMS Configuration (Twilio)
        'twilio_sid': settings.get('twilio_sid'),
        'twilio_auth_token': settings.get('twilio_auth_token'),
        'twilio_from_number': settings.get('twilio_from_number'),

        # Email Configuration
        'sendgrid_key': settings.get('sendgrid_key'),
        'sendgrid_from': settings.get('sendgrid_from'),
        'email_provider': settings.get('email_provider'),
        'resend_key': settings.get('resend_key'),
        'resend_from': settings.get('resend_from'),

        # Operational Settings
        'quiet_hours_start': settings.get('quiet_hours_start'),
        'quiet_hours_end': settings.get('quiet_hours_end'),

        # API Configuration
        'api_base_url': settings.get('api_base_url'),

        # Company Info
        'company_name': settings.get('company_name'),
        'company_phone': settings.get('company_phone'),
        'default_signature': settings.get('default_signature'),

        # Gmail Configuration (for contact form auto-responses)
        'gmail_enabled': settings.get('gmail_enabled', False),
        'gmail_client_id': settings.get('gmail_client_id'),
        'gmail_client_secret': settings.get('gmail_client_secret'),
        'gmail_refresh_token': settings.get('gmail_refresh_token'),
        'gmail_contact_form_sender': settings.get('gmail_contact_form_sender'),

        # DMS Connection (from settings or construct from DB credentials)
        'dms_connection_string': settings.get('dms_connection_string') or _build_dms_connection(settings)
    }

    tenant_config_cache[tenant_id] = config
    return config


def _build_dms_connection(settings):
    """Build DMS connection string from individual database settings."""
    db_host = settings.get('DatabaseHost', 'localhost')
    db_port = settings.get('DatabasePort', 5432)
    db_name = settings.get('DatabaseName')
    db_user = settings.get('DatabaseUser', 'postgres')
    db_password = settings.get('DatabasePassword', '')

    if db_name:
        return f'postgres://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'

    return None


def get_tenant_db_pool(tenant_id):
    """Get or create a connection pool for a tenant database."""
    if tenant_id in tenant_db_pools:
        return tenant_db_pools[tenant_id]

    tenant_config = get_tenant_config(tenant_id)
    if not tenant_config['dms_connection_string']:
        raise Exception(
            f'Tenant {tenant_id} does not expose a DMS connection string.'
        )

    tenant_pool = ConnectionPool(
        conninfo=tenant_config['dms_connection_string'],
        min_size=1,
        max_size=15
    )

    tenant_db_pools[tenant_id] = tenant_pool
    return tenant_pool


def query_tenant_db(tenant_id, query_text, params=None):
    """Execute a query against a tenant's database."""
    tenant_pool = get_tenant_db_pool(tenant_id)
    with tenant_pool.connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cursor:
            cursor.execute(query_text, params or [])
            if cursor.description:
                return cursor.fetchall()
            return []


def fetch_tenant_customer_contact(tenant_id, customer_id):
    """Fetch customer contact information from tenant database."""
    query_text = """
        SELECT id,
               email,
               phone_mobile AS phone,
               contact_preference,
               do_not_disturb_until
        FROM customers
        WHERE id = %s
    """

    rows = query_tenant_db(tenant_id, query_text, [customer_id])
    return rows[0] if rows else None


def find_fallback_email(tenant_id, customer_id):
    """Find fallback email for SMS failures."""
    customer = fetch_tenant_customer_contact(tenant_id, customer_id)
    return customer.get('email') if customer else None


def get_contact_preference(tenant_id, customer_id):
    """Get customer's contact preference."""
    customer = fetch_tenant_customer_contact(tenant_id, customer_id)
    if not customer:
        return None

    if customer.get('contact_preference') == 'do_not_contact':
        return 'do_not_contact'

    return customer.get('contact_preference')


def find_service_reminder_candidates(tenant_id):
    """Find customers due for 2-year service reminders."""
    query_text = """
        SELECT c.id AS customer_id,
               c.email,
               c.first_name,
               c.last_name,
               s.model,
               s.serial_number
        FROM sales s
        INNER JOIN customers c ON c.id = s.customer_id
        WHERE s.purchase_date BETWEEN NOW() - INTERVAL '25 months'
                                AND NOW() - INTERVAL '23 months'
          AND c.email IS NOT NULL
    """
    return query_tenant_db(tenant_id, query_text)


def find_appointments_within_window(tenant_id):
    """Find appointments scheduled 24-25 hours from now."""
    query_text = """
        SELECT a.id AS appointment_id,
               a.customer_id,
               a.scheduled_start,
               c.phone_mobile AS phone,
               c.first_name
        FROM appointments a
        INNER JOIN customers c ON c.id = a.customer_id
        WHERE a.scheduled_start BETWEEN NOW() + INTERVAL '24 hours'
                                  AND NOW() + INTERVAL '25 hours'
    """
    return query_tenant_db(tenant_id, query_text)


def find_past_due_invoices(tenant_id):
    """Find invoices that are 30+ days past due."""
    query_text = """
        SELECT i.id AS invoice_id,
               i.customer_id,
               i.due_date,
               i.balance,
               c.email,
               c.first_name
        FROM invoices i
        INNER JOIN customers c ON c.id = i.customer_id
        WHERE i.due_date <= NOW() - INTERVAL '30 days'
          AND i.balance > 0
    """
    return query_tenant_db(tenant_id, query_text)


def fetch_work_order_equipment(tenant_id, work_order_number):
    """
    Fetch equipment information for a work order from tenant's DMS database.

    Returns equipment details like model, serial number, and service info.
    """
    query_text = """
        SELECT wo.work_order_number,
               wo.description AS service_description,
               e.model AS equipment_model,
               e.serial_number,
               e.year,
               e.manufacturer
        FROM work_orders wo
        LEFT JOIN equipment e ON e.id = wo.equipment_id
        WHERE wo.work_order_number = %s
    """
    rows = query_tenant_db(tenant_id, query_text, [work_order_number])
    return rows[0] if rows else None


def find_seven_day_checkin_candidates(tenant_id):
    """
    Find equipment sold exactly 7 days ago for check-in emails.

    Returns customers with equipment purchased 7 days ago who have email addresses.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.equipment_serial_number,
               e.date_sold,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE e.date_sold = CURRENT_DATE - INTERVAL '7 days'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text)


def find_post_service_survey_candidates(tenant_id):
    """
    Find work orders picked up 48-72 hours ago for post-service surveys.

    Uses detailed_status = 'Picked Up' with last_status_change_at since
    picked_up_at column may not be populated.
    """
    query_text = """
        SELECT wo.service_record_id,
               wo.work_order_number,
               wo.customer_id,
               wo.equipment_id,
               wo.last_status_change_at AS picked_up_at,
               wo.equipment_make,
               wo.equipment_model,
               c.first_name,
               c.last_name,
               c.email_address
        FROM work_orders wo
        INNER JOIN customers c ON c.customer_id = wo.customer_id
        WHERE wo.detailed_status = 'Picked Up'
          AND wo.last_status_change_at >= NOW() - INTERVAL '72 hours'
          AND wo.last_status_change_at <= NOW() - INTERVAL '48 hours'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text)


def find_annual_tuneup_candidates(tenant_id):
    """
    Find equipment with purchase anniversary in 14 days.

    Returns equipment where the month/day of date_sold matches 14 days from now,
    and the equipment is at least 1 year old.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.date_sold,
               EXTRACT(YEAR FROM AGE(e.date_sold))::integer AS years_owned,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE DATE_PART('month', e.date_sold) = DATE_PART('month', CURRENT_DATE + INTERVAL '14 days')
          AND DATE_PART('day', e.date_sold) = DATE_PART('day', CURRENT_DATE + INTERVAL '14 days')
          AND e.date_sold < CURRENT_DATE - INTERVAL '1 year'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text)


def find_seasonal_reminder_candidates(tenant_id):
    """
    Find all customers with equipment for seasonal reminders.

    Returns distinct customers who own equipment and have email addresses.
    Used for spring and fall seasonal campaigns.
    """
    query_text = """
        SELECT DISTINCT ON (c.customer_id)
               c.customer_id,
               c.first_name,
               c.last_name,
               c.email_address,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model
        FROM customers c
        INNER JOIN equipment e ON e.customer_id = c.customer_id
        WHERE c.email_address IS NOT NULL
          AND c.email_address != ''
        ORDER BY c.customer_id, e.created_at DESC
    """
    return query_tenant_db(tenant_id, query_text)


def find_ghost_customers(tenant_id, months=12):
    """
    Find customers with no activity in the specified number of months.

    Returns customers who have made purchases before but haven't had
    any work orders in the specified time period.
    """
    query_text = """
        SELECT c.customer_id,
               c.first_name,
               c.last_name,
               c.email_address,
               c.last_order_date,
               c.total_orders,
               c.lifetime_value
        FROM customers c
        WHERE c.last_order_date < NOW() - INTERVAL '%s months'
          AND c.total_orders > 0
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
        ORDER BY c.lifetime_value DESC
    """
    return query_tenant_db(tenant_id, query_text, [months])


def find_anniversary_offer_candidates(tenant_id):
    """
    Find equipment with purchase anniversary in 7 days.

    Similar to annual tuneup but used for anniversary offers/celebrations.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.date_sold,
               EXTRACT(YEAR FROM AGE(e.date_sold))::integer AS years_owned,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE DATE_PART('month', e.date_sold) = DATE_PART('month', CURRENT_DATE + INTERVAL '7 days')
          AND DATE_PART('day', e.date_sold) = DATE_PART('day', CURRENT_DATE + INTERVAL '7 days')
          AND e.date_sold < CURRENT_DATE - INTERVAL '1 year'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text)


def find_first_service_candidates(tenant_id, hours_threshold=20):
    """
    Find equipment that has reached first service hours threshold.

    Returns equipment where machine_hours >= threshold and no first service
    has been performed (last_service_date is null or before date_sold).
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.machine_hours,
               e.date_sold,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE e.machine_hours >= %s
          AND (e.last_service_date IS NULL OR e.last_service_date <= e.date_sold)
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text, [hours_threshold])


def find_usage_service_candidates(tenant_id, hours_interval=100):
    """
    Find equipment due for service based on usage hours.

    Returns equipment where machine_hours has crossed a service interval
    threshold since last service.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.machine_hours,
               e.last_service_hours,
               e.last_service_date,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE e.machine_hours >= COALESCE(e.last_service_hours, 0) + %s
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text, [hours_interval])


def find_customer_primary_phone(tenant_id, customer_id):
    """
    Find the primary mobile phone for a customer (for SMS).

    Returns the most recent Cell or Mobile phone number.
    """
    query_text = """
        SELECT phone_number, phone_type
        FROM phones
        WHERE customer_id = %s
          AND phone_type IN ('Cell', 'Mobile')
        ORDER BY created_at DESC
        LIMIT 1
    """
    rows = query_tenant_db(tenant_id, query_text, [customer_id])
    return rows[0] if rows else None


def find_warranty_expiration_candidates(tenant_id, days_until_expiration=30):
    """
    Find equipment with warranty expiring within N days.

    Returns equipment where warranty_end_date is within the specified window.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.warranty_end_date,
               e.date_sold,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        WHERE e.warranty_end_date IS NOT NULL
          AND e.warranty_end_date > CURRENT_DATE
          AND e.warranty_end_date <= CURRENT_DATE + INTERVAL '%s days'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
    """
    return query_tenant_db(tenant_id, query_text, [days_until_expiration])


def find_trade_in_candidates(tenant_id, min_age_years=8, min_repair_count=3):
    """
    Find equipment that may be good candidates for trade-in.

    Returns equipment that is old (8+ years) and has high repair history.
    """
    query_text = """
        SELECT e.equipment_id,
               e.customer_id,
               e.equipment_type,
               e.equipment_make,
               e.equipment_model,
               e.date_sold,
               EXTRACT(YEAR FROM AGE(e.date_sold))::integer AS years_owned,
               COUNT(wo.service_record_id) AS repair_count,
               c.first_name,
               c.last_name,
               c.email_address
        FROM equipment e
        INNER JOIN customers c ON c.customer_id = e.customer_id
        LEFT JOIN work_orders wo ON wo.equipment_id = e.equipment_id
        WHERE e.date_sold <= CURRENT_DATE - INTERVAL '%s years'
          AND c.email_address IS NOT NULL
          AND c.email_address != ''
        GROUP BY e.equipment_id, e.customer_id, e.equipment_type,
                 e.equipment_make, e.equipment_model, e.date_sold,
                 c.first_name, c.last_name, c.email_address
        HAVING COUNT(wo.service_record_id) >= %s
        ORDER BY COUNT(wo.service_record_id) DESC
    """
    return query_tenant_db(tenant_id, query_text, [min_age_years, min_repair_count])


def shutdown_tenant_pools():
    """Close all tenant database connection pools."""
    for tenant_pool in tenant_db_pools.values():
        try:
            tenant_pool.close()
        except Exception as e:
            logger.error('Failed to close tenant pool', err=e)
