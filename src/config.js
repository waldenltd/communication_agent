const path = require('path');

require('dotenv').config({
  path: process.env.ENV_FILE
    ? path.resolve(process.env.ENV_FILE)
    : undefined
});

const numberFromEnv = (key, fallback) => {
  const raw = process.env[key];
  if (!raw) {
    return fallback;
  }

  const parsed = Number(raw);
  return Number.isNaN(parsed) ? fallback : parsed;
};

module.exports = {
  centralDbUrl:
    process.env.CENTRAL_DB_URL ||
    'postgres://dms_agent@localhost:5432/dms_communications',
  pollIntervalMs: numberFromEnv('POLL_INTERVAL_MS', 5000),
  maxConcurrentJobs: numberFromEnv('MAX_CONCURRENT_JOBS', 5),
  retryDelayMinutes: numberFromEnv('RETRY_DELAY_MINUTES', 5),
  maxRetries: numberFromEnv('MAX_RETRIES', 3),
  scheduler: {
    serviceReminderHourUtc: numberFromEnv('SERVICE_REMINDER_HOUR_UTC', 14),
    invoiceReminderHourUtc: numberFromEnv('INVOICE_REMINDER_HOUR_UTC', 13),
    serviceReminderIntervalMs: 24 * 60 * 60 * 1000,
    invoiceReminderIntervalMs: 24 * 60 * 60 * 1000,
    appointmentConfirmationIntervalMs: numberFromEnv(
      'APPOINTMENT_CONFIRMATION_INTERVAL_MS',
      60 * 60 * 1000
    )
  }
};
