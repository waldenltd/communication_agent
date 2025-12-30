"""
Email Service - Factory and Facade

This module provides a simple interface for sending emails without
knowing which adapter is being used. It handles adapter selection
and provides a clean API for the rest of the application.
"""

from typing import Dict, Any, Optional, List
from src.providers.email_adapter import EmailAdapter, EmailMessage, EmailResponse, EmailAttachment
from src.providers.sendgrid_adapter import SendGridAdapter
from src.providers.resend_adapter import ResendAdapter
from src import logger


class EmailService:
    """
    Email service that manages adapters and provides a unified interface.

    This is the main class that business logic should use to send emails.
    It automatically selects the appropriate adapter based on configuration.
    """

    # Registry of available adapters
    ADAPTERS = {
        'sendgrid': SendGridAdapter,
        'resend': ResendAdapter
    }

    def __init__(self, provider: str = 'sendgrid'):
        """
        Initialize email service with specified provider.

        Args:
            provider: Name of email provider ('sendgrid', 'resend', etc.)
        """
        self.provider = provider.lower()
        self.adapter = self._get_adapter(self.provider)

    def _get_adapter(self, provider: str) -> EmailAdapter:
        """
        Get the appropriate adapter for the provider.

        Args:
            provider: Provider name

        Returns:
            EmailAdapter instance

        Raises:
            ValueError: If provider is not supported
        """
        adapter_class = self.ADAPTERS.get(provider)
        if not adapter_class:
            available = ', '.join(self.ADAPTERS.keys())
            raise ValueError(
                f'Unsupported email provider: {provider}. '
                f'Available providers: {available}'
            )

        return adapter_class()

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        config: Dict[str, Any],
        from_email: Optional[str] = None,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[List[EmailAttachment]] = None
    ) -> EmailResponse:
        """
        Send an email using the configured provider.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text email body
            config: Provider configuration (API keys, etc.)
            from_email: Optional sender email
            html_body: Optional HTML body
            reply_to: Optional reply-to address
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            attachments: Optional list of email attachments

        Returns:
            EmailResponse with send result
        """
        message = EmailMessage(
            to=to,
            subject=subject,
            body=body,
            from_email=from_email,
            html_body=html_body,
            reply_to=reply_to,
            cc=cc,
            bcc=bcc,
            attachments=attachments
        )

        logger.info(
            f'Sending email via {self.adapter.get_provider_name()}',
            to=to,
            subject=subject
        )

        response = self.adapter.send_email(message, config)

        if response.success:
            logger.info(
                f'Email sent successfully via {self.adapter.get_provider_name()}',
                message_id=response.message_id,
                to=to
            )
        else:
            logger.error(
                f'Email send failed via {self.adapter.get_provider_name()}',
                error=response.error,
                to=to
            )

        return response

    @classmethod
    def register_adapter(cls, provider: str, adapter_class: type):
        """
        Register a new email adapter.

        This allows adding custom adapters at runtime.

        Args:
            provider: Provider name (e.g., 'custom_provider')
            adapter_class: Class that implements EmailAdapter
        """
        if not issubclass(adapter_class, EmailAdapter):
            raise TypeError(f'{adapter_class} must implement EmailAdapter')

        cls.ADAPTERS[provider.lower()] = adapter_class
        logger.info(f'Registered email adapter: {provider}')


def create_email_service(config: Dict[str, Any]) -> EmailService:
    """
    Factory function to create EmailService from configuration.

    This checks the config to determine which provider to use.

    Args:
        config: Tenant configuration

    Returns:
        EmailService instance configured with appropriate provider

    Example:
        >>> config = {'email_provider': 'resend', 'resend_key': 'xxx'}
        >>> service = create_email_service(config)
        >>> response = service.send_email(to='user@example.com', ...)
    """
    # Determine provider from config
    # Priority: explicit 'email_provider' setting, then check which keys exist
    provider = config.get('email_provider')

    if not provider:
        # Auto-detect based on which keys are present
        if config.get('resend_key'):
            provider = 'resend'
        elif config.get('sendgrid_key'):
            provider = 'sendgrid'
        else:
            # Default to sendgrid for backward compatibility
            provider = 'sendgrid'
            logger.warn('No email provider configured, defaulting to SendGrid')

    return EmailService(provider=provider)
