"""
Persistence Tools

Tools for database operations - creating, updating, and querying records.
"""

from datetime import datetime, timedelta
from typing import Optional
import json

from src.db.central_db import query, execute
from src.jobs.job_repository import create_job, mark_job_complete, mark_job_failed
from src.logger import info, debug

from .base import Tool, ToolResult, ToolParameter, ToolCategory


class CreateCommunicationJobTool(Tool):
    """Create a new communication job in the queue."""

    def __init__(self):
        super().__init__(
            name="create_communication_job",
            description="Create a new job in the communication_jobs queue for later processing",
            category=ToolCategory.PERSISTENCE,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
                ToolParameter(
                    name="job_type",
                    type="string",
                    description="Type of job to create",
                    required=True,
                    enum=["send_email", "send_sms", "notify_customer"],
                ),
                ToolParameter(
                    name="payload",
                    type="object",
                    description="Job payload with required parameters for the job type",
                    required=True,
                ),
                ToolParameter(
                    name="process_after",
                    type="string",
                    description="Optional delay - process after this timestamp (ISO format)",
                    required=False,
                ),
                ToolParameter(
                    name="source_reference",
                    type="string",
                    description="Optional reference ID to prevent duplicate jobs",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        job_type: str,
        payload: dict,
        process_after: str = None,
        source_reference: str = None,
    ) -> ToolResult:
        try:
            # Add source reference to payload if provided
            if source_reference:
                payload["source_reference"] = source_reference

            # Parse process_after if provided
            delay_until = None
            if process_after:
                delay_until = datetime.fromisoformat(process_after.replace("Z", "+00:00"))

            job_id = create_job(
                tenant_id=tenant_id,
                job_type=job_type,
                payload=payload,
                process_after=delay_until,
            )

            info("Created communication job",
                 job_id=job_id, tenant_id=tenant_id, job_type=job_type)

            return ToolResult(
                success=True,
                data={
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "job_type": job_type,
                    "status": "pending",
                },
                side_effects=[f"Created job {job_id} in queue"],
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


class UpdateJobStatusTool(Tool):
    """Update the status of a communication job."""

    def __init__(self):
        super().__init__(
            name="update_job_status",
            description="Update the status of an existing communication job",
            category=ToolCategory.PERSISTENCE,
            parameters=[
                ToolParameter(
                    name="job_id",
                    type="integer",
                    description="The job ID to update",
                    required=True,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description="New status for the job",
                    required=True,
                    enum=["complete", "failed", "cancelled"],
                ),
                ToolParameter(
                    name="reason",
                    type="string",
                    description="Reason for the status change",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        job_id: int,
        status: str,
        reason: str = None,
    ) -> ToolResult:
        try:
            if status == "complete":
                mark_job_complete(job_id, reason or "Completed successfully")
            elif status == "failed":
                mark_job_failed(job_id, reason or "Failed")
            else:
                # Handle other statuses with direct SQL
                execute("""
                    UPDATE communication_jobs
                    SET status = %(status)s, last_error = %(reason)s
                    WHERE id = %(job_id)s
                """, {"job_id": job_id, "status": status, "reason": reason})

            info("Updated job status", job_id=job_id, status=status)

            return ToolResult(
                success=True,
                data={
                    "job_id": job_id,
                    "status": status,
                },
                side_effects=[f"Job {job_id} status changed to {status}"],
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


class UpdateQueueItemStatusTool(Tool):
    """Update the status of a communication queue item."""

    def __init__(self):
        super().__init__(
            name="update_queue_item_status",
            description="Update the status of an item in the communication_queue",
            category=ToolCategory.PERSISTENCE,
            parameters=[
                ToolParameter(
                    name="item_id",
                    type="string",
                    description="The queue item ID (UUID)",
                    required=True,
                ),
                ToolParameter(
                    name="status",
                    type="string",
                    description="New status for the item",
                    required=True,
                    enum=["pending", "processing", "sent", "failed", "cancelled"],
                ),
                ToolParameter(
                    name="external_message_id",
                    type="string",
                    description="External provider message ID (for tracking)",
                    required=False,
                ),
                ToolParameter(
                    name="error_details",
                    type="object",
                    description="Error details if status is failed",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        item_id: str,
        status: str,
        external_message_id: str = None,
        error_details: dict = None,
    ) -> ToolResult:
        try:
            sql = """
                UPDATE communication_queue
                SET status = %(status)s
            """
            params = {"item_id": item_id, "status": status}

            if status == "sent":
                sql += ", sent_at = NOW()"

            if external_message_id:
                sql += ", external_message_id = %(external_message_id)s"
                params["external_message_id"] = external_message_id

            if error_details:
                sql += ", error_details = %(error_details)s, retry_count = retry_count + 1"
                params["error_details"] = json.dumps(error_details)

            sql += " WHERE id = %(item_id)s"

            execute(sql, params)

            info("Updated queue item status", item_id=item_id, status=status)

            return ToolResult(
                success=True,
                data={
                    "item_id": item_id,
                    "status": status,
                },
                side_effects=[f"Queue item {item_id} status changed to {status}"],
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


class CheckJobExistsTool(Tool):
    """Check if a job already exists for a given reference."""

    def __init__(self):
        super().__init__(
            name="check_job_exists",
            description="Check if a communication job already exists for a source reference (prevents duplicates)",
            category=ToolCategory.PERSISTENCE,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
                ToolParameter(
                    name="source_reference",
                    type="string",
                    description="The source reference to check",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str, source_reference: str) -> ToolResult:
        try:
            sql = """
                SELECT id, status, created_at
                FROM communication_jobs
                WHERE tenant_id = %(tenant_id)s
                  AND payload->>'source_reference' = %(source_reference)s
                LIMIT 1
            """
            rows = query(sql, {
                "tenant_id": tenant_id,
                "source_reference": source_reference,
            })

            if rows:
                return ToolResult(
                    success=True,
                    data={
                        "exists": True,
                        "job_id": rows[0]["id"],
                        "status": rows[0]["status"],
                        "created_at": str(rows[0]["created_at"]),
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    data={
                        "exists": False,
                    }
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


class SaveAgentContextTool(Tool):
    """Save agent context for resumption in next cycle."""

    def __init__(self):
        super().__init__(
            name="save_agent_context",
            description="Save agent session state and context summary for the next processing cycle",
            category=ToolCategory.PERSISTENCE,
            parameters=[
                ToolParameter(
                    name="job_id",
                    type="string",
                    description="The agent job ID",
                    required=True,
                ),
                ToolParameter(
                    name="context_summary",
                    type="string",
                    description="Summary of current progress for next session hydration",
                    required=True,
                ),
                ToolParameter(
                    name="session_state",
                    type="object",
                    description="Current session state to persist",
                    required=False,
                ),
                ToolParameter(
                    name="reschedule_seconds",
                    type="integer",
                    description="Reschedule job to run after this many seconds",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        job_id: str,
        context_summary: str,
        session_state: dict = None,
        reschedule_seconds: int = None,
    ) -> ToolResult:
        try:
            sql = """
                UPDATE agent_jobs
                SET context_summary = %(context_summary)s
            """
            params = {
                "job_id": job_id,
                "context_summary": context_summary,
            }

            if session_state:
                sql += ", session_state = %(session_state)s"
                params["session_state"] = json.dumps(session_state)

            if reschedule_seconds:
                process_after = datetime.utcnow() + timedelta(seconds=reschedule_seconds)
                sql += ", process_after = %(process_after)s, status = 'pending'"
                params["process_after"] = process_after

            sql += " WHERE id = %(job_id)s"

            execute(sql, params)

            info("Saved agent context",
                 job_id=job_id,
                 rescheduled=reschedule_seconds is not None)

            return ToolResult(
                success=True,
                data={
                    "job_id": job_id,
                    "context_saved": True,
                    "rescheduled": reschedule_seconds is not None,
                },
                side_effects=[f"Context saved for job {job_id}"],
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


# Factory function to register all persistence tools
def register_persistence_tools(registry):
    """Register all persistence tools with the given registry."""
    registry.register(CreateCommunicationJobTool())
    registry.register(UpdateJobStatusTool())
    registry.register(UpdateQueueItemStatusTool())
    registry.register(CheckJobExistsTool())
    registry.register(SaveAgentContextTool())
