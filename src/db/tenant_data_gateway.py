import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from src.db.central_db import query as central_query
from src import logger

# Cache for tenant configurations
tenant_config_cache = {}

# Pool storage for tenant databases
tenant_db_pools = {}


def get_tenant_config(tenant_id):
    """Fetch tenant configuration from central DB with caching."""
    if tenant_id in tenant_config_cache:
        return tenant_config_cache[tenant_id]

    query_text = """
        SELECT tenant_id,
               twilio_sid,
               twilio_auth_token,
               twilio_from_number,
               sendgrid_key,
               sendgrid_from,
               email_provider,
               resend_key,
               resend_from,
               quiet_hours_start,
               quiet_hours_end,
               dms_connection_string
        FROM tenant_configs
        WHERE tenant_id = %s
    """

    rows = central_query(query_text, [tenant_id])

    if not rows:
        raise Exception(f'Missing tenant config for tenant {tenant_id}')

    row = rows[0]
    config = {
        'tenant_id': tenant_id,
        'twilio_sid': row['twilio_sid'],
        'twilio_auth_token': row['twilio_auth_token'],
        'twilio_from_number': row['twilio_from_number'],
        'sendgrid_key': row['sendgrid_key'],
        'sendgrid_from': row.get('sendgrid_from'),
        'email_provider': row.get('email_provider'),
        'resend_key': row.get('resend_key'),
        'resend_from': row.get('resend_from'),
        'quiet_hours_start': row['quiet_hours_start'],
        'quiet_hours_end': row['quiet_hours_end'],
        'dms_connection_string': row['dms_connection_string']
    }

    tenant_config_cache[tenant_id] = config
    return config


def get_tenant_db_pool(tenant_id):
    """Get or create a connection pool for a tenant database."""
    if tenant_id in tenant_db_pools:
        return tenant_db_pools[tenant_id]

    tenant_config = get_tenant_config(tenant_id)
    if not tenant_config['dms_connection_string']:
        raise Exception(
            f'Tenant {tenant_id} does not expose a DMS connection string.'
        )

    tenant_pool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=15,
        dsn=tenant_config['dms_connection_string']
    )

    tenant_db_pools[tenant_id] = tenant_pool
    return tenant_pool


def query_tenant_db(tenant_id, query_text, params=None):
    """Execute a query against a tenant's database."""
    tenant_pool = get_tenant_db_pool(tenant_id)
    conn = tenant_pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query_text, params or [])
            if cursor.description:
                return cursor.fetchall()
            return []
    finally:
        tenant_pool.putconn(conn)


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


def shutdown_tenant_pools():
    """Close all tenant database connection pools."""
    for tenant_pool in tenant_db_pools.values():
        try:
            tenant_pool.closeall()
        except Exception as e:
            logger.error('Failed to close tenant pool', err=e)
