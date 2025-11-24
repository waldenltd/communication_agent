const { sendSmsViaTwilio } = require('../../providers/messaging');

module.exports = async function handleSendSms(job, context) {
  const { payload } = job;
  if (!payload?.to) {
    throw new Error('SMS payload missing "to"');
  }

  if (!payload.body) {
    throw new Error('SMS payload missing "body"');
  }

  const fromNumber = payload.from || context.tenantConfig.twilioFromNumber;
  if (!fromNumber) {
    throw new Error('SMS payload missing "from" and tenant has no default number');
  }

  await sendSmsViaTwilio({
    tenantConfig: context.tenantConfig,
    to: payload.to,
    body: payload.body,
    from: fromNumber
  });
};
