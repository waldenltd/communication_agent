"""
Email Adapter Pattern - Interface and Implementations

This module defines the contract (interface) that all email providers must implement,
making it easy to switch between vendors like SendGrid, Resend, etc.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class EmailMessage:
    """Standard email message format used across all adapters."""
    to: str
    subject: str
    body: str
    from_email: Optional[str] = None
    html_body: Optional[str] = None
    reply_to: Optional[str] = None
    cc: Optional[list[str]] = None
    bcc: Optional[list[str]] = None


@dataclass
class EmailResponse:
    """Standard response format from email providers."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    raw_response: Optional[Any] = None


class EmailAdapter(ABC):
    """
    Abstract base class (interface) for email providers.

    Any email provider implementation must extend this class
    and implement the send_email method.
    """

    @abstractmethod
    def send_email(self, message: EmailMessage, config: Dict[str, Any]) -> EmailResponse:
        """
        Send an email using the provider's API.

        Args:
            message: EmailMessage object containing email details
            config: Provider-specific configuration (API keys, etc.)

        Returns:
            EmailResponse object with send result

        Raises:
            Exception: If send fails (implementations should catch and return error in EmailResponse)
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the name of this email provider."""
        pass
