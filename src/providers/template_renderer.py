"""
Template Renderer Service

Loads and renders message templates from the database with variable substitution.
Supports optional AI enhancement for personalization.
"""

import re
from typing import Optional
from src import logger
from src.db.central_db import query


# In-memory cache for templates (tenant_id:event_type:comm_type -> template)
_template_cache = {}
_cache_ttl_seconds = 300  # 5 minutes


class RenderedMessage:
    """Container for rendered message content."""

    def __init__(self, subject: str, body_text: str, body_html: Optional[str] = None):
        self.subject = subject
        self.body_text = body_text
        self.body_html = body_html or body_text

    def to_dict(self) -> dict:
        return {
            'subject': self.subject,
            'body': self.body_text,
            'body_html': self.body_html
        }


class Template:
    """Represents a message template loaded from the database."""

    def __init__(self, row: dict):
        self.id = row.get('id')
        self.tenant_id = row.get('tenant_id')
        self.event_type = row.get('event_type')
        self.communication_type = row.get('communication_type', 'email')
        self.subject_template = row.get('subject_template', '')
        self.body_html_template = row.get('body_html_template', '')
        self.body_text_template = row.get('body_text_template', '')
        self.variables = row.get('variables') or {}
        self.description = row.get('description', '')
        self.ai_enhance = row.get('ai_enhance', False)
        self.ai_instructions = row.get('ai_instructions', '')
        self.is_active = row.get('is_active', True)
        self.version = row.get('version', 1)


def _get_cache_key(tenant_id: Optional[str], event_type: str, communication_type: str) -> str:
    """Generate a cache key for a template."""
    return f"{tenant_id or 'global'}:{event_type}:{communication_type}"


def clear_template_cache():
    """Clear the template cache."""
    global _template_cache
    _template_cache = {}
    logger.info('Template cache cleared')


def load_template(
    event_type: str,
    tenant_id: Optional[str] = None,
    communication_type: str = 'email'
) -> Optional[Template]:
    """
    Load a template from the database.

    First tries to find a tenant-specific template, then falls back to global default.

    Args:
        event_type: The event type (e.g., 'seven_day_checkin')
        tenant_id: Optional tenant ID for tenant-specific templates
        communication_type: 'email' or 'sms'

    Returns:
        Template object if found, None otherwise
    """
    # Check cache first
    cache_key = _get_cache_key(tenant_id, event_type, communication_type)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    # Try tenant-specific template first
    if tenant_id:
        rows = query(
            """
            SELECT *
            FROM message_templates
            WHERE tenant_id = %s
              AND event_type = %s
              AND communication_type = %s
              AND is_active = true
            LIMIT 1
            """,
            [tenant_id, event_type, communication_type]
        )

        if rows:
            template = Template(rows[0])
            _template_cache[cache_key] = template
            return template

    # Fall back to global default (tenant_id IS NULL)
    global_cache_key = _get_cache_key(None, event_type, communication_type)
    if global_cache_key in _template_cache:
        return _template_cache[global_cache_key]

    rows = query(
        """
        SELECT *
        FROM message_templates
        WHERE tenant_id IS NULL
          AND event_type = %s
          AND communication_type = %s
          AND is_active = true
        LIMIT 1
        """,
        [event_type, communication_type]
    )

    if rows:
        template = Template(rows[0])
        _template_cache[global_cache_key] = template
        return template

    return None


def _substitute_variables(template_text: str, variables: dict) -> str:
    """
    Substitute {{variable}} placeholders in template text.

    Args:
        template_text: Template string with {{variable}} placeholders
        variables: Dictionary of variable values

    Returns:
        String with variables substituted
    """
    if not template_text:
        return ''

    def replace_var(match):
        var_name = match.group(1).strip()
        value = variables.get(var_name, '')
        return str(value) if value else ''

    # Match {{variable_name}} pattern
    return re.sub(r'\{\{([^}]+)\}\}', replace_var, template_text)


def render(template: Template, variables: dict) -> RenderedMessage:
    """
    Render a template with the given variables.

    Args:
        template: Template object to render
        variables: Dictionary of variable values

    Returns:
        RenderedMessage with subject and body
    """
    # Substitute variables in all template parts
    subject = _substitute_variables(template.subject_template, variables)
    body_text = _substitute_variables(template.body_text_template, variables)
    body_html = _substitute_variables(template.body_html_template, variables)

    # Use text template as HTML if no HTML template provided
    if not body_html and body_text:
        # Convert plain text to basic HTML (preserve line breaks)
        body_html = body_text.replace('\n', '<br>\n')

    return RenderedMessage(
        subject=subject,
        body_text=body_text,
        body_html=body_html
    )


