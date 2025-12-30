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


def shutdown_tenant_pools():
    """Close all tenant database connection pools."""
    for tenant_pool in tenant_db_pools.values():
        try:
            tenant_pool.close()
        except Exception as e:
            logger.error('Failed to close tenant pool', err=e)
