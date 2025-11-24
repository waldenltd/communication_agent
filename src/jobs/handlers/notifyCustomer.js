const {
  fetchTenantCustomerContact,
  getContactPreference
} = require('../../db/tenantDataGateway');
const { sendSmsViaTwilio, sendEmailViaSendGrid } = require('../../providers/messaging');

module.exports = async function handleNotifyCustomer(job, context) {
  const { payload } = job;
  if (!payload?.customer_id) {
    throw new Error('notify_customer job missing customer_id');
  }

  if (!payload?.body) {
    throw new Error('notify_customer job missing body');
  }

  const customer = await fetchTenantCustomerContact(
    job.tenant_id,
    payload.customer_id
  );
  if (!customer) {
    throw new Error(
      `Customer ${payload.customer_id} not found for tenant ${job.tenant_id}`
    );
  }

  const preference =
    (await getContactPreference(job.tenant_id, payload.customer_id)) ||
    payload?.preferred_channel;

  if (preference === 'do_not_contact') {
    return { skip: true, reason: 'Customer opted out of communications' };
  }

  const channel =
    preference ||
    (customer.phone ? 'sms' : 'email') ||
    payload.fallback_channel;

  if (channel === 'sms' && !customer.phone) {
    throw new Error('Customer is missing a phone number');
  }

  if (channel === 'email' && !customer.email) {
    throw new Error('Customer is missing an email address');
  }

  if (channel === 'sms') {
    await sendSmsViaTwilio({
      tenantConfig: context.tenantConfig,
      to: customer.phone,
      body: payload.body,
      from: payload.from
    });
    return;
  }

  await sendEmailViaSendGrid({
    tenantConfig: context.tenantConfig,
    to: customer.email,
    subject: payload.subject || 'Notification',
    body: payload.body
  });
};