def render_template(
    event_type: str,
    variables: dict,
    tenant_id: Optional[str] = None,
    communication_type: str = 'email'
) -> Optional[RenderedMessage]:
    """
    Load and render a template in one step.

    Args:
        event_type: The event type (e.g., 'seven_day_checkin')
        variables: Dictionary of variable values
        tenant_id: Optional tenant ID for tenant-specific templates
        communication_type: 'email' or 'sms'

    Returns:
        RenderedMessage if template found, None otherwise
    """
    template = load_template(event_type, tenant_id, communication_type)
    if not template:
        return None

    return render(template, variables)


def get_template_variables(event_type: str, tenant_id: Optional[str] = None) -> dict:
    """
    Get the documented variables for a template.

    Args:
        event_type: The event type
        tenant_id: Optional tenant ID

    Returns:
        Dictionary of variable names and descriptions
    """
    template = load_template(event_type, tenant_id)
    if template:
        return template.variables or {}
    return {}


def should_ai_enhance(event_type: str, tenant_id: Optional[str] = None) -> bool:
    """
    Check if a template should be enhanced with AI.

    Args:
        event_type: The event type
        tenant_id: Optional tenant ID

    Returns:
        True if AI enhancement is enabled for this template
    """
    template = load_template(event_type, tenant_id)
    if template:
        return template.ai_enhance
    return False


def get_ai_instructions(event_type: str, tenant_id: Optional[str] = None) -> str:
    """
    Get AI enhancement instructions for a template.

    Args:
        event_type: The event type
        tenant_id: Optional tenant ID

    Returns:
        AI instructions string, or empty string if none
    """
    template = load_template(event_type, tenant_id)
    if template:
        return template.ai_instructions or ''
    return ''


def list_templates(tenant_id: Optional[str] = None, include_global: bool = True) -> list:
    """
    List all available templates.

    Args:
        tenant_id: Optional tenant ID to filter by
        include_global: Whether to include global templates

    Returns:
        List of template summaries
    """
    if tenant_id and include_global:
        rows = query(
            """
            SELECT id, tenant_id, event_type, communication_type,
                   description, ai_enhance, is_active, version
            FROM message_templates
            WHERE (tenant_id = %s OR tenant_id IS NULL)
              AND is_active = true
            ORDER BY event_type, tenant_id NULLS LAST
            """,
            [tenant_id]
        )
    elif tenant_id:
        rows = query(
            """
            SELECT id, tenant_id, event_type, communication_type,
                   description, ai_enhance, is_active, version
            FROM message_templates
            WHERE tenant_id = %s
              AND is_active = true
            ORDER BY event_type
            """,
            [tenant_id]
        )
    else:
        rows = query(
            """
            SELECT id, tenant_id, event_type, communication_type,
                   description, ai_enhance, is_active, version
            FROM message_templates
            WHERE tenant_id IS NULL
              AND is_active = true
            ORDER BY event_type
            """
        )

    return [dict(row) for row in rows]


def create_tenant_template(
    tenant_id: str,
    event_type: str,
    subject_template: str,
    body_text_template: str,
    communication_type: str = 'email',
    body_html_template: Optional[str] = None,
    variables: Optional[dict] = None,
    description: Optional[str] = None,
    ai_enhance: bool = False,
    ai_instructions: Optional[str] = None
) -> Optional[str]:
    """
    Create a tenant-specific template.

    Args:
        tenant_id: Tenant ID
        event_type: Event type
        subject_template: Subject line template
        body_text_template: Plain text body template
        communication_type: 'email' or 'sms'
        body_html_template: Optional HTML body template
        variables: Optional variable documentation
        description: Optional description
        ai_enhance: Whether to enable AI enhancement
        ai_instructions: Optional AI instructions

    Returns:
        Template ID if created, None if failed
    """
    try:
        rows = query(
            """
            INSERT INTO message_templates
                (tenant_id, event_type, communication_type, subject_template,
                 body_text_template, body_html_template, variables, description,
                 ai_enhance, ai_instructions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, event_type, communication_type)
            DO UPDATE SET
                subject_template = EXCLUDED.subject_template,
                body_text_template = EXCLUDED.body_text_template,
                body_html_template = EXCLUDED.body_html_template,
                variables = EXCLUDED.variables,
                description = EXCLUDED.description,
                ai_enhance = EXCLUDED.ai_enhance,
                ai_instructions = EXCLUDED.ai_instructions
            RETURNING id
            """,
            [
                tenant_id, event_type, communication_type, subject_template,
                body_text_template, body_html_template, variables, description,
                ai_enhance, ai_instructions
            ]
        )

        if rows:
            # Clear cache for this template
            cache_key = _get_cache_key(tenant_id, event_type, communication_type)
            if cache_key in _template_cache:
                del _template_cache[cache_key]

            return str(rows[0]['id'])
        return None

    except Exception as e:
        logger.error('Failed to create tenant template', tenant_id=tenant_id, event_type=event_type, err=e)
        return None
