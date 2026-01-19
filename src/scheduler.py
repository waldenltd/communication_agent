import threading
import time
import math
from datetime import datetime
from src import logger, config
from src.db.central_db import query
from src.db.tenant_data_gateway import (
    find_service_reminder_candidates,
    find_appointments_within_window,
    find_past_due_invoices,
    get_tenant_config
)
from src.jobs.job_repository import insert_job
from src.jobs.handlers.process_queue import process_communication_queue
from src.jobs.handlers.poll_gmail_inbox import poll_gmail_inbox
from src.jobs.handlers.seven_day_checkin import create_seven_day_checkin_jobs
from src.jobs.handlers.post_service_survey import create_post_service_survey_jobs
from src.jobs.handlers.annual_tuneup import create_annual_tuneup_jobs
from src.jobs.handlers.seasonal_reminder import create_spring_reminder_jobs, create_fall_reminder_jobs
from src.jobs.handlers.ghost_customer import create_ghost_customer_jobs
from src.jobs.handlers.anniversary_offer import create_anniversary_offer_jobs
from src.jobs.handlers.warranty_expiration import create_warranty_expiration_jobs
from src.jobs.handlers.trade_in_alert import create_trade_in_alert_jobs
from src.jobs.handlers.first_service_alert import create_first_service_alert_jobs
from src.jobs.handlers.usage_service_alert import create_usage_service_alert_jobs


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
        self.schedule_recurring_task(
            'communication-queue-processor',
            config.SCHEDULER_CONFIG.get('queue_processor_interval_ms', 30000),  # 30 seconds default
            self.run_queue_processor
        )

        # Gmail inbox polling for contact form auto-responses
        gmail_interval = getattr(config, 'GMAIL_POLL_INTERVAL_MS', 60000)
        if gmail_interval > 0:
            self.schedule_recurring_task(
                'gmail-inbox-poller',
                gmail_interval,
                self.run_gmail_inbox_poll
            )

        # New communication jobs - daily scheduled tasks
        # These run once per day (24 hours = 86400000 ms)
        daily_interval = config.SCHEDULER_CONFIG.get('daily_job_interval_ms', 86400000)

        self.schedule_recurring_task(
            'seven-day-checkin',
            daily_interval,
            self.run_seven_day_checkin
        )
        self.schedule_recurring_task(
            'post-service-survey',
            daily_interval,
            self.run_post_service_survey
        )
        self.schedule_recurring_task(
            'annual-tuneup',
            daily_interval,
            self.run_annual_tuneup
        )

        # Ghost customer detection - weekly (7 days = 604800000 ms)
        weekly_interval = config.SCHEDULER_CONFIG.get('weekly_job_interval_ms', 604800000)
        self.schedule_recurring_task(
            'ghost-customer-winback',
            weekly_interval,
            self.run_ghost_customer_winback
        )

        # Seasonal reminders - check daily but only create jobs in March/October
        self.schedule_recurring_task(
            'seasonal-reminders',
            daily_interval,
            self.run_seasonal_reminders
        )

        # Anniversary offers - daily
        self.schedule_recurring_task(
            'anniversary-offer',
            daily_interval,
            self.run_anniversary_offer
        )

        # Warranty expiration warnings - daily
        self.schedule_recurring_task(
            'warranty-expiration',
            daily_interval,
            self.run_warranty_expiration
        )

        # Trade-in alerts - monthly (30 days)
        monthly_interval = config.SCHEDULER_CONFIG.get('monthly_job_interval_ms', 30 * 24 * 60 * 60 * 1000)
        self.schedule_recurring_task(
            'trade-in-alert',
            monthly_interval,
            self.run_trade_in_alert
        )

        # Usage-based service alerts - weekly (check for equipment needing service)
        self.schedule_recurring_task(
            'first-service-alert',
            weekly_interval,
            self.run_first_service_alert
        )
        self.schedule_recurring_task(
            'usage-service-alert',
            weekly_interval,
            self.run_usage_service_alert
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
        """Fetch all active tenant IDs from the central database."""
        rows = query("SELECT tenant_id FROM tenants WHERE status = 'Active'")
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

    def run_queue_processor(self):
        """Process pending items from the communication_queue with AI-generated content."""
        tenants = self.fetch_tenants()
        total_processed = 0

        for tenant_id in tenants:
            processed = process_communication_queue(tenant_id)
            total_processed += processed

        if total_processed > 0:
            logger.info('Communication queue processing completed', processed=total_processed)

    def run_gmail_inbox_poll(self):
        """Poll Gmail inbox for contact form emails and create auto-response jobs."""
        tenants = self.fetch_tenants()
        total_processed = 0

        for tenant_id in tenants:
            try:
                tenant_config = get_tenant_config(tenant_id)
                if not tenant_config.get('gmail_enabled'):
                    continue

                processed = poll_gmail_inbox(tenant_id, tenant_config)
                total_processed += processed
            except Exception as e:
                logger.error(f'Gmail poll failed for tenant {tenant_id}', err=e)

        if total_processed > 0:
            logger.info('Gmail inbox poll completed', processed=total_processed)

    def run_seven_day_checkin(self):
        """Send check-in emails to customers 7 days after equipment purchase."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_seven_day_checkin_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Seven day check-in failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Seven day check-in sweep completed', jobs_created=total_jobs)

    def run_post_service_survey(self):
        """Send survey emails to customers 48-72 hours after service pickup."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_post_service_survey_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Post-service survey failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Post-service survey sweep completed', jobs_created=total_jobs)

    def run_annual_tuneup(self):
        """Send tune-up reminders 14 days before equipment purchase anniversary."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_annual_tuneup_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Annual tune-up reminder failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Annual tune-up sweep completed', jobs_created=total_jobs)

    def run_ghost_customer_winback(self):
        """Send win-back emails to customers with no activity in 12+ months."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_ghost_customer_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Ghost customer win-back failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Ghost customer win-back sweep completed', jobs_created=total_jobs)

    def run_seasonal_reminders(self):
        """Send seasonal preparation reminders (spring in March, fall in October)."""
        current_month = datetime.now().month
        tenants = self.fetch_tenants()
        total_jobs = 0

        # Spring reminders in March
        if current_month == 3:
            for tenant_id in tenants:
                try:
                    jobs_created = create_spring_reminder_jobs(tenant_id)
                    total_jobs += jobs_created
                except Exception as e:
                    logger.error(f'Spring reminder failed for tenant {tenant_id}', err=e)

            if total_jobs > 0:
                logger.info('Spring reminder sweep completed', jobs_created=total_jobs)

        # Fall/winterization reminders in October
        elif current_month == 10:
            for tenant_id in tenants:
                try:
                    jobs_created = create_fall_reminder_jobs(tenant_id)
                    total_jobs += jobs_created
                except Exception as e:
                    logger.error(f'Fall reminder failed for tenant {tenant_id}', err=e)

            if total_jobs > 0:
                logger.info('Fall reminder sweep completed', jobs_created=total_jobs)

    def run_anniversary_offer(self):
        """Send anniversary offer emails 7 days before equipment purchase anniversary."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_anniversary_offer_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Anniversary offer failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Anniversary offer sweep completed', jobs_created=total_jobs)

    def run_warranty_expiration(self):
        """Send warranty expiration warnings 30 days before warranty expires."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_warranty_expiration_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Warranty expiration failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Warranty expiration sweep completed', jobs_created=total_jobs)

    def run_trade_in_alert(self):
        """Send trade-in suggestions for old equipment with high repair history."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_trade_in_alert_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Trade-in alert failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Trade-in alert sweep completed', jobs_created=total_jobs)

    def run_first_service_alert(self):
        """Send first service alerts when equipment reaches first service hours threshold."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_first_service_alert_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'First service alert failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('First service alert sweep completed', jobs_created=total_jobs)

    def run_usage_service_alert(self):
        """Send usage-based service alerts when equipment crosses service interval thresholds."""
        tenants = self.fetch_tenants()
        total_jobs = 0

        for tenant_id in tenants:
            try:
                jobs_created = create_usage_service_alert_jobs(tenant_id)
                total_jobs += jobs_created
            except Exception as e:
                logger.error(f'Usage service alert failed for tenant {tenant_id}', err=e)

        if total_jobs > 0:
            logger.info('Usage service alert sweep completed', jobs_created=total_jobs)
