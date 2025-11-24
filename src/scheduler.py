import threading
import time
import math
from datetime import datetime
from src import logger, config
from src.db.central_db import query
from src.db.tenant_data_gateway import (
    find_service_reminder_candidates,
    find_appointments_within_window,
    find_past_due_invoices
)
from src.jobs.job_repository import insert_job


class Scheduler:
    def __init__(self):
        self.intervals = []
        self.running = False

    def start(self):
        """Start all scheduled tasks."""
        if self.intervals:
            return

        self.running = True

        self.schedule_recurring_task(
            'service-reminders',
            config.SCHEDULER_CONFIG['service_reminder_interval_ms'],
            self.run_service_reminders
        )
        self.schedule_recurring_task(
            'appointment-confirmations',
            config.SCHEDULER_CONFIG['appointment_confirmation_interval_ms'],
            self.run_appointment_confirmations
        )
        self.schedule_recurring_task(
            'invoice-reminders',
            config.SCHEDULER_CONFIG['invoice_reminder_interval_ms'],
            self.run_invoice_reminders
        )

    def stop(self):
        """Stop all scheduled tasks."""
        self.running = False
        self.intervals = []

    def schedule_recurring_task(self, name, interval_ms, task_fn):
        """Schedule a recurring task."""
        def run():
            # Run immediately on start
            self._safe_run(name, task_fn)

            # Then run on interval
            while self.running:
                time.sleep(interval_ms / 1000.0)
                if self.running:
                    self._safe_run(name, task_fn)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.intervals.append(thread)

    def _safe_run(self, name, task_fn):
        """Safely run a task, catching errors."""
        try:
            task_fn()
        except Exception as e:
            logger.error(f'Scheduled task {name} failed', err=e)

    def fetch_tenants(self):
        """Fetch all tenant IDs from the central database."""
        rows = query('SELECT tenant_id FROM tenant_configs')
        return [row['tenant_id'] for row in rows]

    def run_service_reminders(self):
        """Run service reminder sweep for all tenants."""
        tenants = self.fetch_tenants()
        for tenant_id in tenants:
            candidates = find_service_reminder_candidates(tenant_id)
            for candidate in candidates:
                if not candidate.get('email'):
                    continue

                full_name = ' '.join(filter(None, [
                    candidate.get('first_name'),
                    candidate.get('last_name')
                ]))
                model = candidate.get('model', 'equipment')

                body = (
                    f'Hi {full_name or "there"}, it has been almost two years since '
                    f'your {model} purchase. Schedule a 2-Year Tune-Up Special to keep '
                    f'it running at peak performance.'
                )

                insert_job(
                    tenant_id=tenant_id,
                    job_type='send_email',
                    payload={
                        'to': candidate['email'],
                        'subject': '2-Year Tune-Up Special',
                        'body': body,
                        'customer_id': candidate['customer_id']
                    },
                    source_reference=f'service_reminder_{tenant_id}_{candidate["customer_id"]}'
                )

        logger.info('Service reminder sweep completed')

    def run_appointment_confirmations(self):
        """Run appointment confirmation sweep for all tenants."""
        tenants = self.fetch_tenants()
        for tenant_id in tenants:
            appointments = find_appointments_within_window(tenant_id)
            for appt in appointments:
                if not appt.get('phone'):
                    continue

                scheduled_start = appt.get('scheduled_start')
                when = scheduled_start.strftime('%Y-%m-%d %H:%M') if scheduled_start else 'soon'
                first_name = appt.get('first_name', '')

                body = (
                    f'Hi {first_name}, this is a reminder of your service appointment '
                    f'scheduled for {when}. Reply YES to confirm or call us to reschedule.'
                )

                insert_job(
                    tenant_id=tenant_id,
                    job_type='send_sms',
                    payload={
                        'to': appt['phone'],
                        'body': body,
                        'customer_id': appt['customer_id']
                    },
                    source_reference=f'appointment_{tenant_id}_{appt["appointment_id"]}'
                )

        logger.info('Appointment confirmation sweep completed')

    def run_invoice_reminders(self):
        """Run invoice reminder sweep for all tenants."""
        tenants = self.fetch_tenants()
        for tenant_id in tenants:
            invoices = find_past_due_invoices(tenant_id)
            for invoice in invoices:
                if not invoice.get('email'):
                    continue

                first_name = invoice.get('first_name', 'there')
                invoice_id = invoice['invoice_id']
                due_date = invoice.get('due_date')
                balance = invoice.get('balance', 0)

                days_past_due = 0
                if due_date:
                    delta = datetime.now() - due_date
                    days_past_due = math.ceil(delta.total_seconds() / 86400)

                body = (
                    f'Hello {first_name}, invoice #{invoice_id} is now {days_past_due} '
                    f'days past due. Your outstanding balance is ${balance}. '
                    f'Please reply or log into your portal to pay.'
                )

                insert_job(
                    tenant_id=tenant_id,
                    job_type='send_email',
                    payload={
                        'to': invoice['email'],
                        'subject': 'Friendly invoice reminder',
                        'body': body,
                        'customer_id': invoice['customer_id']
                    },
                    source_reference=f'invoice_{tenant_id}_{invoice_id}'
                )

        logger.info('Invoice reminder sweep completed')
