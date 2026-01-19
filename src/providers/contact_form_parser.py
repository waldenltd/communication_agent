"""
Contact Form Parser - Parse website contact form emails into structured data.

Handles the Year Round Power contact form format:
- First Name
- Last Name
- Email
- Phone
- Are you buying or repairing?
- What type of equipment? (may include additional message)
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass

from src.observability import info, warning


@dataclass
class ContactFormData:
    """Parsed contact form data."""
    first_name: str
    last_name: str
    email: str
    phone: str
    inquiry_type: str  # 'buying' or 'repairing'
    equipment_type: str
    message: str
    location: Optional[str] = None
    raw_email_id: Optional[str] = None

    @property
    def full_name(self) -> str:
        """Return full name."""
        return f"{self.first_name} {self.last_name}".strip()


class ContactFormParseError(Exception):
    """Failed to parse contact form email."""
    pass


class ContactFormValidationError(Exception):
    """Parsed data failed validation."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


class ContactFormParser:
    """
    Parse contact form emails into structured data.

    Handles various field label formats and extracts additional
    context like location from the message.
    """

    # Regex patterns for extracting fields
    # Each field has multiple possible label patterns
    FIELD_PATTERNS = {
        'first_name': [
            r'First\s*Name[:\s]*([^\n]+)',
        ],
        'last_name': [
            r'Last\s*Name[:\s]*([^\n]+)',
        ],
        'email': [
            r'Email[:\s]*(\S+@\S+)',
            r'E-mail[:\s]*(\S+@\S+)',
        ],
        'phone': [
            r'Phone[:\s]*([\d\-\(\)\s\.]+)',
            r'Phone\s*Number[:\s]*([\d\-\(\)\s\.]+)',
            r'Tel[:\s]*([\d\-\(\)\s\.]+)',
        ],
        'inquiry_type': [
            r'(?:Are\s*you\s*)?[Bb]uying\s*or\s*[Rr]epairing[?:\s]*([^\n]+)',
            r'Inquiry\s*Type[:\s]*([^\n]+)',
        ],
        'equipment_type': [
            r'(?:What\s*)?[Tt]ype\s*of\s*equipment[?:\s]*([^\n]+(?:\n(?![A-Z][a-z]*\s*[A-Z][a-z]*:)[^\n]*)*)',
            r'Equipment[:\s]*([^\n]+)',
        ],
    }

    # Common location patterns to extract from message
    LOCATION_PATTERNS = [
        r'I\s*live\s*in\s*([A-Za-z\s]+?)(?:\s*[-,.]|\s*-|\s*are)',
        r'located\s*in\s*([A-Za-z\s]+?)(?:\s*[-,.]|\s*and)',
        r'from\s*([A-Za-z\s]+?)(?:\s*[-,.]|\s*and)',
        r'in\s*([A-Za-z]+)\s*(?:area|town|city)',
    ]

    def parse(self, email_body: str, message_id: Optional[str] = None) -> ContactFormData:
        """
        Parse email body into ContactFormData.

        Args:
            email_body: Raw email body text
            message_id: Optional Gmail message ID for tracking

        Returns:
            ContactFormData with extracted fields

        Raises:
            ContactFormParseError: If email doesn't match expected format
        """
        # Clean up the email body
        body = self._clean_body(email_body)

        # Extract each field
        first_name = self._extract_field(body, 'first_name')
        last_name = self._extract_field(body, 'last_name')
        email = self._extract_field(body, 'email')
        phone = self._extract_field(body, 'phone')
        inquiry_type_raw = self._extract_field(body, 'inquiry_type')
        equipment_raw = self._extract_field(body, 'equipment_type')

        # Validate required fields
        if not first_name or not email:
            raise ContactFormParseError(
                f"Missing required fields. Found: first_name={first_name}, email={email}"
            )

        # Normalize inquiry type
        inquiry_type = self._normalize_inquiry_type(inquiry_type_raw or '')

        # Parse equipment type and message
        equipment_type, message = self._parse_equipment_and_message(equipment_raw or '')

        # Try to extract location from message
        location = self._extract_location(message)

        data = ContactFormData(
            first_name=first_name.strip() if first_name else '',
            last_name=last_name.strip() if last_name else '',
            email=email.strip() if email else '',
            phone=self._clean_phone(phone) if phone else '',
            inquiry_type=inquiry_type,
            equipment_type=equipment_type,
            message=message,
            location=location,
            raw_email_id=message_id
        )

        info(f"Parsed contact form: {data.full_name}, {data.inquiry_type}, {data.equipment_type}")
        return data

    def _clean_body(self, body: str) -> str:
        """Clean and normalize email body text."""
        # Remove HTML tags if present
        body = re.sub(r'<[^>]+>', ' ', body)
        # Normalize whitespace but preserve newlines
        body = re.sub(r'[ \t]+', ' ', body)
        # Remove excessive newlines
        body = re.sub(r'\n{3,}', '\n\n', body)
        return body.strip()

    def _extract_field(self, body: str, field_name: str) -> Optional[str]:
        """Extract a field value using configured patterns."""
        patterns = self.FIELD_PATTERNS.get(field_name, [])

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value

        return None

    def _normalize_inquiry_type(self, raw_value: str) -> str:
        """
        Normalize inquiry type to 'buying' or 'repairing'.

        Handles various formats:
        - "Buying", "buying", "BUYING" -> "buying"
        - "Repairing", "repair", "REPAIR" -> "repairing"
        """
        value = raw_value.lower().strip()

        if 'repair' in value:
            return 'repairing'
        elif 'buy' in value or 'purchas' in value or 'new' in value:
            return 'buying'
        else:
            # Default based on keywords
            warning(f"Unknown inquiry type: {raw_value}, defaulting to 'repairing'")
            return 'repairing'

    def _parse_equipment_and_message(self, raw: str) -> Tuple[str, str]:
        """
        Parse equipment field which may contain both type and message.

        Example input:
        "snow blower. I live in Glastonbury - are you able to pick up..."

        Returns:
            Tuple of (equipment_type, additional_message)
        """
        if not raw:
            return '', ''

        # Split on first sentence-ending punctuation followed by space and capital
        # or on ". I" pattern which is common
        split_patterns = [
            r'([^.!?]+[.!?])\s*([A-Z].*)',  # After period + capital letter
            r'([^.]+)\.\s*(I\s.*)',  # "equipment. I..."
        ]

        for pattern in split_patterns:
            match = re.match(pattern, raw.strip(), re.DOTALL)
            if match:
                equipment = match.group(1).strip().rstrip('.')
                message = match.group(2).strip()
                return equipment, message

        # No clear split - treat entire thing as equipment type
        # (short responses like just "lawn mower")
        return raw.strip(), ''

    def _extract_location(self, message: str) -> Optional[str]:
        """Try to extract location from message text."""
        if not message:
            return None

        for pattern in self.LOCATION_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up common trailing words
                location = re.sub(r'\s*(and|or|the|to|for)$', '', location, flags=re.IGNORECASE)
                if location and len(location) > 2:
                    return location.title()

        return None

    def _clean_phone(self, phone: str) -> str:
        """Clean and format phone number."""
        if not phone:
            return ''
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        # Format as XXX-XXX-XXXX if 10 digits
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"{digits[1:4]}-{digits[4:7]}-{digits[7:]}"
        return digits

    def is_valid_contact_form(self, data: ContactFormData) -> Tuple[bool, List[str]]:
        """
        Validate parsed data.

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        if not data.first_name:
            errors.append("Missing first name")

        if not data.email:
            errors.append("Missing email")
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', data.email):
            errors.append(f"Invalid email format: {data.email}")

        if not data.inquiry_type:
            errors.append("Missing inquiry type")

        if not data.equipment_type:
            errors.append("Missing equipment type")

        return len(errors) == 0, errors

    def is_contact_form_email(self, subject: str, body: str) -> bool:
        """
        Check if an email appears to be a contact form submission.

        Args:
            subject: Email subject line
            body: Email body text

        Returns:
            True if this looks like a contact form email
        """
        # Check subject for common patterns
        subject_patterns = [
            r'contact.*form',
            r'form.*submission',
            r'website.*inquiry',
            r'new.*inquiry',
            r'contact\s*us',
        ]

        subject_lower = subject.lower()
        for pattern in subject_patterns:
            if re.search(pattern, subject_lower):
                return True

        # Check body for field patterns
        required_fields = ['first_name', 'email', 'equipment_type']
        found_fields = 0

        for field in required_fields:
            if self._extract_field(body, field):
                found_fields += 1

        # Need at least 2 of 3 required fields
        return found_fields >= 2
