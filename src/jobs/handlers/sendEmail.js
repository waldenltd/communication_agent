const { sendEmailViaSendGrid } = require('../../providers/messaging');

module.exports = async function handleSendEmail(job, context) {
  const { payload } = job;
  if (!payload?.to) {
    throw new Error('Email payload missing "to"');
  }

  if (!payload.subject) {
    throw new Error('Email payload missing "subject"');
  }

  if (!payload.body) {
    throw new Error('Email payload missing "body"');
  }

  await sendEmailViaSendGrid({
    tenantConfig: context.tenantConfig,
    to: payload.to,
    subject: payload.subject,
    body: payload.body,
    from: payload.from
  });
};
