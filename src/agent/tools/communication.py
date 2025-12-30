"""
Communication Tools

Tools for sending outbound communications (email, SMS).
These perform actual messaging operations with side effects.
"""

from typing import Optional

from src.db.tenant_data_gateway import get_tenant_config, fetch_tenant_customer_contact
from src.providers.messaging import send_sms_via_twilio, send_email_via_sendgrid
from src.logger import info, error

from .base import Tool, ToolResult, ToolParameter, ToolCategory


class SendEmailTool(Tool):
    """Send an email using the tenant's configured email provider."""

    def __init__(self):
        super().__init__(
            name="send_email",
            description="Send an email to a recipient using the tenant's email provider (SendGrid or Resend)",
            category=ToolCategory.COMMUNICATION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID for provider configuration",
                    required=True,
                ),
                ToolParameter(
                    name="to",
                    type="string",
                    description="Recipient email address",
                    required=True,
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    description="Email subject line",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="Email body content (plain text)",
                    required=True,
                ),
                ToolParameter(
                    name="from_email",
                    type="string",
                    description="Optional sender email (overrides tenant default)",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        to: str,
        subject: str,
        body: str,
        from_email: str = None,
    ) -> ToolResult:
        try:
            config = get_tenant_config(tenant_id)

            response = send_email_via_sendgrid(
                tenant_config=config,
                to=to,
                subject=subject,
                body=body,
                from_email=from_email,
            )

            info("Email sent successfully", tenant_id=tenant_id, to=to)

            return ToolResult(
                success=True,
                data={
                    "message_id": getattr(response, "message_id", None),
                    "to": to,
                    "subject": subject,
                },
                side_effects=[f"Email sent to {to}"],
            )

        except Exception as e:
            error("Email send failed", tenant_id=tenant_id, to=to, err=e)
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason="Email provider error",
                suggested_action="Check email provider configuration and recipient address",
            )


class SendSmsTool(Tool):
    """Send an SMS using Twilio."""

    def __init__(self):
        super().__init__(
            name="send_sms",
            description="Send an SMS message via Twilio",
            category=ToolCategory.COMMUNICATION,
            parameters=[
                ToolParameter(
                    name="tenant_id",
                    type="string",
                    description="The tenant ID for Twilio configuration",
                    required=True,
                ),
                ToolParameter(
                    name="to",
                    type="string",
                    description="Recipient phone number (E.164 format preferred)",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="SMS message content",
                    required=True,
                ),
                ToolParameter(
                    name="from_number",
                    type="string",
                    description="Optional sender number (overrides tenant default)",
                    required=False,
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        to: str,
        body: str,
        from_number: str = None,
    ) -> ToolResult:
        try:
            config = get_tenant_config(tenant_id)

            message_sid = send_sms_via_twilio(
                tenant_config=config,
                to=to,
                body=body,
                from_number=from_number or config.get("twilio_from_number"),
            )

            info("SMS sent successfully", tenant_id=tenant_id, to=to, sid=message_sid)

            return ToolResult(
                success=True,
                data={
                    "message_sid": message_sid,
                    "to": to,
                },
                side_effects=[f"SMS sent to {to}"],
            )

        except Exception as e:
            error("SMS send failed", tenant_id=tenant_id, to=to, err=e)
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason="Twilio error",
                suggested_action="Check Twilio credentials and phone number format",
            )


class NotifyCustomerTool(Tool):
    """
    Send a notification to a customer using their preferred channel.

    Automatically determines the best communication channel based on
    customer preferences and available contact information.
    """

    def __init__(self):
        super().__init__(
            name="notify_customer",
            description="Send a notification to a customer using their preferred channel (SMS or email)",
            category=ToolCategory.COMMUNICATION,
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
                    description="The customer ID to notify",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="Notification message content",
                    required=True,
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    description="Email subject (used if email is the channel)",
                    required=False,
                    default="Notification",
                ),
                ToolParameter(
                    name="preferred_channel",
                    type="string",
                    description="Override channel preference (sms or email)",
                    required=False,
                    enum=["sms", "email"],
                ),
                ToolParameter(
                    name="fallback_channel",
                    type="string",
                    description="Fallback channel if preferred is unavailable",
                    required=False,
                    enum=["sms", "email"],
                ),
            ],
        )

    def execute(
        self,
        tenant_id: str,
        customer_id: str,
        body: str,
        subject: str = "Notification",
        preferred_channel: str = None,
        fallback_channel: str = None,
    ) -> ToolResult:
        try:
            # Get customer info
            customer = fetch_tenant_customer_contact(tenant_id, customer_id)
            if not customer:
                return ToolResult(
                    success=False,
                    error=f"Customer {customer_id} not found",
                    suggested_action="Verify customer_id is correct",
                )

            # Check contact preference
            preference = customer.get("contact_preference")
            if preference == "do_not_contact":
                return ToolResult(
                    success=True,
                    data={
                        "skipped": True,
                        "reason": "Customer opted out of communications",
                    },
                )

            # Determine channel
            channel = (
                preferred_channel
                or preference
                or ("sms" if customer.get("phone") else "email")
                or fallback_channel
            )

            # Validate channel requirements
            if channel == "sms" and not customer.get("phone"):
                if fallback_channel == "email" and customer.get("email"):
                    channel = "email"
                else:
                    return ToolResult(
                        success=False,
                        error="Customer has no phone number for SMS",
                        suggested_action="Use email channel or update customer phone",
                    )

            if channel == "email" and not customer.get("email"):
                if fallback_channel == "sms" and customer.get("phone"):
                    channel = "sms"
                else:
                    return ToolResult(
                        success=False,
                        error="Customer has no email address",
                        suggested_action="Use SMS channel or update customer email",
                    )

            config = get_tenant_config(tenant_id)

            # Send via chosen channel
            if channel == "sms":
                message_sid = send_sms_via_twilio(
                    tenant_config=config,
                    to=customer["phone"],
                    body=body,
                )
                info("Customer notified via SMS",
                     tenant_id=tenant_id, customer_id=customer_id)
                return ToolResult(
                    success=True,
                    data={
                        "channel": "sms",
                        "message_sid": message_sid,
                        "to": customer["phone"],
                    },
                    side_effects=[f"SMS sent to customer {customer_id}"],
                )
            else:
                send_email_via_sendgrid(
                    tenant_config=config,
                    to=customer["email"],
                    subject=subject,
                    body=body,
                )
                info("Customer notified via email",
                     tenant_id=tenant_id, customer_id=customer_id)
                return ToolResult(
                    success=True,
                    data={
                        "channel": "email",
                        "to": customer["email"],
                        "subject": subject,
                    },
                    side_effects=[f"Email sent to customer {customer_id}"],
                )

        except Exception as e:
            error("Customer notification failed",
                  tenant_id=tenant_id, customer_id=customer_id, err=e)
            return ToolResult(
                success=False,
                error=str(e),
                needs_retry=True,
                retry_reason="Communication error",
            )


# Factory function to register all communication tools
def register_communication_tools(registry):
    """Register all communication tools with the given registry."""
    registry.register(SendEmailTool())
    registry.register(SendSmsTool())
    registry.register(NotifyCustomerTool())
