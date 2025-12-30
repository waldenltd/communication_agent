"""
Job Bridge

Bridges legacy communication_jobs to Level 2 Agent jobs.
Allows gradual migration from legacy job processing to autonomous agent processing.
"""

from typing import Optional
from datetime import datetime

from src.db.central_db import query
from src.logger import info, debug

from .context_manager import ContextManager


# Goal templates for converting legacy job types to agent goals
JOB_TYPE_GOALS = {
    "send_email": {
        "goal": "Send an email to {to} with subject '{subject}'",
        "checklist": [
            "Validate recipient email address",
            "Check tenant email configuration",
            "Send the email via configured provider",
            "Verify delivery status",
        ],
    },
    "send_sms": {
        "goal": "Send an SMS to {to}",
        "checklist": [
            "Validate recipient phone number",
            "Check tenant Twilio configuration",
            "Check quiet hours status",
            "Send the SMS via Twilio",
            "Verify delivery status",
        ],
    },
    "notify_customer": {
        "goal": "Notify customer {customer_id} about: {subject}",
        "checklist": [
            "Fetch customer contact information",
            "Check customer contact preferences",
            "Check do-not-disturb status",
            "Determine best communication channel",
            "Send notification via chosen channel",
            "Record notification result",
        ],
    },
    "process_queue_item": {
        "goal": "Process communication queue item {item_id} ({event_type})",
        "checklist": [
            "Load queue item details",
            "Generate personalized content using AI",
            "Fetch any required attachments (PDF)",
            "Send communication via appropriate channel",
            "Update queue item status",
        ],
    },
    "service_reminder": {
        "goal": "Send 2-year service reminder to customer {customer_id} for {model}",
        "checklist": [
            "Verify customer contact information",
            "Check customer hasn't been contacted recently",
            "Generate personalized service reminder content",
            "Send email with service offer",
            "Record reminder sent",
        ],
    },
    "appointment_confirmation": {
        "goal": "Send appointment confirmation to {customer_name} for {scheduled_start}",
        "checklist": [
            "Verify appointment details",
            "Check customer phone number available",
            "Check quiet hours",
            "Send SMS confirmation",
            "Mark confirmation as sent",
        ],
    },
    "invoice_reminder": {
        "goal": "Send payment reminder for invoice {invoice_id} (${balance} past due)",
        "checklist": [
            "Verify invoice is still unpaid",
            "Check customer contact information",
            "Calculate days past due",
            "Generate polite reminder content",
            "Send email reminder",
            "Record reminder sent",
        ],
    },
}


