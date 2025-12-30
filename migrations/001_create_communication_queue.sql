-- Migration: 001_create_communication_queue
-- Description: Create communication_queue table for outbound communications
-- Created: 2025-12-16

-- Create the update_updated_at_column function if it doesn't exist
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create alias function for compatibility
CREATE OR REPLACE FUNCTION public.update_communication_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create the communication_queue table
CREATE TABLE IF NOT EXISTS public.communication_queue
(
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    event_type character varying(100) NOT NULL,
    event_id uuid NOT NULL,
    event_timestamp timestamp with time zone NOT NULL DEFAULT now(),
    communication_type character varying(50) NOT NULL,
    template_id character varying(100),
    priority integer DEFAULT 5,
    recipient_type character varying(50) NOT NULL,
    recipient_id uuid NOT NULL,
    recipient_address jsonb NOT NULL,
    subject character varying(500),
    message_params jsonb,
    attachments jsonb,
    status character varying(50) NOT NULL DEFAULT 'pending',
    scheduled_for timestamp with time zone,
    retry_count integer DEFAULT 0,
    max_retries integer DEFAULT 3,
    last_retry_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    error_details jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    opened_at timestamp with time zone,
    external_message_id character varying(255),
    external_status jsonb,
    tenant_id uuid NOT NULL,

    CONSTRAINT communication_queue_pkey PRIMARY KEY (id),
    CONSTRAINT chk_communication_queue_type CHECK (
        communication_type IN ('email', 'sms', 'push')
    ),
    CONSTRAINT chk_communication_queue_status CHECK (
        status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')
    ),
    CONSTRAINT valid_priority CHECK (priority >= 1 AND priority <= 10)
);

-- Add table comment
COMMENT ON TABLE public.communication_queue IS 'Queue for outbound communications (email, SMS) across all tenants';
COMMENT ON COLUMN public.communication_queue.priority IS 'Priority for sending (1=highest, 10=lowest)';
COMMENT ON COLUMN public.communication_queue.tenant_id IS 'Tenant identifier from the tenant database';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_comm_queue_created
    ON public.communication_queue (created_at);

CREATE INDEX IF NOT EXISTS idx_comm_queue_event
    ON public.communication_queue (event_type, event_id);

CREATE INDEX IF NOT EXISTS idx_comm_queue_recipient
    ON public.communication_queue (recipient_id);

CREATE INDEX IF NOT EXISTS idx_comm_queue_retry
    ON public.communication_queue (next_retry_at)
    WHERE status = 'failed' AND retry_count < max_retries;

CREATE INDEX IF NOT EXISTS idx_comm_queue_scheduled
    ON public.communication_queue (scheduled_for)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_comm_queue_tenant_status
    ON public.communication_queue (tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_communication_queue_status
    ON public.communication_queue (status);

CREATE INDEX IF NOT EXISTS idx_communication_queue_tenant_id
    ON public.communication_queue (tenant_id);

-- Create trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS update_communication_queue_updated_at ON public.communication_queue;
CREATE TRIGGER update_communication_queue_updated_at
    BEFORE UPDATE ON public.communication_queue
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
