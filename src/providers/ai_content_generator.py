"""
AI Content Generator for email communications.

Uses DeepSeek (OpenAI-compatible API) to generate personalized email content
based on event type and message parameters.
"""

import os
from openai import OpenAI
from src import logger

# DeepSeek API configuration
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')


# Event type to prompt mapping
EVENT_TYPE_PROMPTS = {
    'work_order_receipt': {
        'system': """You work for a power equipment sales and service company.
Write a brief email receipt for a work order.
Simply thank them for their business and reference the work order number.
Do NOT say the work is "complete" or "completed" - this is just a receipt.
Do NOT mention pickup, delivery, or equipment status.
End with "Best regards," followed by the company name on the next line.
Keep it to one or two sentences plus the sign-off.""",
        'default_subject': 'Your Work Order Receipt'
    },

    'sales_order_receipt': {
        'system': """You work for a power equipment sales and service company.
Write a brief email receipt for a sales order.
Simply thank them for their purchase and reference the sales order number.
Do NOT mention delivery status or shipping details unless provided.
End with "Best regards," followed by the company name on the next line.
Keep it to one or two sentences plus the sign-off.""",
        'default_subject': 'Your Sales Order Receipt'
    },

    'service_reminder': {
        'system': """You are a helpful customer service representative for an HVAC/home services company.
Write a friendly reminder email about scheduling a maintenance service.
Emphasize the benefits of regular maintenance (efficiency, longevity, preventing breakdowns).
Keep it brief and include a clear call-to-action to schedule.
Do not include a subject line - only the body content.""",
        'default_subject': 'Time for Your Equipment Tune-Up'
    },

    'appointment_confirmation': {
        'system': """You are a customer service representative for an HVAC/home services company.
Write a clear, helpful appointment confirmation email.
Include the appointment date/time prominently.
Provide any preparation instructions if relevant.
Include contact info for rescheduling.
Keep it concise and professional.
Do not include a subject line - only the body content.""",
        'default_subject': 'Your Appointment Confirmation'
    },

    'invoice_reminder': {
        'system': """You are a professional accounts receivable representative for an HVAC/home services company.
Write a polite, non-aggressive payment reminder email.
Be respectful and understanding - assume the best intentions.
Clearly state the invoice number, amount due, and how long it's been outstanding.
Offer to help if there are questions or concerns about the invoice.
Do not include a subject line - only the body content.""",
        'default_subject': 'Friendly Payment Reminder'
    },

    'estimate_followup': {
        'system': """You are a sales representative for an HVAC/home services company.
Write a friendly follow-up email about a recent estimate/quote.
Don't be pushy - offer to answer questions.
Mention you're available to discuss options or make adjustments.
Keep it brief and helpful.
Do not include a subject line - only the body content.""",
        'default_subject': 'Following Up on Your Estimate'
    },

    'job_complete': {
        'system': """You are a customer service representative for an HVAC/home services company.
Write a thank-you email after completing a service job.
Thank them for their business.
Briefly mention any warranty or follow-up care instructions.
Invite them to reach out with any questions.
Encourage them to leave a review if satisfied.
Do not include a subject line - only the body content.""",
        'default_subject': 'Service Complete - Thank You!'
    },

    'default': {
        'system': """You are a professional customer service representative for an HVAC/home services company.
Write a professional, friendly email based on the context provided.
Keep the tone warm but professional. Be concise.
Do not include a subject line - only the body content.""",
        'default_subject': 'Message from Your Service Team'
    }
}


def get_ai_client():
    """Create and return an OpenAI client configured for DeepSeek."""
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY environment variable is not set")

    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL
    )


def build_user_prompt(event_type: str, message_params: dict, recipient_address: dict, company_name: str = None) -> str:
    """Build the user prompt from message parameters.

    Keep it simple - just pass along whatever is in message_params.
    """

    prompt_parts = []

    # Add company name if provided
    if company_name:
        prompt_parts.append(f"Company Name: {company_name}")

    # Add all message_params as context (skip tenant_id as it's not useful for content)
    for key, value in message_params.items():
        if value and key != 'tenant_id':  # Only include non-empty values, skip tenant_id
            # Convert snake_case to readable format
            readable_key = key.replace('_', ' ').title()
            prompt_parts.append(f"{readable_key}: {value}")

    # If no params, provide minimal context
    if not prompt_parts:
        name = recipient_address.get('name', 'Customer')
        prompt_parts.append(f"Customer name: {name}")

    return "\n".join(prompt_parts)


