const { Pool } = require('pg');
const { pool: centralPool } = require('./centralDb');
const logger = require('../logger');

const tenantConfigCache = new Map();
const tenantDbPools = new Map();

const getTenantConfig = async (tenantId) => {
  if (tenantConfigCache.has(tenantId)) {
    return tenantConfigCache.get(tenantId);
  }

  const query = `
    SELECT tenant_id,
           twilio_sid,
           twilio_auth_token,
           twilio_from_number,
           sendgrid_key,
           quiet_hours_start,
           quiet_hours_end,
           dms_connection_string
    FROM tenant_configs
    WHERE tenant_id = $1
  `;

  const { rows } = await centralPool.query(query, [tenantId]);

  if (!rows.length) {
    throw new Error(`Missing tenant config for tenant ${tenantId}`);
  }

  const config = {
    tenantId,
    twilioSid: rows[0].twilio_sid,
    twilioAuthToken: rows[0].twilio_auth_token,
    twilioFromNumber: rows[0].twilio_from_number,
    sendgridKey: rows[0].sendgrid_key,
    quietHoursStart: rows[0].quiet_hours_start,
    quietHoursEnd: rows[0].quiet_hours_end,
    dmsConnectionString: rows[0].dms_connection_string
  };

  tenantConfigCache.set(tenantId, config);
  return config;
};

const getTenantDbPool = async (tenantId) => {
  if (tenantDbPools.has(tenantId)) {
    return tenantDbPools.get(tenantId);
  }

  const tenantConfig = await getTenantConfig(tenantId);
  if (!tenantConfig.dmsConnectionString) {
    throw new Error(
      `Tenant ${tenantId} does not expose a DMS connection string.`
    );
  }

  const pool = new Pool({
    connectionString: tenantConfig.dmsConnectionString,
    max: 15,
    idleTimeoutMillis: 30_000
  });

  tenantDbPools.set(tenantId, pool);
  return pool;
};

const fetchTenantCustomerContact = async (tenantId, customerId) => {
  const pool = await getTenantDbPool(tenantId);
  const query = `
    SELECT id,
           email,
           phone_mobile AS phone,
           contact_preference,
           do_not_disturb_until
    FROM customers
    WHERE id = $1
  `;

  const { rows } = await pool.query(query, [customerId]);
  return rows[0] || null;
};

const findFallbackEmail = async (tenantId, customerId) => {
  const customer = await fetchTenantCustomerContact(tenantId, customerId);
  return customer?.email || null;
};

const getContactPreference = async (tenantId, customerId) => {
  const customer = await fetchTenantCustomerContact(tenantId, customerId);
  if (!customer) {
    return null;
  }

  if (customer.contact_preference === 'do_not_contact') {
    return 'do_not_contact';
  }

  return customer.contact_preference || null;
};

const findServiceReminderCandidates = async (tenantId) => {
  const pool = await getTenantDbPool(tenantId);
  const query = `
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
  `;
  const { rows } = await pool.query(query);
  return rows;
};

const findAppointmentsWithinWindow = async (tenantId) => {
  const pool = await getTenantDbPool(tenantId);
  const query = `
    SELECT a.id AS appointment_id,
           a.customer_id,
           a.scheduled_start,
           c.phone_mobile AS phone,
           c.first_name
    FROM appointments a
    INNER JOIN customers c ON c.id = a.customer_id
    WHERE a.scheduled_start BETWEEN NOW() + INTERVAL '24 hours'
                              AND NOW() + INTERVAL '25 hours'
  `;
  const { rows } = await pool.query(query);
  return rows;
};

const findPastDueInvoices = async (tenantId) => {
  const pool = await getTenantDbPool(tenantId);
  const query = `
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
  `;
  const { rows } = await pool.query(query);
  return rows;
};

const shutdownTenantPools = async () => {
  for (const pool of tenantDbPools.values()) {
    try {
      await pool.end();
    } catch (error) {
      logger.error({ err: error }, 'Failed to close tenant pool');
    }
  }
};

module.exports = {
  getTenantConfig,
  findFallbackEmail,
  getContactPreference,
  fetchTenantCustomerContact,
  findServiceReminderCandidates,
  findAppointmentsWithinWindow,
  findPastDueInvoices,
  shutdownTenantPools
};