class JobBridge:
    """
    Bridges legacy job processing to Level 2 Agent.

    Provides methods to:
    - Convert legacy jobs to agent jobs
    - Create agent jobs from scheduler events
    - Monitor migration progress
    """

    def __init__(self):
        self.context_manager = ContextManager()

    def convert_legacy_job(self, legacy_job: dict) -> Optional[str]:
        """
        Convert a legacy communication_job to an agent_job.

        Args:
            legacy_job: Dict with id, tenant_id, job_type, payload, etc.

        Returns:
            New agent job ID, or None if conversion not supported
        """
        job_type = legacy_job.get("job_type")
        payload = legacy_job.get("payload", {})
        tenant_id = legacy_job.get("tenant_id")

        if job_type not in JOB_TYPE_GOALS:
            debug(f"No agent template for job type: {job_type}")
            return None

        template = JOB_TYPE_GOALS[job_type]

        # Format goal with payload values
        try:
            goal = template["goal"].format(**payload)
        except KeyError:
            # Fallback if payload doesn't have all template vars
            goal = f"{job_type}: {payload}"

        # Create agent job
        agent_job_id = self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type="communication",
            goal=goal,
            checklist=template["checklist"],
            source_job_id=legacy_job.get("id"),
            source_reference=payload.get("source_reference"),
        )

        info(f"Converted legacy job to agent job",
             legacy_job_id=legacy_job.get("id"),
             agent_job_id=agent_job_id,
             job_type=job_type)

        return agent_job_id

    def create_queue_processing_job(
        self,
        tenant_id: str,
        queue_item_id: str,
        event_type: str,
        recipient_email: str,
    ) -> str:
        """
        Create an agent job to process a communication queue item.
        """
        template = JOB_TYPE_GOALS["process_queue_item"]
        goal = template["goal"].format(item_id=queue_item_id, event_type=event_type)

        return self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type="communication",
            goal=goal,
            checklist=template["checklist"],
            source_reference=f"queue:{queue_item_id}",
        )

    def create_service_reminder_job(
        self,
        tenant_id: str,
        customer_id: str,
        customer_email: str,
        customer_name: str,
        model: str,
        serial_number: str = None,
    ) -> str:
        """
        Create an agent job for a 2-year service reminder.
        """
        template = JOB_TYPE_GOALS["service_reminder"]
        goal = template["goal"].format(customer_id=customer_id, model=model)

        job_id = self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type="communication",
            goal=goal,
            checklist=template["checklist"],
            source_reference=f"service_reminder:{customer_id}:{model}",
        )

        # Store additional context in session state
        if job_id:
            from .context_manager import SessionState
            session = self.context_manager.load_session(job_id)
            if session:
                session.set_variable("customer_id", customer_id)
                session.set_variable("customer_email", customer_email)
                session.set_variable("customer_name", customer_name)
                session.set_variable("model", model)
                session.set_variable("serial_number", serial_number)
                self.context_manager.save_session(session)

        return job_id

    def create_appointment_confirmation_job(
        self,
        tenant_id: str,
        appointment_id: str,
        customer_id: str,
        customer_name: str,
        customer_phone: str,
        scheduled_start: str,
    ) -> str:
        """
        Create an agent job for appointment confirmation.
        """
        template = JOB_TYPE_GOALS["appointment_confirmation"]
        goal = template["goal"].format(
            customer_name=customer_name,
            scheduled_start=scheduled_start,
        )

        job_id = self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type="communication",
            goal=goal,
            checklist=template["checklist"],
            source_reference=f"appt_confirm:{appointment_id}",
        )

        if job_id:
            session = self.context_manager.load_session(job_id)
            if session:
                session.set_variable("appointment_id", appointment_id)
                session.set_variable("customer_id", customer_id)
                session.set_variable("customer_name", customer_name)
                session.set_variable("customer_phone", customer_phone)
                session.set_variable("scheduled_start", scheduled_start)
                self.context_manager.save_session(session)

        return job_id

    def create_invoice_reminder_job(
        self,
        tenant_id: str,
        invoice_id: str,
        customer_id: str,
        customer_email: str,
        customer_name: str,
        balance: float,
        due_date: str,
    ) -> str:
        """
        Create an agent job for invoice payment reminder.
        """
        template = JOB_TYPE_GOALS["invoice_reminder"]
        goal = template["goal"].format(invoice_id=invoice_id, balance=balance)

        job_id = self.context_manager.create_job(
            tenant_id=tenant_id,
            job_type="communication",
            goal=goal,
            checklist=template["checklist"],
            source_reference=f"invoice_reminder:{invoice_id}",
        )

        if job_id:
            session = self.context_manager.load_session(job_id)
            if session:
                session.set_variable("invoice_id", invoice_id)
                session.set_variable("customer_id", customer_id)
                session.set_variable("customer_email", customer_email)
                session.set_variable("customer_name", customer_name)
                session.set_variable("balance", balance)
                session.set_variable("due_date", due_date)
                self.context_manager.save_session(session)

        return job_id

    def get_migration_stats(self) -> dict:
        """
        Get statistics on job migration progress.
        """
        # Count legacy jobs
        legacy_result = query("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'complete') as complete,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM communication_jobs
        """)

        # Count agent jobs
        agent_result = query("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE status = 'resolved') as resolved,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE source_job_id IS NOT NULL) as converted
            FROM agent_jobs
        """)

        legacy = legacy_result[0] if legacy_result else {}
        agent = agent_result[0] if agent_result else {}

        return {
            "legacy_jobs": {
                "total": legacy.get("total", 0),
                "pending": legacy.get("pending", 0),
                "complete": legacy.get("complete", 0),
                "failed": legacy.get("failed", 0),
            },
            "agent_jobs": {
                "total": agent.get("total", 0),
                "pending": agent.get("pending", 0),
                "in_progress": agent.get("in_progress", 0),
                "resolved": agent.get("resolved", 0),
                "failed": agent.get("failed", 0),
                "converted_from_legacy": agent.get("converted", 0),
            },
        }


# Global instance
_bridge: Optional[JobBridge] = None


def get_job_bridge() -> JobBridge:
    """Get or create the global job bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = JobBridge()
    return _bridge
