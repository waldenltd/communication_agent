# Communication Agent Implementation Plan

## Plan Review Summary

The provided plan is **well-designed and architecturally sound**. It aligns well with the existing codebase infrastructure. Below is an analysis of what exists vs. what needs to be built, followed by a phased implementation roadmap.

---

## Current State Assessment

### Already Implemented ✓

| Component | Status | Location |
|-----------|--------|----------|
| Queue Processing | ✓ Complete | `src/jobs/job_processor.py` |
| Multi-tenant DB Access | ✓ Complete | `src/db/tenant_data_gateway.py` |
| Email Sending (SendGrid/Resend) | ✓ Complete | `src/providers/email_service.py` |
| SMS Sending (Twilio) | ✓ Complete | `src/providers/messaging.py` |
| Job Scheduler Framework | ✓ Complete | `src/scheduler.py` |
| AI Content Generation | ✓ Complete | `src/providers/ai_content_generator.py` |
| Health Check Endpoints | ✓ Complete | `src/health.py` |
| Prometheus Metrics | ✓ Complete | `src/agent/metrics.py` |
| Retry Logic with Backoff | ✓ Complete | `src/jobs/job_processor.py` |
| Quiet Hours Enforcement | ✓ Complete | `src/jobs/job_processor.py` |
| Level 2 Agent (ReAct) | ✓ Complete | `src/agent/` |

### Needs Implementation

| Component | Priority | Complexity |
|-----------|----------|------------|
| Seven Day Check-In Job | High | Low |
| Post-Service Survey Job | High | Low |
| Annual Tune-Up Reminder Job | High | Medium |
| Seasonal Reminders (Spring/Fall) | Medium | Low |
| Purchase Anniversary Offer | Medium | Low |
| Ghost Customer Detection | Medium | Medium |
| Warranty Expiration Warning | Low | Low |
| Trade-In Alert | Low | Medium |
| First Service Alert (usage-based) | Low | Medium* |
| Usage-Based Service Alert | Low | Medium* |
| Educational Content | Low | Low |
| Message Template Storage | Medium | Medium |

*Requires `machine_hours` tracking in tenant DB

---

## Implementation Phases

### Phase 1: Core Scheduled Jobs (Priority: High)

**Goal:** Implement the most valuable customer touchpoint jobs.

#### 1.1 Add New Event Types to AI Content Generator

**File:** `src/providers/ai_content_generator.py`

Add system prompts for:
- `seven_day_checkin`
- `post_service_survey`
- `annual_tuneup`
- `seasonal_reminder`
- `anniversary_offer`
- `winback_missed_you`
- `warranty_expiration`
- `trade_in_alert`

#### 1.2 Add Tenant Data Queries

**File:** `src/db/tenant_data_gateway.py`

Add methods:
```python
def find_seven_day_checkin_candidates(tenant_id: str) -> List[Dict]:
    """Equipment sold exactly 7 days ago"""

def find_post_service_survey_candidates(tenant_id: str) -> List[Dict]:
    """Work orders picked up 48-72 hours ago"""

def find_annual_tuneup_candidates(tenant_id: str) -> List[Dict]:
    """Equipment with anniversary in 14 days"""

def find_ghost_customers(tenant_id: str, months: int = 12) -> List[Dict]:
    """Customers with no work orders in N months"""
```

#### 1.3 Create Job Handlers

**Directory:** `src/jobs/handlers/`

Create new handlers:
- `seven_day_checkin.py`
- `post_service_survey.py`
- `annual_tuneup.py`

Each handler:
1. Queries candidates from tenant DB
2. Checks for existing queue entries (deduplication)
3. Generates content via AI
4. Inserts `communication_jobs` entries

#### 1.4 Register Jobs in Scheduler

**File:** `src/scheduler.py`

Add scheduled tasks:
```python
# Daily at 9:00 AM UTC
schedule_seven_day_checkin()

# Daily at 10:00 AM UTC
schedule_post_service_survey()

# Daily at 9:00 AM UTC
schedule_annual_tuneup()
```

#### 1.5 Configuration

**File:** `src/config.py`

