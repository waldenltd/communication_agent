const logger = require('./logger');
const config = require('./config');
const { query } = require('./db/centralDb');
const {
  findServiceReminderCandidates,
  findAppointmentsWithinWindow,
  findPastDueInvoices
} = require('./db/tenantDataGateway');
const { insertJob } = require('./jobs/jobRepository');

class Scheduler {
  constructor() {
    this.intervals = [];
  }

  start() {
    if (this.intervals.length) {
      return;
    }

    this.scheduleRecurringTask(
      'service-reminders',
      config.scheduler.serviceReminderIntervalMs,
      () => this.runServiceReminders()
    );
    this.scheduleRecurringTask(
      'appointment-confirmations',
      config.scheduler.appointmentConfirmationIntervalMs,
      () => this.runAppointmentConfirmations()
    );
    this.scheduleRecurringTask(
      'invoice-reminders',
      config.scheduler.invoiceReminderIntervalMs,
      () => this.runInvoiceReminders()
    );
  }

  stop() {
    this.intervals.forEach((timer) => clearInterval(timer));
    this.intervals = [];
  }

  scheduleRecurringTask(name, intervalMs, taskFn) {
    const run = async () => {
      try {
        await taskFn();
      } catch (error) {
        logger.error({ err: error }, `Scheduled task ${name} failed`);
      }
    };

    run();
    const timer = setInterval(run, intervalMs);
    this.intervals.push(timer);
  }

  async fetchTenants() {
    const { rows } = await query('SELECT tenant_id FROM tenant_configs');
    return rows.map((row) => row.tenant_id);
  }

  async runServiceReminders() {
    const tenants = await this.fetchTenants();
    for (const tenantId of tenants) {
      const candidates = await findServiceReminderCandidates(tenantId);
      for (const candidate of candidates) {
        if (!candidate.email) {
          continue;
        }
        const fullName = [candidate.first_name, candidate.last_name]
          .filter(Boolean)
          .join(' ');
        const body = `Hi ${fullName || 'there'}, it has been almost two years since your ${
          candidate.model || 'equipment'
        } purchase. Schedule a 2-Year Tune-Up Special to keep it running at peak performance.`;

        await insertJob({
          tenantId,
          jobType: 'send_email',
          payload: {
            to: candidate.email,
            subject: '2-Year Tune-Up Special',
            body,
            customer_id: candidate.customer_id
          },
          sourceReference: `service_reminder_${tenantId}_${candidate.customer_id}`
        });
      }
    }
    logger.info('Service reminder sweep completed');
  }

  async runAppointmentConfirmations() {
    const tenants = await this.fetchTenants();
    for (const tenantId of tenants) {
      const appointments = await findAppointmentsWithinWindow(tenantId);
      for (const appt of appointments) {
        if (!appt.phone) {
          continue;
        }
        const when = new Date(appt.scheduled_start).toLocaleString();
        const body = `Hi ${appt.first_name || ''}, this is a reminder of your service appointment scheduled for ${when}. Reply YES to confirm or call us to reschedule.`;

        await insertJob({
          tenantId,
          jobType: 'send_sms',
          payload: {
            to: appt.phone,
            body,
            customer_id: appt.customer_id
          },
          sourceReference: `appointment_${tenantId}_${appt.appointment_id}`
        });
      }
    }
    logger.info('Appointment confirmation sweep completed');
  }

  async runInvoiceReminders() {
    const tenants = await this.fetchTenants();
    for (const tenantId of tenants) {
      const invoices = await findPastDueInvoices(tenantId);
      for (const invoice of invoices) {
        if (!invoice.email) {
          continue;
        }

        const body = `Hello ${
          invoice.first_name || 'there'
        }, invoice #${invoice.invoice_id} is now ${Math.ceil(
          (Date.now() - new Date(invoice.due_date).getTime()) / 86400000
        )} days past due. Your outstanding balance is $${
          invoice.balance
        }. Please reply or log into your portal to pay.`;

        await insertJob({
          tenantId,
          jobType: 'send_email',
          payload: {
            to: invoice.email,
            subject: 'Friendly invoice reminder',
            body,
            customer_id: invoice.customer_id
          },
          sourceReference: `invoice_${tenantId}_${invoice.invoice_id}`
        });
      }
    }
    logger.info('Invoice reminder sweep completed');
  }
}

module.exports = Scheduler;
