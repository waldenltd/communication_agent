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
Start with a greeting using the customer's first name (e.g., "Hi Scott,").
Simply thank them for their business and reference the work order number.
Do NOT say the work is "complete" or "completed" - this is just a receipt.
Do NOT mention pickup, delivery, or equipment status.
End with "Best regards," followed by the company name on the next line.
Keep it to 2-3 sentences plus the sign-off.""",
        'default_subject': 'Your Work Order Receipt'
    },

    'sales_order_receipt': {
        'system': """You work for a power equipment sales and service company.
Write a brief email receipt for a sales order.
Start with a greeting using the customer's first name (e.g., "Hi Scott,").
Simply thank them for their purchase and reference the sales order number.
Do NOT mention delivery status or shipping details unless provided.
End with "Best regards," followed by the company name on the next line.
Keep it to 2-3 sentences plus the sign-off.""",
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

    'contact_form_buying': {
        'system': """You are a sales representative for an outdoor power equipment company.
Write a warm, helpful response to a customer inquiry about BUYING equipment.
Start with a greeting using the customer's first name.
Thank them for their interest and express enthusiasm to help.
Reference the specific equipment type they mentioned.
Invite them to visit the showroom, call, or reply with questions.
Keep it friendly, professional, and brief (3-4 sentences plus sign-off).
End with "Best regards," followed by the signature name and company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Thank You for Your Interest'
    },

    'contact_form_repairing': {
        'system': """You are a service representative for an outdoor power equipment company.
Write a helpful response to a customer inquiry about REPAIRING equipment.
Start with a greeting using the customer's first name.
Acknowledge their repair need with empathy.
If a location is mentioned, confirm pickup/delivery service availability.
Ask for make/model and issue description to get started.
Provide the phone number for scheduling.
Keep it friendly, professional, and brief (3-4 sentences plus sign-off).
End with "Best regards," followed by the signature name and company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Re: Your Repair Inquiry'
    },

    'seven_day_checkin': {
        'system': """You are a customer service representative for an outdoor power equipment company.
Write a friendly 7-day check-in email to a customer who recently purchased equipment.
Start with a greeting using the customer's first name.
Ask how they're enjoying their new equipment and if they have any questions.
Offer tips for getting the most out of their purchase.
Remind them you're available if they need anything.
Keep it warm, brief (3-4 sentences), and genuine - not salesy.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'How Are You Enjoying Your New Equipment?'
    },

    'post_service_survey': {
        'system': """You are a customer service representative for an outdoor power equipment company.
Write a brief follow-up email asking about their recent service experience.
Start with a greeting using the customer's first name.
Thank them for choosing your service department.
Ask if their equipment is running well and if they were satisfied with the service.
Invite them to share feedback or contact you with any concerns.
Keep it short (2-3 sentences) and sincere.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'How Was Your Service Experience?'
    },

    'annual_tuneup': {
        'system': """You are a service advisor for an outdoor power equipment company.
Write a friendly reminder that it's time for an annual tune-up.
Start with a greeting using the customer's first name.
Reference how long they've owned their equipment (anniversary).
Explain the benefits of annual maintenance (reliability, longevity, performance).
Provide a clear call-to-action to schedule service.
Keep it helpful and informative, not pushy.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Time for Your Annual Tune-Up'
    },

    'seasonal_reminder_spring': {
        'system': """You are a service advisor for an outdoor power equipment company.
Write a friendly spring preparation reminder email.
Start with a greeting using the customer's first name.
Mention that spring is coming and it's time to get equipment ready.
Suggest a tune-up or inspection before the busy season.
Highlight benefits: avoid breakdowns, ensure peak performance.
Keep it seasonal and timely, not salesy.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Get Your Equipment Ready for Spring!'
    },

    'seasonal_reminder_fall': {
        'system': """You are a service advisor for an outdoor power equipment company.
Write a friendly fall/winterization reminder email.
Start with a greeting using the customer's first name.
Mention that winter is approaching and it's time to prepare equipment for storage.
Suggest winterization service or proper storage preparation.
Highlight benefits: protect investment, ensure easy startup in spring.
Keep it helpful and seasonal.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Prepare Your Equipment for Winter'
    },

    'anniversary_offer': {
        'system': """You are a customer service representative for an outdoor power equipment company.
Write a friendly purchase anniversary email.
Start with a greeting using the customer's first name.
Congratulate them on owning their equipment for another year.
Thank them for being a loyal customer.
Optionally mention a special offer or discount for anniversary.
Invite them to schedule service if needed.
Keep it celebratory and appreciative.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Happy Equipment Anniversary!'
    },

    'winback_missed_you': {
        'system': """You are a customer service representative for an outdoor power equipment company.
Write a friendly "we miss you" email to a customer who hasn't visited in a while.
Start with a greeting using the customer's first name.
Express that you noticed it's been a while since their last visit.
Ask if their equipment is running well or if they need any help.
Remind them of the services you offer.
Keep it warm and genuine, not guilt-tripping or overly promotional.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'We Miss You!'
    },

    'first_service_alert': {
        'system': """You are a service advisor for an outdoor power equipment company.
Write an email alerting the customer that their equipment is due for its first service.
Start with a greeting using the customer's first name.
Mention the equipment has reached the recommended hours for first service.
Explain why first service is important (break-in period, initial adjustments).
Provide a clear call-to-action to schedule service.
Keep it informative and helpful.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Time for Your First Service'
    },

    'usage_service_alert': {
        'system': """You are a service advisor for an outdoor power equipment company.
Write an email alerting the customer that their equipment is due for service based on usage hours.
Start with a greeting using the customer's first name.
Mention the equipment has reached the recommended service interval.
Briefly explain what service typically includes at this interval.
Provide a clear call-to-action to schedule service.
Keep it straightforward and helpful.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Service Interval Reached'
    },

    'warranty_expiration': {
        'system': """You are a customer service representative for an outdoor power equipment company.
Write an email alerting the customer that their warranty is expiring soon.
Start with a greeting using the customer's first name.
Mention the warranty expiration date.
Suggest scheduling any needed repairs while still under warranty.
Optionally mention extended warranty options if available.
Keep it informative and helpful, not alarming.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Your Warranty Is Expiring Soon'
    },

    'trade_in_alert': {
        'system': """You are a sales representative for an outdoor power equipment company.
Write a friendly email suggesting it might be time to consider upgrading equipment.
Start with a greeting using the customer's first name.
Mention the age of their equipment and high repair history (if applicable).
Suggest exploring newer models with improved features.
Mention trade-in program if available.
Keep it suggestive, not pushy - respect their decision.
End with "Best regards," followed by the company name.
Do not include a subject line - only the body content.""",
        'default_subject': 'Time for an Upgrade?'
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


def generate_from_template(
    event_type: str,
    message_params: dict,
    tenant_id: str = None,
    company_name: str = None
) -> dict:
    """
    Generate email content from a database template.

    Loads the template, renders it with variables, and optionally enhances with AI.

    Args:
        event_type: The event type (e.g., 'seven_day_checkin')
        message_params: Dictionary of variable values for the template
        tenant_id: Optional tenant ID for tenant-specific templates
        company_name: Optional company name to include in variables

    Returns:
        dict with 'subject' and 'body' keys, or None if no template found
    """
    try:
        from src.providers.template_renderer import (
            load_template, render, should_ai_enhance, get_ai_instructions
        )
    except ImportError:
        # Template renderer not available
        return None

    # Load the template
    template = load_template(event_type, tenant_id)
    if not template:
        return None

    # Prepare variables for rendering
    variables = dict(message_params)
    if company_name and 'company_name' not in variables:
        variables['company_name'] = company_name

    # Handle work order reference formatting
    if 'work_order_number' in variables and 'work_order_ref' not in variables:
        wo_num = variables['work_order_number']
        variables['work_order_ref'] = f" (Work Order #{wo_num})" if wo_num else ""

    # Render the template
    rendered = render(template, variables)

    result = {
        'subject': rendered.subject,
        'body': rendered.body_text
    }

    # Check if AI enhancement is enabled
    if template.ai_enhance:
        try:
            enhanced = _enhance_with_ai(
                event_type=event_type,
                base_content=rendered.body_text,
                variables=variables,
                ai_instructions=template.ai_instructions,
                company_name=company_name
            )
            if enhanced:
                result['body'] = enhanced
        except Exception as e:
            logger.warn(
                'AI enhancement failed, using base template',
                event_type=event_type,
                error=str(e)
            )

    logger.info(
        'Generated content from template',
        event_type=event_type,
        tenant_id=tenant_id,
        ai_enhanced=template.ai_enhance
    )

    return result


def _enhance_with_ai(
    event_type: str,
    base_content: str,
    variables: dict,
    ai_instructions: str = None,
    company_name: str = None
) -> str:
    """
    Enhance template-rendered content with AI personalization.

    Args:
        event_type: The event type
        base_content: The rendered template content
        variables: Variables used in rendering
        ai_instructions: Optional custom AI instructions
        company_name: Company name for context

    Returns:
        Enhanced content string, or None if enhancement failed
    """
    if not DEEPSEEK_API_KEY:
        return None

    # Build enhancement prompt
    prompt_config = EVENT_TYPE_PROMPTS.get(event_type, EVENT_TYPE_PROMPTS['default'])

    system_prompt = f"""You are enhancing a customer email for {company_name or 'a service company'}.

Your task is to improve the provided email draft while:
1. Maintaining the core message and all important information
2. Making the tone more personal and warm
3. Keeping the same overall structure
4. Not changing any facts, names, or specific details
5. Keeping it concise - similar length to the original

{ai_instructions or ''}

Do not include a subject line - only output the improved email body."""

    user_prompt = f"""Here is the email draft to enhance:

---
{base_content}
---

Please improve this email to make it more personal and engaging while keeping all the key information."""

    try:
        client = get_ai_client()

        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,  # Slightly lower for more consistent enhancement
            max_tokens=1000
        )

        enhanced = response.choices[0].message.content.strip()
        return enhanced

    except Exception as e:
        logger.error('AI enhancement failed', event_type=event_type, error=str(e))
        return None


def generate_email_content(
    event_type: str,
    message_params: dict,
    recipient_address: dict,
    subject_override: str = None,
    company_name: str = None,
    use_templates: bool = True,
    tenant_id: str = None
) -> dict:
    """
    Generate email content using templates with optional AI enhancement.

    This is the main entry point for content generation. It uses a hybrid approach:
    1. Try to load a template from the database
    2. If template exists and AI enhancement is disabled, use template directly
    3. If AI enhancement is enabled, enhance the rendered template with AI
    4. Fall back to pure AI generation if no template exists

    Args:
        event_type: The type of event triggering this email
        message_params: Dictionary of parameters for the email content
        recipient_address: Dictionary with recipient info (email, name, etc.)
        subject_override: Optional subject line override (skip AI generation)
        company_name: Optional company name to include in context
        use_templates: Whether to try loading templates first (default True)
        tenant_id: Optional tenant ID for tenant-specific templates

    Returns:
        dict with 'subject' and 'body' keys
    """
    # Try template-based generation first
    if use_templates:
        try:
            result = generate_from_template(
                event_type=event_type,
                message_params=message_params,
                tenant_id=tenant_id,
                company_name=company_name
            )
            if result:
                # Override subject if specified
                if subject_override:
                    result['subject'] = subject_override
                return result
        except Exception as e:
            logger.warn(
                'Template generation failed, falling back to AI',
                event_type=event_type,
                error=str(e)
            )

    # Fall back to AI-only generation
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

    elif event_type == 'contact_form_buying':
        equipment = message_params.get('equipment_type', 'equipment')
        company_name = message_params.get('company_name', 'Year Round Power')
        company_phone = message_params.get('company_phone', '860-953-9421')
        signature = message_params.get('signature_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Thank you for your interest in {equipment} from {company_name}!

We'd love to help you find the right equipment for your needs. We carry a wide selection and our team can help you choose the best option.

Feel free to visit our showroom, give us a call at {company_phone}, or reply to this email with any questions.

Best regards,
{signature}
{company_name}"""

    elif event_type == 'contact_form_repairing':
        equipment = message_params.get('equipment_type', 'equipment')
        company_name = message_params.get('company_name', 'Year Round Power')
        company_phone = message_params.get('company_phone', '860-953-9421')
        signature = message_params.get('signature_name', 'Your Service Team')
        location = message_params.get('location', '')
        location_text = f" Yes, we do offer pickup and delivery service in {location}." if location else ""
        body = f"""Hi {customer_name},

Thank you for reaching out to {company_name}!

We'd be happy to help with your {equipment} repair.{location_text}

To get started, could you let us know:
- The make and model of your {equipment}
- A brief description of the issue you're experiencing

Feel free to reply to this email or give us a call at {company_phone} to schedule service.

Best regards,
{signature}
{company_name}"""

    elif event_type == 'seven_day_checkin':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'new equipment'))
        company_name = message_params.get('company_name', 'Your Equipment Team')
        body = f"""Hi {customer_name},

It's been about a week since you picked up your {equipment}, and we wanted to check in!

We hope you're enjoying it. If you have any questions about operation, maintenance, or anything else, don't hesitate to reach out.

Best regards,
{company_name}"""

    elif event_type == 'post_service_survey':
        work_order = message_params.get('work_order_number', '')
        company_name = message_params.get('company_name', 'Your Service Team')
        work_order_text = f" (Work Order #{work_order})" if work_order else ""
        body = f"""Hi {customer_name},

Thank you for choosing us for your recent service{work_order_text}!

We hope everything is running smoothly. If you have any questions or concerns about the work performed, please don't hesitate to contact us.

Best regards,
{company_name}"""

    elif event_type == 'annual_tuneup':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        years_owned = message_params.get('years_owned', '1')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Can you believe it's been {years_owned} year(s) since you got your {equipment}? Time flies!

