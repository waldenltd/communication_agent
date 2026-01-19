-- Migration: 007_add_source_reference_index
-- Description: Add source_reference column and unique index for job deduplication
-- Target Database: Central DB (dms_admin_db)
-- Created: 2025-01-19

-- Add source_reference column for efficient deduplication
-- This moves the source_reference from the JSONB payload to a dedicated column
ALTER TABLE public.communication_jobs
ADD COLUMN IF NOT EXISTS source_reference VARCHAR(255);

-- Add comment for documentation
COMMENT ON COLUMN public.communication_jobs.source_reference IS
    'Unique reference to prevent duplicate job creation (e.g., seven_day_checkin_tenant123_equip456)';

-- Migrate existing source_reference from payload to the new column
UPDATE public.communication_jobs
SET source_reference = payload ->> 'source_reference'
WHERE source_reference IS NULL
  AND payload ->> 'source_reference' IS NOT NULL;

-- Create unique partial index for deduplication
-- Only enforce uniqueness for pending, processing, and complete jobs
-- This allows the same reference to be used again after a job fails
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_reference_unique
    ON public.communication_jobs (tenant_id, job_type, source_reference)
    WHERE source_reference IS NOT NULL
      AND status IN ('pending', 'processing', 'complete');

-- Create a regular index for lookups by source_reference
CREATE INDEX IF NOT EXISTS idx_jobs_source_reference
    ON public.communication_jobs (source_reference)
    WHERE source_reference IS NOT NULL;
