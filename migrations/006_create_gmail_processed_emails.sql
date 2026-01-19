-- Migration: 006_create_gmail_processed_emails
-- Description: Create gmail_processed_emails table for tracking processed contact form emails
-- Target Database: Central DB (dms_admin_db)
-- Created: 2025-01-09

-- Create gmail_processed_emails table to prevent duplicate processing
CREATE TABLE IF NOT EXISTS public.gmail_processed_emails (
    -- Primary identification
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,

    -- Gmail message tracking
    gmail_message_id VARCHAR(255) NOT NULL,
    gmail_thread_id VARCHAR(255),

    -- Parsed email info
    sender_email VARCHAR(255),
    sender_name VARCHAR(255),
    subject VARCHAR(500),
    inquiry_type VARCHAR(50),
    equipment_type VARCHAR(255),

    -- Processing result
    response_job_id BIGINT REFERENCES public.communication_jobs(id),
    parse_error TEXT,
    was_valid BOOLEAN DEFAULT TRUE,

    -- Timing
    email_received_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Ensure we don't process same email twice per tenant
    CONSTRAINT uq_gmail_processed_tenant_message
        UNIQUE (tenant_id, gmail_message_id)
);

-- Add table comments
COMMENT ON TABLE public.gmail_processed_emails IS 'Tracks Gmail messages processed by contact form auto-responder';
COMMENT ON COLUMN public.gmail_processed_emails.gmail_message_id IS 'Unique Gmail message ID from API';
COMMENT ON COLUMN public.gmail_processed_emails.gmail_thread_id IS 'Gmail thread ID for conversation tracking';
COMMENT ON COLUMN public.gmail_processed_emails.inquiry_type IS 'Parsed type: buying or repairing';
COMMENT ON COLUMN public.gmail_processed_emails.response_job_id IS 'Reference to the auto-response email job created';
COMMENT ON COLUMN public.gmail_processed_emails.parse_error IS 'Error message if parsing failed';
COMMENT ON COLUMN public.gmail_processed_emails.was_valid IS 'Whether the email was a valid contact form';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_gmail_processed_tenant_id
    ON public.gmail_processed_emails (tenant_id);

CREATE INDEX IF NOT EXISTS idx_gmail_processed_processed_at
    ON public.gmail_processed_emails (processed_at);

CREATE INDEX IF NOT EXISTS idx_gmail_processed_sender_email
    ON public.gmail_processed_emails (sender_email);

CREATE INDEX IF NOT EXISTS idx_gmail_processed_inquiry_type
    ON public.gmail_processed_emails (tenant_id, inquiry_type);
