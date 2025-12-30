-- Migration: 002_create_communication_jobs
-- Description: Create communication_jobs table for job queue processing
-- Target Database: Central DB (dms_admin_db)
-- Created: 2024-12-20

-- Create communication_jobs table for job queue
CREATE TABLE IF NOT EXISTS public.communication_jobs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    process_after TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT chk_communication_jobs_status CHECK (
        status IN ('pending', 'processing', 'complete', 'failed', 'cancelled')
    )
);

-- Add table comments
COMMENT ON TABLE public.communication_jobs IS 'Job queue for processing outbound communications';
COMMENT ON COLUMN public.communication_jobs.job_type IS 'Type of job: send_email, send_sms, notify_customer, etc.';
COMMENT ON COLUMN public.communication_jobs.payload IS 'JSONB payload containing job-specific data';
COMMENT ON COLUMN public.communication_jobs.status IS 'Job status: pending, processing, complete, failed, cancelled';
COMMENT ON COLUMN public.communication_jobs.process_after IS 'Timestamp when job should be processed (for delayed jobs)';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_communication_jobs_status_process_after
    ON public.communication_jobs (status, process_after)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_communication_jobs_tenant_id
    ON public.communication_jobs (tenant_id);

CREATE INDEX IF NOT EXISTS idx_communication_jobs_created_at
    ON public.communication_jobs (created_at);

CREATE INDEX IF NOT EXISTS idx_communication_jobs_job_type
    ON public.communication_jobs (job_type);

CREATE INDEX IF NOT EXISTS idx_communication_jobs_retry
    ON public.communication_jobs (status, retry_count)
    WHERE status = 'failed' AND retry_count < max_retries;

-- Create trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION public.update_communication_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_communication_jobs_updated_at ON public.communication_jobs;
CREATE TRIGGER update_communication_jobs_updated_at
    BEFORE UPDATE ON public.communication_jobs
    FOR EACH ROW
    EXECUTE FUNCTION public.update_communication_jobs_updated_at();
