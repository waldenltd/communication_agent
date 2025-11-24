# Database Configuration Setup

This guide shows you where and how to configure email and SMS providers for your communication agent.

## 📍 Configuration Location

**All configuration keys are stored in the PostgreSQL database** in the `tenant_configs` table.

There are NO configuration files with API keys - everything is stored securely in the database.

---

## 🗄️ Database Schema

### Current Schema (Minimum Required)

```sql
CREATE TABLE tenant_configs (
    tenant_id VARCHAR(255) PRIMARY KEY,

    -- SMS Configuration (Twilio)
    twilio_sid VARCHAR(255),
    twilio_auth_token VARCHAR(255),
    twilio_from_number VARCHAR(20),

    -- Email Configuration (SendGrid - original)
    sendgrid_key VARCHAR(255),
    sendgrid_from VARCHAR(255),

    -- Operational Settings
    quiet_hours_start TIME,           -- e.g., '21:00'
    quiet_hours_end TIME,             -- e.g., '08:00'
    dms_connection_string TEXT        -- Connection to tenant's DMS database
);
```

### Migration: Add Email Provider Support

To enable switching between SendGrid and Resend, run this migration:

```sql
ALTER TABLE tenant_configs
ADD COLUMN IF NOT EXISTS email_provider VARCHAR(50),
ADD COLUMN IF NOT EXISTS resend_key VARCHAR(255),
ADD COLUMN IF NOT EXISTS resend_from VARCHAR(255);
```

---

## 🔧 Configuration Examples

### Example 1: SendGrid Only (Default)

```sql
INSERT INTO tenant_configs (
    tenant_id,
    twilio_sid,
    twilio_auth_token,
    twilio_from_number,
    sendgrid_key,
    sendgrid_from,
    quiet_hours_start,
    quiet_hours_end,
    dms_connection_string
) VALUES (
    'acme_corp',
    'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'your_twilio_auth_token',
    '+15551234567',
    'SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'noreply@acmecorp.com',
    '21:00',
    '08:00',
    'postgres://user:pass@db.acmecorp.com:5432/acme_dms'
);
```

### Example 2: Resend (Explicit)

```sql
INSERT INTO tenant_configs (
    tenant_id,
    email_provider,
    resend_key,
    resend_from,
    twilio_sid,
    twilio_auth_token,
    twilio_from_number,
    quiet_hours_start,
    quiet_hours_end,
    dms_connection_string
) VALUES (
    'beta_company',
    'resend',
    're_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'noreply@betacompany.com',
    'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'your_twilio_auth_token',
    '+15559876543',
    '22:00',
    '07:00',
    'postgres://user:pass@db.betacompany.com:5432/beta_dms'
);
```

### Example 3: Auto-Detection (Recommended)

Just provide the keys - the system automatically detects which provider to use:

```sql
-- This will use Resend (because resend_key is present)
INSERT INTO tenant_configs (
    tenant_id,
    resend_key,
    resend_from,
    twilio_sid,
    twilio_auth_token,
    twilio_from_number,
    dms_connection_string
) VALUES (
    'gamma_inc',
    're_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'noreply@gammainc.com',
    'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'your_twilio_auth_token',
    '+15551112222',
    'postgres://user:pass@db.gammainc.com:5432/gamma_dms'
);
```

---

## 🔄 Switching Providers

### Switch from SendGrid to Resend

```sql
UPDATE tenant_configs
SET email_provider = 'resend',
    resend_key = 're_your_resend_key_here',
    resend_from = 'noreply@yourdomain.com'
WHERE tenant_id = 'your_tenant_id';
```

**That's it!** The next email sent will use Resend automatically.

### Switch from Resend to SendGrid

```sql
UPDATE tenant_configs
SET email_provider = 'sendgrid'
WHERE tenant_id = 'your_tenant_id';
```

### Remove Provider Preference (Auto-Detect)

```sql
UPDATE tenant_configs
SET email_provider = NULL
WHERE tenant_id = 'your_tenant_id';
```

The system will auto-detect based on which keys are present.

---

## 📊 Configuration Priority

When determining which email provider to use, the system checks in this order:

1. **`email_provider` field** - Explicit setting (highest priority)
2. **`resend_key` presence** - If key exists, use Resend
3. **`sendgrid_key` presence** - If key exists, use SendGrid
4. **Default to SendGrid** - Fallback for backward compatibility

---

## 🔍 Viewing Current Configuration

### Check which provider a tenant is using:

```sql
SELECT
    tenant_id,
    CASE
        WHEN email_provider IS NOT NULL THEN email_provider
        WHEN resend_key IS NOT NULL THEN 'resend (auto)'
        WHEN sendgrid_key IS NOT NULL THEN 'sendgrid (auto)'
        ELSE 'none configured'
    END as active_provider,
    sendgrid_from,
    resend_from,
    quiet_hours_start,
    quiet_hours_end
FROM tenant_configs
WHERE tenant_id = 'your_tenant_id';
```

