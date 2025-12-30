"""
Processing Tools

Tools for transforming and analyzing data.
These perform computations and content generation.
"""

from typing import Optional

from src.providers.ai_content_generator import generate_email_content
from src.utils.pdf_fetcher import fetch_work_order_pdf, fetch_sales_receipt_pdf
from src.db.tenant_data_gateway import get_tenant_config, fetch_work_order_equipment
from src.logger import info, debug

from .base import Tool, ToolResult, ToolParameter, ToolCategory


class GenerateEmailContentTool(Tool):
    """Generate AI-powered email content based on event type."""

    def __init__(self):
        super().__init__(
            name="generate_email_content",
            description="Generate personalized email subject and body using AI based on event type and parameters",
            category=ToolCategory.PROCESSING,
            parameters=[
                ToolParameter(
                    name="event_type",
                    type="string",
                    description="Type of event triggering the email",
                    required=True,
                    enum=[
                        "work_order_receipt",
                        "sales_order_receipt",
                        "service_reminder",
                        "appointment_confirmation",
                        "invoice_reminder",
                        "estimate_followup",
                        "job_complete",
                        "default",
                    ],
                ),
                ToolParameter(
                    name="message_params",
                    type="object",
                    description="Parameters for email content (customer_name, work_order_number, etc.)",
                    required=True,
                ),
                ToolParameter(
                    name="recipient_address",
                    type="object",
                    description="Recipient info with email and optional name",
                    required=True,
                ),
                ToolParameter(
                    name="subject_override",
                    type="string",
                    description="Optional override for subject line (skips AI generation for subject)",
                    required=False,
                ),
                ToolParameter(
                    name="company_name",
                    type="string",
                    description="Company name to personalize content",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        event_type: str,
        message_params: dict,
        recipient_address: dict,
        subject_override: str = None,
        company_name: str = None,
    ) -> ToolResult:
        try:
            content = generate_email_content(
                event_type=event_type,
                message_params=message_params,
                recipient_address=recipient_address,
                subject_override=subject_override,
                company_name=company_name,
            )

            info("Generated email content",
                 event_type=event_type,
                 subject_length=len(content.get("subject", "")),
                 body_length=len(content.get("body", "")))

            return ToolResult(
                success=True,
                data={
                    "subject": content["subject"],
                    "body": content["body"],
                    "event_type": event_type,
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason="AI generation error",
                suggested_action="Check DEEPSEEK_API_KEY and try again",
            )


class FetchPdfAttachmentTool(Tool):
    """Fetch a PDF attachment from the tenant's API."""

    def __init__(self):
        super().__init__(
            name="fetch_pdf_attachment",
            description="Fetch a PDF file (work order or sales receipt) from the tenant's API for email attachment",
            category=ToolCategory.PROCESSING,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID for API configuration",
                    required=True,
                ),
                ToolParameter(
                    name="document_type",
                    type="string",
                    description="Type of document to fetch",
                    required=True,
                    enum=["work_order", "sales_receipt", "invoice"],
                ),
                ToolParameter(
                    name="document_id",
                    type="string",
                    description="The document ID or number to fetch",
                    required=True,
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        document_type: str,
        document_id: str,
    ) -> ToolResult:
        try:
            config = get_tenant_config(tenant_id)
            api_base_url = config.get("api_base_url")

            if not api_base_url:
                return ToolResult(
                    success=False,
                    error="Tenant has no API base URL configured",
                    suggested_action="Configure api_base_url in tenant settings",
                )

            # Fetch based on document type
            # Note: pdf_fetcher functions take (document_id, api_base_url)
            if document_type == "work_order":
                pdf_data = fetch_work_order_pdf(document_id, api_base_url)
                filename = f"WorkOrder_{document_id}.pdf"
            elif document_type in ("sales_receipt", "invoice"):
                pdf_data = fetch_sales_receipt_pdf(document_id, api_base_url)
                filename = f"Receipt_{document_id}.pdf"
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown document type: {document_type}",
                )

            if pdf_data:
                debug("Fetched PDF attachment",
                      document_type=document_type,
                      document_id=document_id,
                      size=len(pdf_data))

                return ToolResult(
                    success=True,
                    data={
                        "filename": filename,
                        "content": pdf_data,  # bytes
                        "content_type": "application/pdf",
                        "size": len(pdf_data),
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"PDF not found for {document_type} {document_id}",
                    suggested_action="Verify document ID exists in the system",
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason="PDF fetch error",
            )


class GetWorkOrderDetailsTool(Tool):
    """Get work order equipment details from the DMS."""

    def __init__(self):
        super().__init__(
            name="get_work_order_details",
            description="Fetch equipment and service details for a work order from the tenant's DMS",
            category=ToolCategory.PROCESSING,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID",
                    required=True,
                ),
                ToolParameter(
                    name="work_order_number",
                    type="string",
                    description="The work order number to look up",
                    required=True,
                ),
            ],
        )

    def execute(self, tenant_id: str, work_order_number: str) -> ToolResult:
        try:
            details = fetch_work_order_equipment(tenant_id, work_order_number)

            if details:
                return ToolResult(
                    success=True,
                    data=dict(details),
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Work order {work_order_number} not found",
                    suggested_action="Verify work order number is correct",
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


class CalculateDaysPastDueTool(Tool):
    """Calculate days past due for an invoice."""

    def __init__(self):
        super().__init__(
            name="calculate_days_past_due",
            description="Calculate the number of days an invoice is past its due date",
            category=ToolCategory.PROCESSING,
            parameters=[
                ToolParameter(
                    name="due_date",
                    type="string",
                    description="Invoice due date (ISO format: YYYY-MM-DD)",
                    required=True,
                ),
            ],
        )

    def execute(self, due_date: str) -> ToolResult:
        from datetime import datetime, date

        try:
            # Parse the due date
            if isinstance(due_date, str):
                due = datetime.fromisoformat(due_date.replace("Z", "+00:00")).date()
            elif isinstance(due_date, datetime):
                due = due_date.date()
            elif isinstance(due_date, date):
                due = due_date
            else:
                return ToolResult(
                    success=False,
                    error=f"Invalid due_date format: {due_date}",
                )

            today = date.today()
            days_past = (today - due).days

            return ToolResult(
                success=True,
                data={
                    "due_date": str(due),
                    "today": str(today),
                    "days_past_due": max(0, days_past),
                    "is_past_due": days_past > 0,
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )


# Factory function to register all processing tools
def register_processing_tools(registry):
    """Register all processing tools with the given registry."""
    registry.register(GenerateEmailContentTool())
    registry.register(FetchPdfAttachmentTool())
    registry.register(GetWorkOrderDetailsTool())
    registry.register(CalculateDaysPastDueTool())
