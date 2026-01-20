# Communication Agent - System Overview

## Purpose
A **multi-tenant automated customer communication system** for power equipment dealerships. It sends personalized emails and SMS messages to customers based on triggers like equipment purchases, service completions, and time-based reminders.

---

## Architecture

### Three Operating Modes (`main.py`)

| Mode | Description |
|------|-------------|
| **Legacy** | Traditional job queue processor with scheduled tasks |
| **Level 2 Agent** | AI-powered autonomous agent with ReAct reasoning loop |
| **Hybrid** | Both systems running in parallel |

---

## Core Components

### 1. Job Processor (`src/jobs/job_processor.py`)
- Polls `communication_jobs` table for pending work
- Uses `SELECT FOR UPDATE SKIP LOCKED` for concurrent processing
- Supports 3 job types: `send_email`, `send_sms`, `notify_customer`
- **Quiet Hours Enforcement**: Delays messages during configured hours (e.g., 9pm-8am)
- **Retry Logic**: 3 retries with exponential backoff
- **SMS→Email Fallback**: If SMS fails, creates email job as backup

### 2. Scheduler (`src/scheduler.py`)
Runs recurring tasks to find customers needing communication:

| Job | Schedule | What It Does |
|-----|----------|--------------|
| `seven_day_checkin` | Daily | Emails customers 7 days after equipment purchase |
| `post_service_survey` | Daily | Survey emails 48-72 hours after service pickup |
| `annual_tuneup` | Daily | Tune-up reminders 14 days before purchase anniversary |
| `seasonal_reminder` | Daily* | Spring prep (March) / winterization (October) |
| `ghost_customer_winback` | Weekly | "We miss you" emails for inactive customers (12+ months) |
| `anniversary_offer` | Daily | Purchase anniversary celebrations |
| `warranty_expiration` | Daily | Warranty expiring in 30 days warnings |
| `trade_in_alert` | Monthly | Suggests upgrades for old equipment (8+ years, 3+ repairs) |
| `first_service_alert` | Weekly | First service reminders (20+ machine hours) |
| `usage_service_alert` | Weekly | Service interval reminders (every 100 hours) |
| `gmail_inbox_poll` | Every 60s | Polls Gmail for contact form submissions |
| `communication_queue_processor` | Every 30s | Processes external queue items |

### 3. AI Content Generator (`src/providers/ai_content_generator.py`)
- Uses **DeepSeek AI** (OpenAI-compatible API) to generate personalized email content
- **Hybrid Template System**:
  1. First tries database templates with `{{variable}}` substitution
  2. Optionally enhances with AI for personalization
  3. Falls back to pure AI generation if no template
- 15+ event types with customized prompts and fallback templates

### 4. Template Renderer (`src/providers/template_renderer.py`)
- Loads templates from `message_templates` table
- Supports tenant-specific overrides of global defaults
- In-memory caching for performance
- Variable substitution: `{{first_name}}`, `{{equipment_model}}`, etc.

### 5. Email Service (`src/providers/email_service.py`)
- **Adapter Pattern** supporting multiple providers:
  - SendGrid
  - Resend
- Auto-detects provider from tenant configuration
- Supports attachments (PDF receipts)

### 6. SMS Service (`src/providers/messaging.py`)
- **Twilio integration** for SMS delivery
- Per-tenant credentials

### 7. Gmail Integration (`src/providers/gmail_adapter.py`)
- OAuth2 authentication
- Polls inbox for contact form emails
- Parses intent (buying vs. repairing)
- Creates auto-response jobs

---

## Level 2 Agent System (`src/agent/`)

An autonomous AI agent using the **ReAct (Reasoning + Acting)** pattern:

### Components:
| Component | Purpose |
|-----------|---------|
| **Orchestrator** | Sleep/Wake cycle management, job dispatching |
| **ReAct Engine** | Think → Act → Observe loop with tool execution |
| **Context Manager** | Session state persistence across cycles |
| **Personas** | Role definitions (Communication Agent, Scheduler Agent) |
| **Tool Registry** | Available actions: perception, communication, processing, persistence |

### Capabilities:
- Autonomous goal completion
- Multi-step reasoning
- Tool invocation (query DB, send email, etc.)
- State persistence between cycles
- Prometheus metrics export

---

## Database Layer

### Central Database (`src/db/central_db.py`)
- `communication_jobs` - Job queue
- `communication_queue` - External queue (from other systems)
- `message_templates` - Customizable email templates
- `agent_jobs` - Level 2 agent tasks
- `tenants` - Tenant configuration

### Tenant Databases (`src/db/tenant_data_gateway.py`)
Each tenant has their own database with:
- `customers` - Customer records
- `equipment` - Sold equipment
- `work_orders` - Service records
- `emails`, `phones` - Contact info

---

## Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Scheduler    │────▶│  Job Handlers   │────▶│ communication   │
│  (finds work)   │     │ (create jobs)   │     │    _jobs        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Email/SMS      │◀────│  Job Processor  │◀────│  claim_pending  │
│   Provider      │     │ (executes jobs) │     │    _jobs()      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────────┐
        │               │  AI Content     │
        │               │  Generator      │
        │               └─────────────────┘
        │                       │
        ▼                       ▼
   Customer               Template DB
   Inbox                  (optional)
