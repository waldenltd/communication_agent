"""
Gmail Adapter - Interface for polling Gmail inbox via Gmail API.

This module provides OAuth-based Gmail access for:
- Fetching unread messages with query filtering
- Adding labels to track processed messages
- Marking messages as read
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import base64
import re

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.observability import info, warning, error as log_error


@dataclass
class GmailMessage:
    """Parsed Gmail message with relevant fields."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    body_text: str
    body_html: Optional[str] = None
    received_at: Optional[datetime] = None
    labels: List[str] = field(default_factory=list)


class GmailApiError(Exception):
    """Base exception for Gmail API errors."""
    pass


class GmailAuthenticationError(GmailApiError):
    """OAuth token expired or invalid."""
    pass


class GmailQuotaExceededError(GmailApiError):
    """API rate limit exceeded."""
    pass


class GmailMessageNotFoundError(GmailApiError):
    """Message ID not found (may have been deleted)."""
    pass


class GmailAdapter:
    """
    Gmail API client with OAuth token management.

    Handles authentication, message fetching, and label management.
    """

    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with OAuth credentials from tenant config.

        Required config keys:
            - gmail_client_id: OAuth client ID
            - gmail_client_secret: OAuth client secret
            - gmail_refresh_token: Refresh token for access
        """
        self.config = config
        self.credentials = None
        self.service = None
        self._label_cache: Dict[str, str] = {}

    def authenticate(self) -> bool:
        """
        Authenticate and refresh tokens if needed.

        Returns:
            True if authentication successful

        Raises:
            GmailAuthenticationError: If authentication fails
        """
        try:
            client_id = self.config.get('gmail_client_id')
            client_secret = self.config.get('gmail_client_secret')
            refresh_token = self.config.get('gmail_refresh_token')

            if not all([client_id, client_secret, refresh_token]):
                raise GmailAuthenticationError(
                    "Missing Gmail OAuth credentials (gmail_client_id, gmail_client_secret, gmail_refresh_token)"
                )

            self.credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=self.SCOPES
            )

            # Refresh to get a valid access token
            if not self.credentials.valid:
                self.credentials.refresh(Request())

            # Build the Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)

            info("Gmail API authenticated successfully")
            return True

        except Exception as e:
            log_error("Gmail authentication failed", err=str(e))
            raise GmailAuthenticationError(f"Authentication failed: {str(e)}")

    def fetch_unread_messages(
        self,
        query: Optional[str] = None,
        max_results: int = 10
    ) -> List[GmailMessage]:
        """
        Fetch unread messages matching query.

        Args:
            query: Gmail search query (e.g., "from:noreply@example.com subject:Contact")
            max_results: Maximum number of messages to fetch

        Returns:
            List of GmailMessage objects
        """
        if not self.service:
            self.authenticate()

        try:
            # Build query - always filter for unread inbox messages
            full_query = "is:unread in:inbox"
            if query:
                full_query = f"{full_query} {query}"

            # List messages matching query
            results = self.service.users().messages().list(
                userId='me',
                q=full_query,
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                return []

            # Fetch full details for each message
            gmail_messages = []
            for msg in messages:
                try:
                    full_message = self.get_message_details(msg['id'])
                    if full_message:
                        gmail_messages.append(full_message)
                except GmailMessageNotFoundError:
                    warning(f"Message {msg['id']} not found, may have been deleted")
                    continue

            info(f"Fetched {len(gmail_messages)} unread messages")
            return gmail_messages

        except HttpError as e:
            if e.resp.status == 429:
                raise GmailQuotaExceededError("Gmail API quota exceeded")
            raise GmailApiError(f"Failed to fetch messages: {str(e)}")

    def get_message_details(self, message_id: str) -> Optional[GmailMessage]:
        """
        Get full message content by ID.

        Args:
            message_id: Gmail message ID

        Returns:
            GmailMessage with parsed content
        """
        if not self.service:
            self.authenticate()

        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Parse headers
            headers = {h['name'].lower(): h['value'] for h in message['payload'].get('headers', [])}
            subject = headers.get('subject', '')
            from_header = headers.get('from', '')
            date_header = headers.get('date', '')

            # Extract sender email from "Name <email>" format
            sender_email = from_header
            sender_name = from_header
            email_match = re.search(r'<([^>]+)>', from_header)
            if email_match:
                sender_email = email_match.group(1)
                sender_name = from_header.split('<')[0].strip().strip('"')

            # Parse body
            body_text = ''
            body_html = None
            payload = message['payload']

            if 'parts' in payload:
                for part in payload['parts']:
                    body_text, body_html = self._extract_body_from_part(part, body_text, body_html)
            elif 'body' in payload and payload['body'].get('data'):
                mime_type = payload.get('mimeType', '')
                decoded = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
                if mime_type == 'text/html':
                    body_html = decoded
                else:
                    body_text = decoded

            # Parse date
            received_at = None
            if date_header:
                try:
                    from email.utils import parsedate_to_datetime
                    received_at = parsedate_to_datetime(date_header)
                except Exception:
                    pass

            return GmailMessage(
                message_id=message_id,
                thread_id=message.get('threadId', ''),
                subject=subject,
                sender=sender_name,
                sender_email=sender_email,
                body_text=body_text,
                body_html=body_html,
                received_at=received_at,
                labels=message.get('labelIds', [])
            )

        except HttpError as e:
            if e.resp.status == 404:
                raise GmailMessageNotFoundError(f"Message {message_id} not found")
            raise GmailApiError(f"Failed to get message details: {str(e)}")

    def _extract_body_from_part(
        self,
        part: Dict,
        body_text: str,
        body_html: Optional[str]
    ) -> tuple:
        """Recursively extract body text and HTML from message parts."""
        mime_type = part.get('mimeType', '')

        if 'parts' in part:
            for subpart in part['parts']:
                body_text, body_html = self._extract_body_from_part(subpart, body_text, body_html)
        elif part.get('body', {}).get('data'):
            decoded = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            if mime_type == 'text/plain' and not body_text:
                body_text = decoded
            elif mime_type == 'text/html' and not body_html:
                body_html = decoded

        return body_text, body_html

    def add_label(self, message_id: str, label_name: str) -> bool:
        """
        Add a label to a message (creates label if not exists).

        Args:
            message_id: Gmail message ID
            label_name: Label name (e.g., "yrp/processed")

        Returns:
            True if successful
        """
        if not self.service:
            self.authenticate()

        try:
            # Get or create label
            label_id = self._get_or_create_label(label_name)

            # Add label to message
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            return True

        except HttpError as e:
            log_error(f"Failed to add label {label_name} to message {message_id}", err=str(e))
            return False

    def mark_as_read(self, message_id: str) -> bool:
        """
        Mark message as read (remove UNREAD label).

        Args:
            message_id: Gmail message ID

        Returns:
            True if successful
        """
        if not self.service:
            self.authenticate()

        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True

        except HttpError as e:
            log_error(f"Failed to mark message {message_id} as read", err=str(e))
            return False

    def _get_or_create_label(self, label_name: str) -> str:
        """Get label ID, creating the label if it doesn't exist."""
        # Check cache first
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        try:
            # List all labels
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            for label in labels:
                if label['name'].lower() == label_name.lower():
                    self._label_cache[label_name] = label['id']
                    return label['id']

            # Create label if not found
            label_body = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }
            created = self.service.users().labels().create(
                userId='me',
                body=label_body
            ).execute()

            self._label_cache[label_name] = created['id']
            info(f"Created Gmail label: {label_name}")
            return created['id']

        except HttpError as e:
            raise GmailApiError(f"Failed to get/create label {label_name}: {str(e)}")

    def get_provider_name(self) -> str:
        """Return the name of this provider."""
        return 'gmail'
