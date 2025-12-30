"""
Agent Scheduler

Proactive task scheduler for the Level 2 Agent.
Replaces the legacy scheduler with agent-native job creation.
"""

import threading
import time
from datetime import datetime
from typing import Optional

from src.config import SCHEDULER_CONFIG
from src.db.central_db import query
from src.db.tenant_data_gateway import (
    get_tenant_config,
    find_service_reminder_candidates,
    find_appointments_within_window,
    find_past_due_invoices,
)
from src.logger import info, error, debug, warn

from .job_bridge import get_job_bridge
from .metrics import get_metrics


class AgentScheduler:
    """
    Proactive scheduler for the Level 2 Agent.

    Scans tenant data and creates agent jobs for:
    - 2-year service reminders
    - 24-hour appointment confirmations
    - Past-due invoice reminders
    - Communication queue processing
    """

    def __init__(self):
        self.bridge = get_job_bridge()
        self._running = False
        self._threads: list[threading.Thread] = []
        self._metrics = get_metrics()

        # Configuration
        self.service_reminder_hour = SCHEDULER_CONFIG.get('service_reminder_hour_utc', 14)
        self.invoice_reminder_hour = SCHEDULER_CONFIG.get('invoice_reminder_hour_utc', 13)
        self.appt_interval_ms = SCHEDULER_CONFIG.get('appointment_confirmation_interval_ms', 3600000)
        self.queue_interval_ms = SCHEDULER_CONFIG.get('queue_processor_interval_ms', 30000)

    def start(self):
        """Start all scheduler threads."""
        if self._running:
            warn("Agent scheduler already running")
            return

        self._running = True
        info("Starting agent scheduler")

        # Start scheduler threads
        threads = [
            ("service_reminders", self._run_service_reminders),
            ("appointment_confirmations", self._run_appointment_confirmations),
            ("invoice_reminders", self._run_invoice_reminders),
            ("queue_processor", self._run_queue_processor),
        ]

        for name, target in threads:
            thread = threading.Thread(target=target, name=name, daemon=True)
            self._threads.append(thread)
            thread.start()
            debug(f"Started scheduler thread: {name}")

    def stop(self):
        """Stop all scheduler threads."""
        if not self._running:
            return

        info("Stopping agent scheduler")
        self._running = False

        # Wait for threads to finish
        for thread in self._threads:
            thread.join(timeout=5)

        self._threads.clear()
        info("Agent scheduler stopped")

    def _get_active_tenants(self) -> list[dict]:
        """Get all active tenants."""
        return query("""
            SELECT tenant_id, settings
            FROM tenants
            WHERE status = 'Active'
        """)

    def _run_service_reminders(self):
        """Run service reminder sweep hourly at configured hour."""
        while self._running:
            try:
                current_hour = datetime.utcnow().hour

                if current_hour == self.service_reminder_hour:
                    self._sweep_service_reminders()

                # Sleep until next hour
                self._sleep_until_next_hour()

            except Exception as e:
                error("Service reminder sweep failed", err=e)
                time.sleep(60)  # Back off on error

    def _run_appointment_confirmations(self):
        """Run appointment confirmation sweep at configured interval."""
        interval_seconds = self.appt_interval_ms / 1000

        while self._running:
            try:
                self._sweep_appointment_confirmations()
            except Exception as e:
                error("Appointment confirmation sweep failed", err=e)

            self._interruptible_sleep(interval_seconds)

    def _run_invoice_reminders(self):
        """Run invoice reminder sweep hourly at configured hour."""
        while self._running:
            try:
                current_hour = datetime.utcnow().hour

                if current_hour == self.invoice_reminder_hour:
                    self._sweep_invoice_reminders()

                # Sleep until next hour
                self._sleep_until_next_hour()

            except Exception as e:
                error("Invoice reminder sweep failed", err=e)
                time.sleep(60)

    def _run_queue_processor(self):
        """Run queue processor sweep at configured interval."""
        interval_seconds = self.queue_interval_ms / 1000

        while self._running:
            try:
                self._sweep_communication_queue()
            except Exception as e:
                error("Queue processor sweep failed", err=e)

            self._interruptible_sleep(interval_seconds)

    def _sweep_service_reminders(self):
        """Create agent jobs for customers due for service reminders."""
        info("Starting service reminder sweep")
        jobs_created = 0

        for tenant in self._get_active_tenants():
            tenant_id = tenant["tenant_id"]

            try:
                candidates = find_service_reminder_candidates(tenant_id)
                debug(f"Found {len(candidates)} service reminder candidates",
                      tenant_id=tenant_id)

                for customer in candidates:
                    # Check if job already exists
                    source_ref = f"service_reminder:{customer['customer_id']}:{customer.get('model', 'unknown')}"
                    existing = self._check_existing_job(source_ref)
                    if existing:
                        continue

                    job_id = self.bridge.create_service_reminder_job(
                        tenant_id=tenant_id,
                        customer_id=str(customer["customer_id"]),
                        customer_email=customer.get("email", ""),
                        customer_name=f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
                        model=customer.get("model", "equipment"),
                        serial_number=customer.get("serial_number"),
                    )

                    if job_id:
                        jobs_created += 1

            except Exception as e:
                error(f"Service reminder sweep failed for tenant",
                      tenant_id=tenant_id, err=e)

        info(f"Service reminder sweep complete", jobs_created=jobs_created)
        self._metrics.record_scheduler_sweep("service_reminder", jobs_created)

    def _sweep_appointment_confirmations(self):
        """Create agent jobs for appointments needing confirmation."""
        debug("Starting appointment confirmation sweep")
        jobs_created = 0

        for tenant in self._get_active_tenants():
            tenant_id = tenant["tenant_id"]

            try:
                appointments = find_appointments_within_window(tenant_id)

                for appt in appointments:
                    if not appt.get("phone"):
                        continue  # Skip if no phone number

                    source_ref = f"appt_confirm:{appt['appointment_id']}"
                    existing = self._check_existing_job(source_ref)
                    if existing:
                        continue

                    job_id = self.bridge.create_appointment_confirmation_job(
                        tenant_id=tenant_id,
                        appointment_id=str(appt["appointment_id"]),
                        customer_id=str(appt["customer_id"]),
                        customer_name=appt.get("first_name", "Customer"),
                        customer_phone=appt["phone"],
                        scheduled_start=str(appt.get("scheduled_start", "")),
                    )

                    if job_id:
                        jobs_created += 1

            except Exception as e:
                error(f"Appointment confirmation sweep failed for tenant",
                      tenant_id=tenant_id, err=e)

        if jobs_created:
            debug(f"Appointment confirmation sweep complete", jobs_created=jobs_created)
        self._metrics.record_scheduler_sweep("appointment_confirmation", jobs_created)

    def _sweep_invoice_reminders(self):
        """Create agent jobs for past-due invoices."""
        info("Starting invoice reminder sweep")
        jobs_created = 0

        for tenant in self._get_active_tenants():
            tenant_id = tenant["tenant_id"]

            try:
                invoices = find_past_due_invoices(tenant_id)
                debug(f"Found {len(invoices)} past-due invoices", tenant_id=tenant_id)

                for invoice in invoices:
                    source_ref = f"invoice_reminder:{invoice['invoice_id']}"
                    existing = self._check_existing_job(source_ref)
                    if existing:
                        continue

                    job_id = self.bridge.create_invoice_reminder_job(
                        tenant_id=tenant_id,
                        invoice_id=str(invoice["invoice_id"]),
                        customer_id=str(invoice["customer_id"]),
                        customer_email=invoice.get("email", ""),
                        customer_name=invoice.get("first_name", "Customer"),
                        balance=float(invoice.get("balance", 0)),
                        due_date=str(invoice.get("due_date", "")),
                    )

                    if job_id:
                        jobs_created += 1

            except Exception as e:
                error(f"Invoice reminder sweep failed for tenant",
                      tenant_id=tenant_id, err=e)

        info(f"Invoice reminder sweep complete", jobs_created=jobs_created)
        self._metrics.record_scheduler_sweep("invoice_reminder", jobs_created)

    def _sweep_communication_queue(self):
        """Create agent jobs for pending communication queue items."""
        # Get pending queue items
        items = query("""
            SELECT id, tenant_id, event_type, recipient_address, subject
            FROM communication_queue
            WHERE status = 'pending'
              AND communication_type = 'email'
            ORDER BY created_at
            LIMIT 50
        """)

        if not items:
            return

        debug(f"Found {len(items)} pending queue items")
        jobs_created = 0

        for item in items:
            source_ref = f"queue:{item['id']}"
            existing = self._check_existing_job(source_ref)
            if existing:
                continue

            recipient = item.get("recipient_address", {})
            if isinstance(recipient, str):
                import json
                recipient = json.loads(recipient)

            job_id = self.bridge.create_queue_processing_job(
                tenant_id=str(item["tenant_id"]),
                queue_item_id=str(item["id"]),
                event_type=item.get("event_type", "default"),
                recipient_email=recipient.get("email", ""),
            )

            if job_id:
                jobs_created += 1
                # Mark queue item as processing
                query("""
                    UPDATE communication_queue
                    SET status = 'processing'
                    WHERE id = %s
                """, [item["id"]])

        if jobs_created:
            debug(f"Queue processing jobs created", jobs_created=jobs_created)
        self._metrics.record_scheduler_sweep("queue_processing", jobs_created)

    def _check_existing_job(self, source_reference: str) -> bool:
        """Check if an agent job already exists for this source reference."""
        result = query("""
            SELECT 1 FROM agent_jobs
            WHERE source_reference = %s
              AND status IN ('pending', 'in_progress', 'resolved')
            LIMIT 1
        """, [source_reference])
        return len(result) > 0

    def _sleep_until_next_hour(self):
        """Sleep until the start of the next hour."""
        now = datetime.utcnow()
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        from datetime import timedelta
        next_hour += timedelta(hours=1)
        sleep_seconds = (next_hour - now).total_seconds()
        self._interruptible_sleep(sleep_seconds)

    def _interruptible_sleep(self, seconds: float):
        """Sleep that can be interrupted by stop()."""
        end_time = time.time() + seconds
        while self._running and time.time() < end_time:
            time.sleep(min(1.0, end_time - time.time()))


# Global instance
_scheduler: Optional[AgentScheduler] = None


def get_agent_scheduler() -> AgentScheduler:
    """Get or create the global agent scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AgentScheduler()
    return _scheduler


def start_agent_scheduler():
    """Start the global agent scheduler."""
    get_agent_scheduler().start()


def stop_agent_scheduler():
    """Stop the global agent scheduler."""
    if _scheduler:
        _scheduler.stop()