def generate_email_content(
    event_type: str,
    message_params: dict,
    recipient_address: dict,
    subject_override: str = None,
    company_name: str = None
) -> dict:
    """
    Generate email content using DeepSeek AI.

    Args:
        event_type: The type of event triggering this email
        message_params: Dictionary of parameters for the email content
        recipient_address: Dictionary with recipient info (email, name, etc.)
        subject_override: Optional subject line override (skip AI generation)
        company_name: Optional company name to include in context

    Returns:
        dict with 'subject' and 'body' keys
    """

    # Get the prompt configuration for this event type
    prompt_config = EVENT_TYPE_PROMPTS.get(event_type, EVENT_TYPE_PROMPTS['default'])

    # Build system prompt
    system_prompt = prompt_config['system']
    if company_name:
        system_prompt = system_prompt.replace('an HVAC/home services company', f'{company_name}')

    # Build user prompt
    user_prompt = build_user_prompt(event_type, message_params, recipient_address, company_name)

    logger.info(
        'Generating AI email content',
        event_type=event_type,
        has_params=bool(message_params)
    )

    try:
        client = get_ai_client()

        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        generated_body = response.choices[0].message.content.strip()

        # Use override subject or default
        subject = subject_override or prompt_config['default_subject']

        # Personalize subject if we have customer info
        if message_params.get('work_order_number') and 'work_order' in event_type.lower():
            subject = f"{subject} - #{message_params['work_order_number']}"

        logger.info(
            'AI email content generated successfully',
            event_type=event_type,
            body_length=len(generated_body)
        )

        return {
            'subject': subject,
            'body': generated_body
        }

    except Exception as e:
        logger.error(
            'AI content generation failed, using fallback',
            event_type=event_type,
            error=str(e)
        )

        # Fallback to basic template
        return generate_fallback_content(event_type, message_params, recipient_address)


def generate_fallback_content(event_type: str, message_params: dict, recipient_address: dict) -> dict:
    """Generate fallback email content when AI is unavailable."""

    customer_name = message_params.get('customer_name',
                   message_params.get('first_name',
                   recipient_address.get('name', 'Customer')))

    prompt_config = EVENT_TYPE_PROMPTS.get(event_type, EVENT_TYPE_PROMPTS['default'])
    subject = prompt_config['default_subject']

    if event_type == 'work_order_receipt':
        work_order = message_params.get('work_order_number', 'N/A')
        body = f"""Hello {customer_name},

Thank you for your business. This email confirms receipt of your work order.

Work Order Number: {work_order}

If you have any questions, please don't hesitate to contact us.

Best regards,
Your Service Team"""

    elif event_type == 'sales_order_receipt':
        sales_order = message_params.get('work_order_number', message_params.get('sales_order_number', 'N/A'))
        body = f"""Hello {customer_name},

Thank you for your purchase. This email confirms receipt of your sales order.

Sales Order Number: {sales_order}

If you have any questions, please don't hesitate to contact us.

Best regards,
Your Service Team"""

    elif event_type == 'service_reminder':
        model = message_params.get('model', 'equipment')
        body = f"""Hello {customer_name},

It's been a while since your last service appointment. Regular maintenance helps keep your {model} running efficiently and prevents unexpected breakdowns.

We'd love to schedule a tune-up at your convenience. Please contact us to book an appointment.

Best regards,
Your Service Team"""

    elif event_type == 'appointment_confirmation':
        appt_time = message_params.get('scheduled_start', message_params.get('appointment_time', 'your scheduled time'))
        body = f"""Hello {customer_name},

This is a confirmation of your upcoming service appointment scheduled for {appt_time}.

If you need to reschedule, please contact us as soon as possible.

We look forward to serving you!

Best regards,
Your Service Team"""

    elif event_type == 'invoice_reminder':
        invoice_id = message_params.get('invoice_id', message_params.get('invoice_number', 'N/A'))
        balance = message_params.get('balance', message_params.get('amount_due', 'N/A'))
        body = f"""Hello {customer_name},

This is a friendly reminder that invoice #{invoice_id} with a balance of ${balance} is past due.

If you have any questions about this invoice or need to discuss payment options, please don't hesitate to contact us.

Thank you,
Your Service Team"""

    else:
        body = f"""Hello {customer_name},

Thank you for being a valued customer.

If you have any questions, please contact us.

Best regards,
Your Service Team"""

    return {
        'subject': subject,
        'body': body
    }
