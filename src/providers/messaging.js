const logger = require('../logger');

const fetchImpl =
  globalThis.fetch ||
  ((...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args)));

const ensureSuccessfulResponse = async (response, channel) => {
  if (response.ok) {
    return;
  }

  const payload = await response.text();
  const error = new Error(
    `Failed to send ${channel} message (${response.status}): ${payload}`
  );
  error.statusCode = response.status;
  error.body = payload;
  throw error;
};

const sendSmsViaTwilio = async ({ tenantConfig, to, body, from }) => {
  if (!tenantConfig.twilioSid || !tenantConfig.twilioAuthToken) {
    throw new Error('Missing Twilio credentials');
  }

  if (!to) {
    throw new Error('SMS requires a destination phone number');
  }

  if (!from && !tenantConfig.twilioFromNumber) {
    throw new Error('Missing Twilio "from" number');
  }

  const endpoint = `https://api.twilio.com/2010-04-01/Accounts/${tenantConfig.twilioSid}/Messages.json`;
  const params = new URLSearchParams({
    To: to,
    From: from || tenantConfig.twilioFromNumber,
    Body: body
  });

  const auth = Buffer.from(
    `${tenantConfig.twilioSid}:${tenantConfig.twilioAuthToken}`
  ).toString('base64');

  logger.debug({ to }, 'Sending SMS via Twilio');

  const response = await fetchImpl(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${auth}`,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: params
  });

  await ensureSuccessfulResponse(response, 'sms');
};

const sendEmailViaSendGrid = async ({
  tenantConfig,
  to,
  subject,
  body,
  from
}) => {
  if (!tenantConfig.sendgridKey) {
    throw new Error('Missing SendGrid API key');
  }

  const payload = {
    personalizations: [
      {
        to: [{ email: to }]
      }
    ],
    from: {
      email: from || tenantConfig.sendgridFrom || 'no-reply@example.com'
    },
    subject,
    content: [
      {
        type: 'text/plain',
        value: body
      }
    ]
  };

  const response = await fetchImpl('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${tenantConfig.sendgridKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  await ensureSuccessfulResponse(response, 'email');
};

module.exports = {
  sendSmsViaTwilio,
  sendEmailViaSendGrid
};
