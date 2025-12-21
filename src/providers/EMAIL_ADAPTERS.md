# Email Adapter Pattern

This directory implements the **Adapter Design Pattern** for email providers, making it trivial to switch between different email services without changing your business logic.

## Architecture

```
┌─────────────────────┐
│  Business Logic     │
│  (Job Handlers)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  EmailService       │  ← Factory/Facade
│  (email_service.py) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  EmailAdapter       │  ← Interface (Contract)
│  (email_adapter.py) │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌─────────┐
│SendGrid │  │ Resend  │  ← Concrete Implementations
│ Adapter │  │ Adapter │
└─────────┘  └─────────┘
```

## Components

### 1. EmailAdapter (Interface)
**File:** `email_adapter.py`

Defines the contract that all email providers must implement:
- `EmailMessage` - Standard message format
- `EmailResponse` - Standard response format
- `EmailAdapter` - Abstract base class with `send_email()` method

### 2. Concrete Adapters

**SendGridAdapter** (`sendgrid_adapter.py`)
- Uses SendGrid Python SDK
- Supports HTML, CC, BCC, Reply-To
- Requires: `sendgrid_key` in config

**ResendAdapter** (`resend_adapter.py`)
- Uses Resend REST API
- Supports HTML, CC, BCC, Reply-To
- Requires: `resend_key` in config

### 3. EmailService (Facade)
**File:** `email_service.py`

Provides a clean, unified interface for sending emails:
- Automatically selects the right adapter based on config
- Factory function for easy instantiation
- Supports registering custom adapters

## Usage

### Basic Usage (Automatic Provider Detection)

```python
from src.providers.messaging import send_email_via_sendgrid

# The function now auto-detects provider from config
tenant_config = {
    'sendgrid_key': 'SG.xxx',  # Will use SendGrid
    'sendgrid_from': 'noreply@example.com'
}

send_email_via_sendgrid(
    tenant_config=tenant_config,
    to='user@example.com',
    subject='Hello',
    body='Test email'
)
```

### Switching to Resend

Just change the config keys:

```python
tenant_config = {
    'resend_key': 're_xxx',  # Will automatically use Resend
    'resend_from': 'noreply@example.com'
}

# Same function call works!
send_email_via_sendgrid(tenant_config, to='...', subject='...', body='...')
```

### Explicit Provider Selection

```python
tenant_config = {
    'email_provider': 'resend',  # Explicitly set provider
    'resend_key': 're_xxx',
    'resend_from': 'noreply@example.com'
}
```

### Direct EmailService Usage

```python
from src.providers.email_service import EmailService

# Create service with specific provider
service = EmailService(provider='resend')

# Send email
response = service.send_email(
    to='user@example.com',
    subject='Hello',
    body='Test email',
    config=tenant_config,
    html_body='<h1>Test email</h1>',  # Optional HTML
    cc=['cc@example.com'],             # Optional CC
    reply_to='reply@example.com'       # Optional Reply-To
)

if response.success:
    print(f'Sent! Message ID: {response.message_id}')
else:
    print(f'Failed: {response.error}')
```

## Adding a New Email Provider

To add support for a new provider (e.g., Mailgun, AWS SES):

1. **Create adapter class** (e.g., `mailgun_adapter.py`):

```python
from src.providers.email_adapter import EmailAdapter, EmailMessage, EmailResponse

class MailgunAdapter(EmailAdapter):
    def get_provider_name(self) -> str:
        return "Mailgun"

    def send_email(self, message: EmailMessage, config: dict) -> EmailResponse:
        # Implement Mailgun API call
        api_key = config.get('mailgun_key')
        # ... send logic ...
        return EmailResponse(success=True, message_id='...')
```

2. **Register the adapter**:

```python
from src.providers.email_service import EmailService
from my_adapters import MailgunAdapter

EmailService.register_adapter('mailgun', MailgunAdapter)
```

3. **Use it**:

```python
tenant_config = {
    'email_provider': 'mailgun',
    'mailgun_key': 'key-xxx',
    'mailgun_domain': 'mg.example.com'
}
```

## Configuration Reference

### SendGrid
```python
{
    'email_provider': 'sendgrid',  # Optional (auto-detected)
    'sendgrid_key': 'SG.xxx',      # Required
    'sendgrid_from': 'no-reply@example.com'  # Optional default
}
```

### Resend
```python
{
    'email_provider': 'resend',    # Optional (auto-detected)
    'resend_key': 're_xxx',        # Required
    'resend_from': 'no-reply@example.com'  # Optional default
}
```

## Benefits of This Pattern

1. **Decoupling** - Business logic doesn't depend on specific vendors
2. **Flexibility** - Switch providers by changing config (no code changes)
3. **Testability** - Easy to create mock adapters for testing
4. **Extensibility** - Add new providers without modifying existing code
5. **Maintainability** - Each adapter is isolated and focused

## Database Schema

To support per-tenant provider selection, add to `tenant_configs`:

```sql
ALTER TABLE tenant_configs ADD COLUMN email_provider VARCHAR(50);
ALTER TABLE tenant_configs ADD COLUMN resend_key VARCHAR(255);
ALTER TABLE tenant_configs ADD COLUMN resend_from VARCHAR(255);
```

Now each tenant can use a different email provider!