Annual maintenance helps keep your equipment running reliably and extends its life. We'd love to schedule a tune-up at your convenience.

Give us a call or reply to this email to book your appointment.

Best regards,
{company_name}"""

    elif event_type in ('seasonal_reminder_spring', 'seasonal_reminder'):
        equipment = message_params.get('equipment_type', 'outdoor power equipment')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Spring is just around the corner! Now is a great time to get your {equipment} ready for the busy season.

A quick tune-up now can help prevent breakdowns when you need your equipment most. We're scheduling spring service appointments now.

Give us a call or reply to schedule your service.

Best regards,
{company_name}"""

    elif event_type == 'seasonal_reminder_fall':
        equipment = message_params.get('equipment_type', 'outdoor power equipment')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Winter is approaching! Now is the perfect time to prepare your {equipment} for storage.

Proper winterization protects your investment and ensures easy startup come spring. We're offering winterization services now.

Give us a call or reply to schedule your service.

Best regards,
{company_name}"""

    elif event_type == 'anniversary_offer':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        years_owned = message_params.get('years_owned', '1')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Happy anniversary! It's been {years_owned} year(s) since you became part of our family with your {equipment}.

Thank you for being a loyal customer. If there's anything we can do to help keep your equipment running great, we're here for you.

Best regards,
{company_name}"""

    elif event_type == 'winback_missed_you':
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

