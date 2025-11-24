-- Communication Agent Database Schema
-- Run this to create the necessary tables in dms_admin_db

-- Create tenant_configs table
CREATE TABLE IF NOT EXISTS tenant_configs (
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

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create communication_jobs table
CREATE TABLE IF NOT EXISTS communication_jobs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    process_after TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_tenant
        FOREIGN KEY(tenant_id)
        REFERENCES tenant_configs(tenant_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status_process_after
    ON communication_jobs(status, process_after);

CREATE INDEX IF NOT EXISTS idx_jobs_tenant_id
    ON communication_jobs(tenant_id);

CREATE INDEX IF NOT EXISTS idx_jobs_created_at
    ON communication_jobs(created_at);

-- Insert a sample tenant configuration
INSERT INTO tenant_configs (
    tenant_id,
    email_provider,
    resend_key,
    resend_from,
    quiet_hours_start,
    quiet_hours_end,
    dms_connection_string
) VALUES (
    'default_tenant',
    'resend',
    're_Qo2uF8Lz_NQHAuasWTXN9z8FkZW5veKhC',
    'noreply@example.com',
    '21:00',
    '08:00',
    'postgres://postgres:0Griswold@localhost:5432/dms_admin_db'
) ON CONFLICT (tenant_id) DO UPDATE
SET email_provider = EXCLUDED.email_provider,
    resend_key = EXCLUDED.resend_key,
    resend_from = EXCLUDED.resend_from,
    updated_at = NOW();

-- Verify setup
SELECT 'Schema created successfully!' as status;
SELECT tenant_id, email_provider, resend_from FROM tenant_configs;
