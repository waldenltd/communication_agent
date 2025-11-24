-- Add Resend columns if they don't exist (safe to run multiple times)
ALTER TABLE tenant_configs
ADD COLUMN IF NOT EXISTS email_provider VARCHAR(50),
ADD COLUMN IF NOT EXISTS resend_key VARCHAR(255),
ADD COLUMN IF NOT EXISTS resend_from VARCHAR(255);

-- Update your tenant configuration to use Resend
-- IMPORTANT: Replace 'your_tenant_id' with your actual tenant ID
UPDATE tenant_configs
SET email_provider = 'resend',
    resend_key = 're_Qo2uF8Lz_NQHAuasWTXN9z8FkZW5veKhC',
    resend_from = 'noreply@yourdomain.com'  -- Replace with your actual from address
WHERE tenant_id = 'your_tenant_id';  -- Replace with your actual tenant ID

-- Verify the update
SELECT
    tenant_id,
    email_provider,
    CASE
        WHEN resend_key IS NOT NULL THEN 'Configured ✓'
        ELSE 'Not configured ✗'
    END as resend_status,
    resend_from
FROM tenant_configs;