We noticed it's been a while since your last visit, and we just wanted to check in!

Is your equipment running well? If you need any service, parts, or just have questions, we're here to help.

We'd love to see you again soon.

Best regards,
{company_name}"""

    elif event_type == 'first_service_alert':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        hours = message_params.get('machine_hours', '20')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Your {equipment} has reached {hours} hours - time for its first service!

The first service is important to check everything after the initial break-in period. This helps ensure long-term reliability and performance.

Give us a call to schedule your first service appointment.

Best regards,
{company_name}"""

    elif event_type == 'usage_service_alert':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        hours = message_params.get('machine_hours', '100')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Your {equipment} has reached {hours} hours and is due for scheduled maintenance.

Regular service at recommended intervals keeps your equipment running at peak performance and helps prevent costly repairs down the road.

Give us a call to schedule your service appointment.

Best regards,
{company_name}"""

    elif event_type == 'warranty_expiration':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        expiration_date = message_params.get('warranty_end_date', 'soon')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

This is a friendly reminder that the warranty on your {equipment} expires {expiration_date}.

If you have any concerns about your equipment, now is a great time to have it checked while it's still covered.

Feel free to contact us with any questions.

Best regards,
{company_name}"""

    elif event_type == 'trade_in_alert':
        equipment = message_params.get('equipment_model', message_params.get('equipment_type', 'equipment'))
        years_owned = message_params.get('years_owned', 'several')
        company_name = message_params.get('company_name', 'Your Service Team')
        body = f"""Hi {customer_name},

Your {equipment} has served you well for {years_owned} years! Have you thought about what's next?

Newer models offer improved features, better fuel efficiency, and enhanced performance. We'd be happy to show you what's available and discuss trade-in options.

No pressure - just let us know if you'd like to explore your options.

Best regards,
{company_name}"""

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
