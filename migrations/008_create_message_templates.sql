-- Migration: 008_create_message_templates
-- Description: Create message_templates table for customizable email/SMS templates
-- Target Database: Central DB (dms_admin_db)
-- Created: 2025-01-19

-- Create message_templates table for storing customizable templates
CREATE TABLE IF NOT EXISTS public.message_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50),  -- NULL = global default template
    event_type VARCHAR(100) NOT NULL,
    communication_type VARCHAR(20) NOT NULL DEFAULT 'email',

    -- Template content
    subject_template TEXT,  -- For emails only, supports {{variable}} syntax
    body_html_template TEXT,  -- HTML version of the body
    body_text_template TEXT,  -- Plain text version of the body

    -- Metadata
    variables JSONB,  -- Documentation of available variables for this template
    description TEXT,  -- Human-readable description of when this template is used

    -- AI enhancement options
    ai_enhance BOOLEAN DEFAULT false,  -- Whether to use AI to personalize the content
    ai_instructions TEXT,  -- Optional instructions for AI personalization

    -- Status
    is_active BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(255),
    updated_by VARCHAR(255),

    -- Ensure unique template per tenant/event/communication type
    CONSTRAINT uq_template_tenant_event_type
        UNIQUE(tenant_id, event_type, communication_type),

    -- Validate communication type
    CONSTRAINT chk_communication_type
        CHECK (communication_type IN ('email', 'sms'))
);

-- Add table comments
COMMENT ON TABLE public.message_templates IS
    'Customizable message templates for automated communications';
COMMENT ON COLUMN public.message_templates.tenant_id IS
    'Tenant ID for tenant-specific templates, NULL for global defaults';
COMMENT ON COLUMN public.message_templates.event_type IS
    'Event type this template is for (e.g., seven_day_checkin, post_service_survey)';
COMMENT ON COLUMN public.message_templates.variables IS
    'JSON documentation of available template variables';
COMMENT ON COLUMN public.message_templates.ai_enhance IS
    'If true, AI will personalize the rendered template';

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_message_templates_tenant
    ON public.message_templates (tenant_id);
CREATE INDEX IF NOT EXISTS idx_message_templates_event_type
    ON public.message_templates (event_type);
CREATE INDEX IF NOT EXISTS idx_message_templates_active
    ON public.message_templates (is_active)
    WHERE is_active = true;

-- Create trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION public.update_message_templates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_message_templates_updated_at ON public.message_templates;
CREATE TRIGGER update_message_templates_updated_at
    BEFORE UPDATE ON public.message_templates
    FOR EACH ROW
    EXECUTE FUNCTION public.update_message_templates_updated_at();

-- Insert default global templates
INSERT INTO public.message_templates
    (tenant_id, event_type, communication_type, subject_template, body_text_template, variables, description, ai_enhance)
