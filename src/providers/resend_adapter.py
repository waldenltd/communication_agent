"""
Resend Email Adapter Implementation

Concrete implementation of the EmailAdapter for Resend.
"""

from typing import Dict, Any
import requests
from src.providers.email_adapter import EmailAdapter, EmailMessage, EmailResponse
from src import logger


class ResendAdapter(EmailAdapter):
    """Resend implementation of the EmailAdapter interface."""

    RESEND_API_URL = "https://api.resend.com/emails"

    def get_provider_name(self) -> str:
        return "Resend"

    def send_email(self, message: EmailMessage, config: Dict[str, Any]) -> EmailResponse:
        """
        Send email via Resend API.

        Args:
            message: EmailMessage with email details
            config: Must contain 'resend_key' and optionally 'resend_from'

        Returns:
            EmailResponse with send result
        """
        try:
            # Validate config
            api_key = config.get('resend_key')
            if not api_key:
                return EmailResponse(
                    success=False,
                    error='Missing Resend API key in config'
                )

            # Determine from address
            from_addr = message.from_email or config.get('resend_from') or 'no-reply@example.com'

            # Build Resend payload
            payload = {
                'from': from_addr,
                'to': [message.to],
                'subject': message.subject,
                'text': message.body
            }

            # Add HTML if provided
            if message.html_body:
                payload['html'] = message.html_body

            # Add CC recipients
            if message.cc:
                payload['cc'] = message.cc

            # Add BCC recipients
            if message.bcc:
                payload['bcc'] = message.bcc

            # Add reply-to
            if message.reply_to:
                payload['reply_to'] = message.reply_to

            # Send via Resend API
            logger.debug(f'Sending email via Resend to {message.to}')

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                self.RESEND_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )

            # Parse response
            response_data = response.json() if response.text else {}

            # Check for errors
            if response.status_code >= 400:
                error_message = response_data.get('message', 'Unknown error')
                return EmailResponse(
                    success=False,
                    error=f'Resend returned status {response.status_code}: {error_message}',
                    status_code=response.status_code,
                    raw_response=response_data
                )

            # Extract message ID
            message_id = response_data.get('id')

            return EmailResponse(
                success=True,
                message_id=message_id,
                status_code=response.status_code,
                raw_response=response_data
            )

        except requests.RequestException as e:
            logger.error(f'Resend API request failed: {str(e)}', err=e)
            return EmailResponse(
                success=False,
                error=f'Failed to connect to Resend API: {str(e)}'
            )
        except Exception as e:
            logger.error(f'Resend email send failed: {str(e)}', err=e)
            return EmailResponse(
                success=False,
                error=f'Failed to send via Resend: {str(e)}'
            )