```

---

## Configuration (`src/config.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `CENTRAL_DB_URL` | `postgres://...` | Central database connection |
| `POLL_INTERVAL_MS` | 5000 | Job polling frequency |
| `MAX_CONCURRENT_JOBS` | 5 | Parallel job limit |
| `MAX_RETRIES` | 3 | Retry attempts before failure |
| `RETRY_DELAY_MINUTES` | 5 | Delay between retries |
| `GHOST_CUSTOMER_MONTHS` | 12 | Inactivity threshold for win-back |
| `FIRST_SERVICE_HOURS_THRESHOLD` | 20 | First service trigger (machine hours) |
| `USAGE_SERVICE_HOURS_INTERVAL` | 100 | Service interval (machine hours) |
| `WARRANTY_WARNING_DAYS` | 30 | Days before warranty expiration to warn |
| `TRADE_IN_MIN_AGE_YEARS` | 8 | Equipment age for trade-in suggestions |
| `TRADE_IN_MIN_REPAIR_COUNT` | 3 | Minimum repairs for trade-in suggestions |
| `DEEPSEEK_API_KEY` | - | AI content generation API key |
| `GMAIL_POLL_INTERVAL_MS` | 60000 | Gmail polling frequency |

---

## Deployment

### Docker
```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t communication-agent .
docker run -e CENTRAL_DB_URL=... communication-agent
```

### Environment Variables
Set these in `.env` or pass to Docker:
```bash
CENTRAL_DB_URL=postgres://user:pass@host:5432/db
DEEPSEEK_API_KEY=your-api-key
AGENT_MODE=legacy  # or level2, hybrid
HEALTH_PORT=8080
```

### Health & Metrics
- **Health endpoint**: `GET /health` - Returns JSON status
- **Metrics endpoint**: `GET /metrics` - Prometheus format

---

## File Structure

```
communication_agent/
├── main.py                     # Entry point
├── Dockerfile                  # Production container
├── docker-compose.yml          # Local development
├── requirements.txt            # Python dependencies
├── migrations/                 # Database migrations
│   ├── 002_create_communication_jobs.sql
│   ├── 007_add_source_reference_index.sql
│   └── 008_create_message_templates.sql
├── src/
│   ├── config.py              # Configuration
│   ├── scheduler.py           # Scheduled tasks
│   ├── health.py              # Health endpoints
│   ├── logger.py              # Logging
│   ├── db/
│   │   ├── central_db.py      # Central DB connection
│   │   └── tenant_data_gateway.py  # Tenant DB queries
│   ├── jobs/
│   │   ├── job_processor.py   # Job execution engine
│   │   ├── job_repository.py  # Job CRUD operations
│   │   └── handlers/          # Job type handlers
│   │       ├── send_email.py
│   │       ├── send_sms.py
│   │       ├── seven_day_checkin.py
│   │       ├── post_service_survey.py
│   │       ├── annual_tuneup.py
│   │       ├── seasonal_reminder.py
│   │       ├── ghost_customer.py
│   │       ├── anniversary_offer.py
│   │       ├── warranty_expiration.py
│   │       ├── trade_in_alert.py
│   │       ├── first_service_alert.py
│   │       ├── usage_service_alert.py
│   │       └── poll_gmail_inbox.py
│   ├── providers/
│   │   ├── ai_content_generator.py  # AI email generation
│   │   ├── template_renderer.py     # Template system
│   │   ├── email_service.py         # Email facade
│   │   ├── sendgrid_adapter.py      # SendGrid provider
│   │   ├── resend_adapter.py        # Resend provider
│   │   ├── messaging.py             # SMS (Twilio)
│   │   └── gmail_adapter.py         # Gmail integration
│   └── agent/                  # Level 2 Agent
│       ├── orchestrator.py     # Agent lifecycle
│       ├── react_engine.py     # ReAct reasoning loop
│       ├── context_manager.py  # State management
│       ├── metrics.py          # Prometheus metrics
│       └── tools/              # Agent capabilities
└── docs/
    └── SYSTEM_OVERVIEW.md      # This file
```

---

## Adding New Communication Types

1. **Add event type prompt** in `src/providers/ai_content_generator.py`:
   ```python
   EVENT_TYPE_PROMPTS['my_new_event'] = {
       'system': "You are...",
       'default_subject': 'Subject Line'
   }
   ```

2. **Add fallback template** in the same file's `generate_fallback_content()` function

3. **Add database query** in `src/db/tenant_data_gateway.py`:
   ```python
   def find_my_new_event_candidates(tenant_id):
       ...
   ```

4. **Create handler** in `src/jobs/handlers/my_new_event.py`:
   ```python
   def create_my_new_event_jobs(tenant_id):
       ...
   ```

5. **Register in scheduler** (`src/scheduler.py`):
   - Import the handler
   - Add `schedule_recurring_task()` call in `start()`
   - Add `run_my_new_event()` method

6. **Add database template** (optional) in migration or via `create_tenant_template()`
