import threading
import time
from datetime import datetime, timedelta
from src import config, logger
from src.jobs.job_repository import (
    claim_pending_jobs,
    mark_job_complete,
    reschedule_job,
    mark_job_failed,
    insert_job
)
from src.db.tenant_data_gateway import get_tenant_config, find_fallback_email
from src.jobs.handlers.send_sms import handle_send_sms
from src.jobs.handlers.send_email import handle_send_email
from src.jobs.handlers.notify_customer import handle_notify_customer


JOB_HANDLERS = {
    'send_sms': handle_send_sms,
    'send_email': handle_send_email,
    'notify_customer': handle_notify_customer
}


def parse_time_to_minutes(time_string):
    """Parse HH:MM time string to minutes since midnight."""
    if not time_string:
        return None

    try:
        parts = time_string.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])

        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return None

        return hours * 60 + minutes
    except (ValueError, IndexError):
        return None


def is_within_quiet_hours(current_minutes, start, end):
    """Check if current time is within quiet hours."""
    if start is None or end is None:
        return False

    if start < end:
        return start <= current_minutes < end

    if start > end:
        return current_minutes >= start or current_minutes < end

    return False


class JobProcessor:
    def __init__(self, poll_interval_ms=None, max_concurrent_jobs=None):
        self.poll_interval_ms = poll_interval_ms or config.POLL_INTERVAL_MS
        self.max_concurrent_jobs = max_concurrent_jobs or config.MAX_CONCURRENT_JOBS
        self.active_jobs = 0
        self.active_jobs_lock = threading.Lock()
        self.timer = None
        self.running = False

    def start(self):
        """Start the job processor."""
        if self.timer:
            return

        self.running = True

        def tick_loop():
            # Initial tick
            self._safe_tick()

            while self.running:
                time.sleep(self.poll_interval_ms / 1000.0)
                self._safe_tick()

        self.timer = threading.Thread(target=tick_loop, daemon=True)
        self.timer.start()

    def stop(self):
        """Stop the job processor."""
        self.running = False
        if self.timer:
            self.timer = None

    def _safe_tick(self):
        """Safely execute a tick, catching any errors."""
        try:
            self.tick()
        except Exception as e:
            logger.error('Job polling tick failed', err=e)

    def tick(self):
        """Poll for jobs and process them."""
        with self.active_jobs_lock:
            if self.active_jobs >= self.max_concurrent_jobs:
                return

            available_slots = self.max_concurrent_jobs - self.active_jobs
            jobs = claim_pending_jobs(available_slots)

            if not jobs:
                return

            for job in jobs:
                self.active_jobs += 1
                thread = threading.Thread(
                    target=self._run_job_with_cleanup,
                    args=(job,),
                    daemon=True
                )
                thread.start()

    def _run_job_with_cleanup(self, job):
        """Run a job and ensure cleanup."""
        try:
            self.run_job(job)
        finally:
            with self.active_jobs_lock:
                self.active_jobs -= 1

    def run_job(self, job):
        """Execute a single job."""
        try:
            tenant_config = get_tenant_config(job['tenant_id'])
            quiet_hours_delay = self.get_quiet_hours_delay(job, tenant_config)

            if quiet_hours_delay:
                reschedule_job(
                    job_id=job['id'],
                    retry_count=job['retry_count'],
                    process_after=quiet_hours_delay,
                    last_error='Deferred for quiet hours',
                    status='pending'
                )
                logger.info(
                    'Deferred job due to quiet hours',
                    jobId=job['id'],
                    tenantId=job['tenant_id']
                )
                return

            handler = JOB_HANDLERS.get(job['job_type'])
            if not handler:
                raise Exception(f'Unsupported job type: {job["job_type"]}')

            result = handler(job, {
                'tenant_config': tenant_config,
                'logger': logger
            })

            reason = result.get('reason') if result and isinstance(result, dict) else None
            mark_job_complete(job['id'], reason)
            logger.info(
                'Job processed successfully',
                jobId=job['id'],
                type=job['job_type']
            )

        except Exception as e:
            self.handle_job_failure(job, e)

    def get_quiet_hours_delay(self, job, tenant_config):
        """Calculate if job should be delayed due to quiet hours."""
        if job['payload'].get('urgent'):
            return None

        start = parse_time_to_minutes(tenant_config.get('quiet_hours_start'))
        end = parse_time_to_minutes(tenant_config.get('quiet_hours_end'))

        if start is None or end is None:
            return None

        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute

        if not is_within_quiet_hours(current_minutes, start, end):
            return None

        # Calculate next allowed time
        next_allowed = now.replace(
            hour=end // 60,
            minute=end % 60,
            second=0,
            microsecond=0
        )

        if start > end:
            # Quiet hours wrap past midnight
            if current_minutes >= start:
                next_allowed += timedelta(days=1)
        elif current_minutes >= end:
            next_allowed += timedelta(days=1)

        if next_allowed <= now:
            next_allowed += timedelta(days=1)

        return next_allowed

    def handle_job_failure(self, job, error):
        """Handle job failure with retry logic."""
        logger.error(
            'Job processing failed',
            err=error,
            jobId=job['id'],
            jobType=job['job_type']
        )

        attempts = (job.get('retry_count', 0) or 0) + 1
        next_retry_at = datetime.now() + timedelta(minutes=config.RETRY_DELAY_MINUTES)

        if attempts < config.MAX_RETRIES:
            reschedule_job(
                job_id=job['id'],
                retry_count=attempts,
                process_after=next_retry_at,
                last_error=str(error),
                status='pending'
            )
            job['retry_count'] = attempts
            return

        if job['job_type'] == 'send_sms':
            if self.try_email_fallback(job, error):
                return

        mark_job_failed(job['id'], str(error))

    def try_email_fallback(self, job, error):
        """Try to create an email fallback for failed SMS."""
        customer_id = job['payload'].get('customer_id')
        if not customer_id:
            mark_job_failed(
                job['id'],
                f'SMS failed after retries: {str(error)}'
            )
            return True

        fallback_email = find_fallback_email(job['tenant_id'], customer_id)
        if not fallback_email:
            mark_job_failed(
                job['id'],
                f'SMS failed, no fallback email for customer {customer_id}'
            )
            return True

        payload = {
            'to': fallback_email,
            'subject': job['payload'].get('subject', 'SMS Fallback Notification'),
            'body': job['payload']['body'],
            'source_job_id': job['id'],
            'source_reference': f'sms_fallback_{job["id"]}'
        }

        insert_job(
            tenant_id=job['tenant_id'],
            job_type='send_email',
            payload=payload,
            source_reference=payload['source_reference']
        )

        mark_job_failed(
            job['id'],
            f'SMS failed but fallback email scheduled for {fallback_email}',
            'failed_fallback_email'
        )

        logger.warn(
            'Created fallback email job',
            jobId=job['id'],
            tenantId=job['tenant_id']
        )
        return True