### See all tenants and their email providers:

```sql
SELECT
    tenant_id,
    COALESCE(email_provider, 'auto-detect') as provider_setting,
    CASE
        WHEN resend_key IS NOT NULL THEN '✓'
        ELSE '✗'
    END as has_resend,
    CASE
        WHEN sendgrid_key IS NOT NULL THEN '✓'
        ELSE '✗'
    END as has_sendgrid
FROM tenant_configs
ORDER BY tenant_id;
```

---

## 🔐 Security Best Practices

1. **Encrypt credentials at rest** - Use PostgreSQL encryption or a secrets manager
2. **Use environment variables** for local development (see `.env` file)
3. **Rotate API keys regularly**
4. **Use separate keys** for each tenant (don't share keys across tenants)
5. **Restrict database access** - Only the application should access `tenant_configs`

### Example: Using PostgreSQL pgcrypto for Encryption

```sql
-- Enable pgcrypto extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Store encrypted
INSERT INTO tenant_configs (tenant_id, sendgrid_key)
VALUES ('tenant1', pgp_sym_encrypt('SG.realkey', 'encryption_password'));

-- Retrieve decrypted
SELECT pgp_sym_decrypt(sendgrid_key::bytea, 'encryption_password')
FROM tenant_configs WHERE tenant_id = 'tenant1';
```

---

## 🧪 Testing Configuration

After adding/updating configuration, test it:

```python
# Python test script
from src.db.tenant_data_gateway import get_tenant_config
from src.providers.email_service import create_email_service

# Load config
config = get_tenant_config('your_tenant_id')

# Check which provider will be used
service = create_email_service(config)
print(f"Provider: {service.adapter.get_provider_name()}")

# Try sending (with valid keys)
response = service.send_email(
    to='test@example.com',
    subject='Test',
    body='Testing email provider',
    config=config
)

print(f"Success: {response.success}")
if not response.success:
    print(f"Error: {response.error}")
```

---

## 📝 Configuration Fields Reference

| Field | Type | Required | Purpose | Example |
|-------|------|----------|---------|---------|
| `tenant_id` | VARCHAR(255) | ✓ | Unique tenant identifier | `'acme_corp'` |
| `twilio_sid` | VARCHAR(255) | ✓ | Twilio Account SID | `'ACxxxxx...'` |
| `twilio_auth_token` | VARCHAR(255) | ✓ | Twilio Auth Token | `'xxxxxx...'` |
| `twilio_from_number` | VARCHAR(20) | ✓ | Twilio phone number | `'+15551234567'` |
| `sendgrid_key` | VARCHAR(255) | * | SendGrid API key | `'SG.xxxx...'` |
| `sendgrid_from` | VARCHAR(255) | ✗ | Default sender email | `'noreply@example.com'` |
| `resend_key` | VARCHAR(255) | * | Resend API key | `'re_xxxx...'` |
| `resend_from` | VARCHAR(255) | ✗ | Default sender email | `'noreply@example.com'` |
| `email_provider` | VARCHAR(50) | ✗ | Explicit provider choice | `'sendgrid'` or `'resend'` |
| `quiet_hours_start` | TIME | ✗ | Start of quiet hours | `'21:00'` |
| `quiet_hours_end` | TIME | ✗ | End of quiet hours | `'08:00'` |
| `dms_connection_string` | TEXT | ✓ | Tenant DMS database | `'postgres://...'` |

\* At least one email provider key (`sendgrid_key` or `resend_key`) is required

---

## 🚨 Troubleshooting

### "Missing SendGrid API key" Error

**Solution:** Add `sendgrid_key` or `resend_key` to `tenant_configs` for that tenant.

```sql
UPDATE tenant_configs
SET sendgrid_key = 'SG.your_key'
WHERE tenant_id = 'your_tenant';
```

### Emails Using Wrong Provider

**Check current configuration:**
```sql
SELECT email_provider, sendgrid_key, resend_key
FROM tenant_configs
WHERE tenant_id = 'your_tenant';
```

**Force specific provider:**
```sql
UPDATE tenant_configs
SET email_provider = 'resend'
WHERE tenant_id = 'your_tenant';
```

### Configuration Not Updating

The system caches tenant configuration. Restart the application after database changes, or clear the cache:

```python
from src.db.tenant_data_gateway import tenant_config_cache
tenant_config_cache.clear()
```

---

## 📚 Related Documentation

- **Email Adapter Pattern:** See `src/providers/EMAIL_ADAPTERS.md`
- **Getting API Keys:**
  - SendGrid: https://app.sendgrid.com/settings/api_keys
  - Resend: https://resend.com/api-keys
  - Twilio: https://console.twilio.com/