Add environment variables:
```python
SEVEN_DAY_CHECKIN_HOUR_UTC = int(os.getenv("SEVEN_DAY_CHECKIN_HOUR_UTC", "14"))
POST_SERVICE_SURVEY_HOUR_UTC = int(os.getenv("POST_SERVICE_SURVEY_HOUR_UTC", "15"))
ANNUAL_TUNEUP_HOUR_UTC = int(os.getenv("ANNUAL_TUNEUP_HOUR_UTC", "14"))
```

---

### Phase 2: Seasonal & Lifecycle Jobs (Priority: Medium)

#### 2.1 Seasonal Reminder Jobs

**Handler:** `src/jobs/handlers/seasonal_reminder.py`

```python
def schedule_spring_reminder():
    """Run on March 1st - spring service prep"""

def schedule_fall_reminder():
    """Run on October 1st - winterization"""
```

#### 2.2 Anniversary & Win-Back Jobs

**Handlers:**
- `src/jobs/handlers/anniversary_offer.py` - 7 days before purchase anniversary
- `src/jobs/handlers/winback.py` - Ghost customer detection (weekly)

#### 2.3 Warranty Expiration Job

**Handler:** `src/jobs/handlers/warranty_expiration.py`

Query equipment with warranty expiring in 30 days.

**Note:** Requires `warranty_end_date` field in equipment table.

---

### Phase 3: Message Template System (Priority: Medium)

#### 3.1 Template Storage Options

**Option A: Database Templates (Recommended)**

Create migration:
```sql
CREATE TABLE message_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50),  -- NULL = global default
    event_type VARCHAR(100) NOT NULL,
    communication_type VARCHAR(20) DEFAULT 'email',
    subject_template TEXT,
    body_html_template TEXT,
    body_text_template TEXT,
    variables JSONB,  -- Available variables documentation
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, event_type, communication_type)
);
```

**Option B: File-Based Templates**

Directory structure:
```
templates/
  email/
    seven_day_checkin.html
    seven_day_checkin.txt
    post_service_survey.html
    post_service_survey.txt
```

#### 3.2 Template Rendering Service

**File:** `src/providers/template_renderer.py`

```python
class TemplateRenderer:
    def load_template(event_type: str, tenant_id: str = None) -> Template
    def render(template: Template, variables: dict) -> RenderedMessage
```

#### 3.3 Hybrid Approach

Use templates for structure, AI for personalization:
1. Load base template
2. Fill in variables
3. Optionally enhance with AI for tone/personalization

---

### Phase 4: Usage-Based Jobs (Priority: Low)

**Prerequisite:** `machine_hours` field in equipment table.

#### 4.1 First Service Alert

**Query:** Equipment where `machine_hours >= 20` AND no first service alert sent.

#### 4.2 Usage-Based Service Alert

**Query:** Equipment where `machine_hours` crossed 100-hour threshold since last service.

#### 4.3 Trade-In Alert

**Query:** Equipment 8+ years old with high repair history (monthly).

---

### Phase 5: Production Hardening (Priority: High - after core jobs)

#### 5.1 Deduplication Enhancement

Add to `communication_jobs` table:
```sql
ALTER TABLE communication_jobs ADD COLUMN IF NOT EXISTS
    source_reference VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_ref
    ON communication_jobs(tenant_id, job_type, source_reference)
    WHERE source_reference IS NOT NULL;
```

This prevents duplicate jobs for the same event (e.g., same equipment_id + seven_day_checkin).

#### 5.2 Row-Level Locking

Already implemented via `SELECT ... FOR UPDATE SKIP LOCKED` in job_processor.py.

#### 5.3 Graceful Shutdown

Enhance main.py:
```python
def graceful_shutdown(signum, frame):
    logger.info("Shutdown signal received, draining jobs...")
    scheduler.stop()
    job_processor.drain()  # Wait for in-flight jobs
    sys.exit(0)
```

#### 5.4 Dockerization

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

Create `docker-compose.yml` for local development.

---

## Implementation Order (Recommended)