VALUES
    -- Seven Day Check-In
    (NULL, 'seven_day_checkin', 'email',
     'How Are You Enjoying Your New {{equipment_type}}?',
     E'Hi {{first_name}},\n\nIt''s been about a week since you picked up your {{equipment_model}}, and we wanted to check in!\n\nWe hope you''re enjoying it. If you have any questions about operation, maintenance, or anything else, don''t hesitate to reach out.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_type": "Type of equipment", "equipment_model": "Equipment make/model", "company_name": "Company name"}',
     'Check-in email sent 7 days after equipment purchase',
     true),

    -- Post-Service Survey
    (NULL, 'post_service_survey', 'email',
     'How Was Your Service Experience?',
     E'Hi {{first_name}},\n\nThank you for choosing {{company_name}} for your recent service{{work_order_ref}}!\n\nWe hope everything is running smoothly. If you have any questions or concerns about the work performed, please don''t hesitate to contact us.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "company_name": "Company name", "work_order_ref": "Work order reference (optional)", "work_order_number": "Work order number"}',
     'Survey email sent 48-72 hours after service pickup',
     true),

    -- Annual Tune-Up
    (NULL, 'annual_tuneup', 'email',
     'Time for Your Annual Tune-Up',
     E'Hi {{first_name}},\n\nCan you believe it''s been {{years_owned}} year(s) since you got your {{equipment_model}}? Time flies!\n\nAnnual maintenance helps keep your equipment running reliably and extends its life. We''d love to schedule a tune-up at your convenience.\n\nGive us a call or reply to this email to book your appointment.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "years_owned": "Number of years owned", "equipment_model": "Equipment make/model", "company_name": "Company name"}',
     'Tune-up reminder sent 14 days before purchase anniversary',
     true),

    -- Seasonal Reminder - Spring
    (NULL, 'seasonal_reminder_spring', 'email',
     'Get Your Equipment Ready for Spring!',
     E'Hi {{first_name}},\n\nSpring is just around the corner! Now is a great time to get your {{equipment_type}} ready for the busy season.\n\nA quick tune-up now can help prevent breakdowns when you need your equipment most. We''re scheduling spring service appointments now.\n\nGive us a call or reply to schedule your service.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_type": "Type of equipment", "company_name": "Company name"}',
     'Spring preparation reminder sent in March',
     true),

    -- Seasonal Reminder - Fall
    (NULL, 'seasonal_reminder_fall', 'email',
     'Prepare Your Equipment for Winter',
     E'Hi {{first_name}},\n\nWinter is approaching! Now is the perfect time to prepare your {{equipment_type}} for storage.\n\nProper winterization protects your investment and ensures easy startup come spring. We''re offering winterization services now.\n\nGive us a call or reply to schedule your service.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_type": "Type of equipment", "company_name": "Company name"}',
     'Fall/winterization reminder sent in October',
     true),

    -- Win-back / Ghost Customer
    (NULL, 'winback_missed_you', 'email',
     'We Miss You!',
     E'Hi {{first_name}},\n\nWe noticed it''s been a while since your last visit, and we just wanted to check in!\n\nIs your equipment running well? If you need any service, parts, or just have questions, we''re here to help.\n\nWe''d love to see you again soon.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "company_name": "Company name", "months_inactive": "Months since last visit"}',
     'Win-back email for customers inactive 12+ months',
     true),

    -- Anniversary Offer
    (NULL, 'anniversary_offer', 'email',
     'Happy Equipment Anniversary!',
     E'Hi {{first_name}},\n\nHappy anniversary! It''s been {{years_owned}} year(s) since you became part of our family with your {{equipment_model}}.\n\nThank you for being a loyal customer. If there''s anything we can do to help keep your equipment running great, we''re here for you.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "years_owned": "Years since purchase", "equipment_model": "Equipment make/model", "company_name": "Company name"}',
     'Anniversary celebration email 7 days before purchase anniversary',
     true),

    -- Warranty Expiration
    (NULL, 'warranty_expiration', 'email',
     'Your Warranty Is Expiring Soon',
     E'Hi {{first_name}},\n\nThis is a friendly reminder that the warranty on your {{equipment_model}} expires {{warranty_end_date}}.\n\nIf you have any concerns about your equipment, now is a great time to have it checked while it''s still covered.\n\nFeel free to contact us with any questions.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_model": "Equipment make/model", "warranty_end_date": "Warranty expiration date", "company_name": "Company name"}',
     'Warranty expiration warning sent 30 days before expiry',
     false),

    -- Trade-In Alert
    (NULL, 'trade_in_alert', 'email',
     'Time for an Upgrade?',
     E'Hi {{first_name}},\n\nYour {{equipment_model}} has served you well for {{years_owned}} years! Have you thought about what''s next?\n\nNewer models offer improved features, better fuel efficiency, and enhanced performance. We''d be happy to show you what''s available and discuss trade-in options.\n\nNo pressure - just let us know if you''d like to explore your options.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_model": "Equipment make/model", "years_owned": "Years since purchase", "repair_count": "Number of repairs", "company_name": "Company name"}',
     'Trade-in suggestion for old equipment with high repair history',
     true),

    -- First Service Alert
    (NULL, 'first_service_alert', 'email',
     'Time for Your First Service',
     E'Hi {{first_name}},\n\nYour {{equipment_model}} has reached {{machine_hours}} hours - time for its first service!\n\nThe first service is important to check everything after the initial break-in period. This helps ensure long-term reliability and performance.\n\nGive us a call to schedule your first service appointment.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_model": "Equipment make/model", "machine_hours": "Current machine hours", "company_name": "Company name"}',
     'First service reminder when equipment reaches 20 hours',
     false),

    -- Usage Service Alert
    (NULL, 'usage_service_alert', 'email',
     'Service Interval Reached',
     E'Hi {{first_name}},\n\nYour {{equipment_model}} has reached {{machine_hours}} hours and is due for scheduled maintenance.\n\nRegular service at recommended intervals keeps your equipment running at peak performance and helps prevent costly repairs down the road.\n\nGive us a call to schedule your service appointment.\n\nBest regards,\n{{company_name}}',
     '{"first_name": "Customer first name", "equipment_model": "Equipment make/model", "machine_hours": "Current machine hours", "service_interval": "Service interval hours", "company_name": "Company name"}',
     'Service reminder when equipment crosses 100-hour intervals',
     false)
ON CONFLICT (tenant_id, event_type, communication_type) DO NOTHING;
