"""
Perception Tools

Tools for observing the current state of the system.
These are the "eyes" of the agent - they gather information
without modifying state.
"""

from datetime import datetime
from typing import Optional

from src.db.central_db import query
from src.db.tenant_data_gateway import (
    get_tenant_config,
    fetch_tenant_customer_contact,
    get_contact_preference,
    find_service_reminder_candidates,
    find_appointments_within_window,
    find_past_due_invoices,
    query_tenant_db,
)
from src.logger import debug

from .base import Tool, ToolResult, ToolParameter, ToolCategory, FunctionTool


class CheckPendingJobsTool(Tool):
    """Check for pending jobs in the communication queue."""

    def __init__(self):
        super().__init__(
            name="check_pending_jobs",
            description="Check the number and types of pending communication jobs for a tenant",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID to check jobs for",
                    required=True,
                ),
                ToolParameter(
                    name="job_type",
                    type="string",
                    description="Optional filter by job type (send_email, send_sms, notify_customer)",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of jobs to return (default 10)",
                    required=False,
                    default=10,
                ),
            ],
        )

    def execute(self, tenant_id: str, job_type: str = None, limit: int = 10) -> ToolResult:
        sql = """
            SELECT id, job_type, status, created_at, process_after, retry_count
            FROM communication_jobs
            WHERE tenant_id = %(tenant_id)s
              AND status = 'pending'
        """
        params = {"tenant_id": tenant_id, "limit": limit}

        if job_type:
            sql += " AND job_type = %(job_type)s"
            params["job_type"] = job_type

        sql += " ORDER BY process_after LIMIT %(limit)s"

        try:
            rows = query(sql, params)
            return ToolResult(
                success=True,
                data={
                    "count": len(rows),
                    "jobs": [dict(r) for r in rows],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CheckQueueItemsTool(Tool):
    """Check items in the communication queue."""

    def __init__(self):
        super().__init__(
            name="check_queue_items",
            description="Check pending items in the communication_queue table for event-driven processing",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID to check queue for",
                    required=True,
                ),
                ToolParameter(
                    name="event_type",
                    type="string",
                    description="Optional filter by event type (work_order_receipt, service_reminder, etc.)",
                    required=False,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description="Filter by status (pending, processing, sent, failed)",
                    required=False,
                    default="pending",
                    enum=["pending", "processing", "sent", "failed"],
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of items to return (default 20)",
                    required=False,
                    default=20,
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        event_type: str = None,
        status: str = "pending",
        limit: int = 20,
    ) -> ToolResult:
        sql = """
            SELECT id, event_type, communication_type, recipient_address,
                   subject, status, retry_count, created_at
            FROM communication_queue
            WHERE tenant_id = %(tenant_id)s
              AND status = %(status)s
        """
        params = {"tenant_id": tenant_id, "status": status, "limit": limit}

        if event_type:
            sql += " AND event_type = %(event_type)s"
            params["event_type"] = event_type

        sql += " ORDER BY created_at LIMIT %(limit)s"

        try:
            rows = query(sql, params)
            return ToolResult(
                success=True,
                data={
                    "count": len(rows),
                    "items": [dict(r) for r in rows],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GetCustomerContextTool(Tool):
    """Get customer contact information and preferences."""

    def __init__(self):
        super().__init__(
            name="get_customer_context",
            description="Fetch customer contact details, preferences, and do-not-disturb status",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
                ToolParameter(
                    name="customer_id",
                    type="string",
                    description="The customer ID to look up",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str, customer_id: str) -> ToolResult:
        try:
            customer = fetch_tenant_customer_contact(tenant_id, customer_id)
            if not customer:
                return ToolResult(
                    success=False,
                    error=f"Customer {customer_id} not found for tenant {tenant_id}",
                    suggested_action="Verify customer_id is correct",
                )

            preference = get_contact_preference(tenant_id, customer_id)

            return ToolResult(
                success=True,
                data={
                    "customer_id": customer_id,
                    "email": customer.get("email"),
                    "phone": customer.get("phone"),
                    "contact_preference": preference,
                    "do_not_disturb_until": str(customer.get("do_not_disturb_until"))
                    if customer.get("do_not_disturb_until")
                    else None,
                    "can_contact": preference != "do_not_contact",
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CheckQuietHoursTool(Tool):
    """Check if current time falls within tenant's quiet hours."""

    def __init__(self):
        super().__init__(
            name="check_quiet_hours",
            description="Check if current time is within tenant's quiet hours (no outbound communications)",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID to check quiet hours for",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str) -> ToolResult:
        try:
            config = get_tenant_config(tenant_id)
            quiet_start = config.get("quiet_hours_start")
            quiet_end = config.get("quiet_hours_end")

            if not quiet_start or not quiet_end:
                return ToolResult(
                    success=True,
                    data={
                        "in_quiet_hours": False,
                        "quiet_hours_configured": False,
                    }
                )

            # Parse quiet hours (format: "HH:MM")
            now = datetime.utcnow().time()
            start_time = datetime.strptime(quiet_start, "%H:%M").time()
            end_time = datetime.strptime(quiet_end, "%H:%M").time()

            # Handle overnight quiet hours (e.g., 21:00 - 08:00)
            if start_time > end_time:
                in_quiet = now >= start_time or now < end_time
            else:
                in_quiet = start_time <= now < end_time

            return ToolResult(
                success=True,
                data={
                    "in_quiet_hours": in_quiet,
                    "quiet_hours_configured": True,
                    "quiet_start": quiet_start,
                    "quiet_end": quiet_end,
                    "current_time": now.strftime("%H:%M"),
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GetTenantConfigTool(Tool):
    """Get tenant configuration details."""

    def __init__(self):
        super().__init__(
            name="get_tenant_config",
            description="Fetch tenant configuration including messaging providers and settings",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str) -> ToolResult:
        try:
            config = get_tenant_config(tenant_id)

            # Return safe subset (no secrets)
            return ToolResult(
                success=True,
                data={
                    "tenant_id": tenant_id,
                    "has_twilio": bool(config.get("twilio_sid")),
                    "has_sendgrid": bool(config.get("sendgrid_key")),
                    "has_resend": bool(config.get("resend_key")),
                    "email_provider": config.get("email_provider", "auto"),
                    "quiet_hours_start": config.get("quiet_hours_start"),
                    "quiet_hours_end": config.get("quiet_hours_end"),
                    "company_name": config.get("company_name"),
                    "has_dms_connection": bool(config.get("dms_connection_string")),
                }
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                suggested_action="Check if tenant_id exists in the system",
            )


class FindServiceReminderCandidatesTool(Tool):
    """Find customers due for 2-year service reminders."""

    def __init__(self):
        super().__init__(
            name="find_service_reminder_candidates",
            description="Find customers with equipment purchases 23-25 months ago who need service reminders",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str) -> ToolResult:
        try:
            candidates = find_service_reminder_candidates(tenant_id)
            return ToolResult(
                success=True,
                data={
                    "count": len(candidates),
                    "candidates": [dict(c) for c in candidates],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FindUpcomingAppointmentsTool(Tool):
    """Find appointments scheduled in the next 24-25 hours."""

    def __init__(self):
        super().__init__(
            name="find_upcoming_appointments",
            description="Find appointments scheduled 24-25 hours from now that need confirmation",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str) -> ToolResult:
        try:
            appointments = find_appointments_within_window(tenant_id)
            return ToolResult(
                success=True,
                data={
                    "count": len(appointments),
                    "appointments": [dict(a) for a in appointments],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FindPastDueInvoicesTool(Tool):
    """Find invoices that are 30+ days past due."""

    def __init__(self):
        super().__init__(
            name="find_past_due_invoices",
            description="Find invoices that are 30+ days past due with outstanding balances",
            category=ToolCategory.PERCEPTION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str) -> ToolResult:
        try:
            invoices = find_past_due_invoices(tenant_id)
            return ToolResult(
                success=True,
                data={
                    "count": len(invoices),
                    "invoices": [dict(i) for i in invoices],
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# Factory function to register all perception tools
def register_perception_tools(registry):
    """Register all perception tools with the given registry."""
    registry.register(CheckPendingJobsTool())
    registry.register(CheckQueueItemsTool())
    registry.register(GetCustomerContextTool())
    registry.register(CheckQuietHoursTool())
    registry.register(GetTenantConfigTool())
    registry.register(FindServiceReminderCandidatesTool())
    registry.register(FindUpcomingAppointmentsTool())
    registry.register(FindPastDueInvoicesTool())