```
Week 1-2: Phase 1 (Core Jobs)
├── 1.1 Add event types to ai_content_generator.py
├── 1.2 Add tenant data queries
├── 1.3 Create job handlers
├── 1.4 Register in scheduler
└── 1.5 Add configuration

Week 3: Phase 5.1-5.3 (Production Hardening)
├── Deduplication indexes
├── Graceful shutdown
└── Testing

Week 4: Phase 2 (Seasonal & Lifecycle)
├── Seasonal reminders
├── Anniversary offer
└── Win-back detection

Week 5: Phase 3 (Templates)
├── Template storage decision
├── Template renderer
└── Migrate existing prompts

Week 6+: Phase 4 (Usage-Based - if DB supports)
├── First service alert
├── Usage-based alerts
└── Trade-in alerts
```

---

## Database Schema Dependencies

The plan assumes these tables exist in tenant databases:

### Required Tables

```sql
-- Equipment table (must have)
equipment (
    equipment_id,
    customer_id,
    equipment_type,
    equipment_make,
    equipment_model,
    date_sold,
    -- Optional for Phase 4:
    machine_hours,
    warranty_end_date
)

-- Work orders table (must have)
work_orders (
    service_record_id,
    work_order_number,
    customer_id,
    picked_up_at,  -- or completion_date
    dropped_off_at
)

-- Customers table (must have)
customers (
    customer_id,
    first_name,
    last_name
)

-- Emails table (must have)
emails (
    email_id,
    customer_id,
    email,
    is_primary
)
```

### Action Item

Verify tenant database schemas match these requirements. Run exploration query on a sample tenant DB.

---

## Testing Strategy

### Unit Tests

```
tests/
  test_handlers/
    test_seven_day_checkin.py
    test_post_service_survey.py
    test_annual_tuneup.py
  test_providers/
    test_template_renderer.py
    test_ai_content_generator.py
```

### Integration Tests

1. Test job creation from scheduler
2. Test job processing to email send
3. Test deduplication logic
4. Test quiet hours enforcement

### E2E Tests

1. Create test tenant with sample data
2. Run scheduler cycle
3. Verify jobs created
4. Process jobs
5. Verify emails sent (use sandbox/test mode)

---

## Configuration Summary

### New Environment Variables

```bash
# Job schedules (hour in UTC)
SEVEN_DAY_CHECKIN_HOUR_UTC=14
POST_SERVICE_SURVEY_HOUR_UTC=15
ANNUAL_TUNEUP_HOUR_UTC=14
ANNIVERSARY_OFFER_HOUR_UTC=14
SEASONAL_REMINDER_HOUR_UTC=14

# Job intervals
WINBACK_INTERVAL_DAYS=7
TRADE_IN_INTERVAL_DAYS=30

# Feature flags
ENABLE_SEVEN_DAY_CHECKIN=true
ENABLE_POST_SERVICE_SURVEY=true
ENABLE_SEASONAL_REMINDERS=true
ENABLE_WINBACK_DETECTION=true
```

### Tenant Settings (tenants.settings JSONB)

```json
{
  "communication_preferences": {
    "seven_day_checkin_enabled": true,
    "post_service_survey_enabled": true,
    "seasonal_reminders_enabled": true,
    "winback_enabled": true
  }
}
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tenant DB schema mismatch | High | Validate schemas before implementation |
| Email deliverability issues | Medium | Use verified sender domains, monitor bounce rates |
| Over-messaging customers | High | Implement frequency caps, respect preferences |
| Missing customer emails | Medium | Gracefully skip, log for manual follow-up |
| AI content quality | Medium | Review generated content, add human approval option |

---

## Success Metrics

1. **Job Completion Rate:** >99% of scheduled jobs complete successfully
2. **Email Delivery Rate:** >95% delivered (not bounced)
3. **Customer Engagement:** Track open rates, click rates per event type
4. **Error Rate:** <1% job failures after retries

---

## Next Steps

1. **Validate tenant DB schemas** - Confirm equipment, work_orders, customers, emails tables exist
2. **Start Phase 1.1** - Add event types to ai_content_generator.py
3. **Create first job handler** - seven_day_checkin.py as template for others
4. **Test with single tenant** - Before enabling for all tenants
