"""
SendGrid Email Adapter Implementation

Concrete implementation of the EmailAdapter for SendGrid.
"""

from typing import Dict, Any
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, Cc, Bcc
from src.providers.email_adapter import EmailAdapter, EmailMessage, EmailResponse
from src import logger


class SendGridAdapter(EmailAdapter):
    """SendGrid implementation of the EmailAdapter interface."""

    def get_provider_name(self) -> str:
        return "SendGrid"

    def send_email(self, message: EmailMessage, config: Dict[str, Any]) -> EmailResponse:
        """
        Send email via SendGrid API.

        Args:
            message: EmailMessage with email details
            config: Must contain 'sendgrid_key' and optionally 'sendgrid_from'

        Returns:
            EmailResponse with send result
        """
        try:
            # Validate config
            api_key = config.get('sendgrid_key')
            if not api_key:
                return EmailResponse(
                    success=False,
                    error='Missing SendGrid API key in config'
                )

            # Determine from address
            from_addr = message.from_email or config.get('sendgrid_from') or 'no-reply@example.com'

            # Build SendGrid Mail object
            mail = Mail(
                from_email=from_addr,
                to_emails=message.to,
                subject=message.subject,
                plain_text_content=message.body
            )

            # Add HTML if provided
            if message.html_body:
                mail.add_html_content(message.html_body)

            # Add CC recipients
            if message.cc:
                for cc_email in message.cc:
                    mail.add_cc(Cc(cc_email))

            # Add BCC recipients
            if message.bcc:
                for bcc_email in message.bcc:
                    mail.add_bcc(Bcc(bcc_email))

            # Add reply-to
            if message.reply_to:
                mail.reply_to = message.reply_to

            # Send via SendGrid
            logger.debug(f'Sending email via SendGrid to {message.to}')
            sg = SendGridAPIClient(api_key)
            response = sg.send(mail)

            # Check response
            if response.status_code >= 400:
                return EmailResponse(
                    success=False,
                    error=f'SendGrid returned status {response.status_code}',
                    status_code=response.status_code,
                    raw_response=response.body
                )

            # Extract message ID from headers if available
            message_id = response.headers.get('X-Message-Id')

            return EmailResponse(
                success=True,
                message_id=message_id,
                status_code=response.status_code,
                raw_response=response.body
            )

        except Exception as e:
            logger.error(f'SendGrid email send failed: {str(e)}', err=e)
            return EmailResponse(
                success=False,
                error=f'Failed to send via SendGrid: {str(e)}'
            )
