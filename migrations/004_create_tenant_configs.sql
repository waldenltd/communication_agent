-- Migration: 004_create_tenant_configs
-- Description: Create tenant_configs table for storing tenant-specific configuration
-- Created: 2025-12-21

-- Create the tenant_configs table
CREATE TABLE IF NOT EXISTS public.tenant_configs (
    tenant_id VARCHAR(255) PRIMARY KEY,

    -- SMS Configuration (Twilio)
    twilio_sid VARCHAR(255),
    twilio_auth_token VARCHAR(255),
    twilio_from_number VARCHAR(20),

    -- Email Configuration
    sendgrid_key VARCHAR(255),
    sendgrid_from VARCHAR(255),
    email_provider VARCHAR(50),
    resend_key VARCHAR(255),
    resend_from VARCHAR(255),

    -- Operational Settings
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    dms_connection_string TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add table and column comments
COMMENT ON TABLE public.tenant_configs IS 'Stores configuration settings for each tenant including email/SMS credentials';
COMMENT ON COLUMN public.tenant_configs.tenant_id IS 'Unique identifier for the tenant';
COMMENT ON COLUMN public.tenant_configs.twilio_sid IS 'Twilio Account SID for SMS';
COMMENT ON COLUMN public.tenant_configs.twilio_auth_token IS 'Twilio Auth Token for SMS';
COMMENT ON COLUMN public.tenant_configs.twilio_from_number IS 'Twilio phone number for sending SMS';
COMMENT ON COLUMN public.tenant_configs.sendgrid_key IS 'SendGrid API key for email';
COMMENT ON COLUMN public.tenant_configs.sendgrid_from IS 'SendGrid sender email address';
COMMENT ON COLUMN public.tenant_configs.email_provider IS 'Email provider to use (sendgrid, resend)';
COMMENT ON COLUMN public.tenant_configs.resend_key IS 'Resend API key for email';
COMMENT ON COLUMN public.tenant_configs.resend_from IS 'Resend sender email address';
COMMENT ON COLUMN public.tenant_configs.quiet_hours_start IS 'Start time for quiet hours (no notifications)';
COMMENT ON COLUMN public.tenant_configs.quiet_hours_end IS 'End time for quiet hours';
COMMENT ON COLUMN public.tenant_configs.dms_connection_string IS 'Connection string to tenant DMS database';

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_tenant_configs_email_provider
    ON public.tenant_configs (email_provider);

-- Create trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS update_tenant_configs_updated_at ON public.tenant_configs;
CREATE TRIGGER update_tenant_configs_updated_at
    BEFORE UPDATE ON public.tenant_configs
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
