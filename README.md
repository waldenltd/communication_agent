## Communication Agent MVP

This repository contains the first-cut worker service that fulfills the DMS Communication Agent specification. It is designed to run as a single process that polls a central `communication_jobs` table, enforces tenant-specific rules, and proactively creates new communication jobs.

### Key Capabilities

- **Multi-tenant worker** that claims jobs via `SELECT … FOR UPDATE SKIP LOCKED` semantics to stay idempotent.
- **Channel handlers** for `send_sms`, `send_email`, and `notify_customer`, including quiet-hour awareness and per-customer contact preference checks.
- **Smart retries** with exponential-style `process_after` scheduling, capped attempts, and automatic SMS→email fallback on persistent failures.
- **Proactive schedulers** that scan tenant DMS databases for:
  - Customers due for a 2-year service reminder.
  - Appointments occurring 24–25 hours from now that need confirmation texts.
  - Past-due invoices (30+ days) that require polite reminder emails.

### Running the Agent

First, install the dependencies:

```bash
pip install -r requirements.txt
```

Then run the agent:

```bash
CENTRAL_DB_URL=postgres://user:pass@host:5432/central python main.py
```

Environment variables (all optional unless noted):

| Variable | Purpose | Default |
| --- | --- | --- |
| `CENTRAL_DB_URL` | Postgres connection string for the central queue/config DB | `postgres://dms_agent@localhost:5432/dms_communications` |
| `POLL_INTERVAL_MS` | Worker polling cadence | `5000` |
| `MAX_CONCURRENT_JOBS` | Number of simultaneous jobs | `5` |
| `RETRY_DELAY_MINUTES` | Delay between retries | `5` |
| `MAX_RETRIES` | Attempts before failure/fallback | `3` |
| `SERVICE_REMINDER_HOUR_UTC` | Hour (UTC) to run service reminders | `14` |
| `INVOICE_REMINDER_HOUR_UTC` | Hour (UTC) to run invoice reminders | `13` |
| `APPOINTMENT_CONFIRMATION_INTERVAL_MS` | Override hourly confirmation sweep | `3600000` |

`.env` files are supported via the optional `ENV_FILE` var.

### Database Expectations

#### communication_jobs

| Column | Notes |
| --- | --- |
| `id` (PK) | bigint |
| `tenant_id` | Matches tenant config |
| `job_type` | `send_sms`, `send_email`, `notify_customer`, etc. |
| `payload` | `jsonb` with data such as `{ "to": "...", "body": "...", "customer_id": 42 }` |
| `status` | `pending`, `processing`, `complete`, `failed`, `failed_fallback_email` |
| `retry_count` | int |
| `last_error` | text |
| `process_after` | timestamp |
| `created_at` | timestamp |

#### tenant_configs

This MVP expects the following fields (in addition to any encryption at rest you use):

| Column | Purpose |
| --- | --- |
| `tenant_id` | Primary key |
| `twilio_sid`, `twilio_auth_token`, `twilio_from_number` | Twilio credentials |
| `sendgrid_key`, `sendgrid_from` | Email credentials |
| `quiet_hours_start`, `quiet_hours_end` | e.g., `21:00` → `08:00` |
| `dms_connection_string` | Connection string to the tenant’s operational DB |

The tenant database is expected to expose `customers`, `sales`, `appointments`, and `invoices` tables similar to the schema outlined in the spec. Adjust the SQL inside `src/db/tenant_data_gateway.py` if your table/column names differ.

### Code Structure

- `main.py` — bootstrapper that wires the job processor and proactive scheduler.
- `src/jobs/job_processor.py` — polling loop, retry/defer logic, fallback creation.
- `src/jobs/handlers/` — per-job handlers for SMS, email, and notify workflows.
- `src/jobs/job_repository.py` — shared data-access helpers for the queue table.
- `src/db/` — central DB access and tenant-data gateway abstractions.
- `src/providers/messaging.py` — Twilio and SendGrid integrations.
- `src/scheduler.py` — background tasks that generate new revenue/operational jobs.
- `src/config.py` — configuration management with environment variables.
- `src/logger.py` — structured JSON logging.

### Extending the Agent

- Add new handler files under `src/jobs/handlers/` and register them in `job_processor.py`.
- Introduce additional proactive generators by creating new methods in `Scheduler`.
- Implement LLM-driven logic or new channels (WhatsApp, Messenger, etc.) by attaching new providers and job types; the repository structure keeps channel code isolated.

### Notes & Assumptions

- Twilio/SendGrid calls are real HTTP requests; ensure credentials are valid and network access is permitted in your deployment environment.
- Tenant DMS schemas may not exactly match the placeholder SQL; adapt the queries accordingly.
- The MVP defers non-urgent jobs during quiet hours based on the tenant window and a `payload.urgent` flag.
- All schema modifications (extra columns such as `twilio_auth_token`, `dms_connection_string`) are assumptions for this MVP and should be reflected in your migrations.
