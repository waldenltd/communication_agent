# Level 2 Agent - Communication Agent

A goal-oriented autonomous system that uses ReAct (Reason + Act) loops to perceive state changes, reason over outcomes, and self-correct.

## Architecture Overview

The Level 2 Agent follows a 4-Layer Stack architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 4: Control Loop                     │
│              AgentOrchestrator (Sleep/Wake Cycles)           │
├─────────────────────────────────────────────────────────────┤
│                  Layer 3: Persistence Layer                  │
│           SessionState (Short-term) + ContextLedger (Long-term)│
├─────────────────────────────────────────────────────────────┤
│                   Layer 2: Action Module                     │
│              ToolRegistry (20 tools, 4 categories)           │
├─────────────────────────────────────────────────────────────┤
│               Layer 1: Persona & Reasoning Core              │
│            AgentPersona + ReActEngine (Thought→Action→Observe)│
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/agent/
├── __init__.py           # Module exports
├── README.md             # This file
├── orchestrator.py       # Layer 4: Control loop with Sleep/Wake cycles
├── context_manager.py    # Layer 3: Session state and context persistence
├── react_engine.py       # Layer 1: Core ReAct reasoning loop
├── job_bridge.py         # Bridge legacy jobs to agent pattern
├── agent_scheduler.py    # Proactive task scheduler
├── metrics.py            # Observability metrics
├── persona/
│   ├── base.py           # Base AgentPersona class
│   └── communication.py  # Communication and Scheduler personas
└── tools/
    ├── base.py           # Tool base class and ToolResult
    ├── registry.py       # Central tool registry
    ├── perception.py     # 8 perception tools
    ├── communication.py  # 3 communication tools
    ├── processing.py     # 4 processing tools
    └── persistence.py    # 5 persistence tools
```

## Run Modes

The agent supports three run modes via the `AGENT_MODE` environment variable:

| Mode | Description |
|------|-------------|
| `legacy` | Original job processor (default) |
| `level2` | New ReAct-based agent with agent scheduler |
| `hybrid` | Both systems running in parallel |

```bash
# Run Level 2 Agent mode
AGENT_MODE=level2 python main.py

# Run hybrid mode
AGENT_MODE=hybrid python main.py
```

## 7-Phase Execution Lifecycle

Each job goes through these phases:

1. **HYDRATE** - Load session state and context from database
2. **PERCEIVE** - Observe current state via perception tools
3. **PLAN** - LLM reasons about next action
4. **EXECUTE** - Call the chosen tool
5. **OBSERVE** - Record tool result
6. **ITERATE** - Loop until goal achieved or max iterations
7. **PERSIST** - Save state for next cycle

## ReAct Pattern

The agent uses the ReAct (Reason + Act) pattern for decision-making:

```
Thought: I need to check if the customer has a valid email address
Action: {"tool": "get_customer_context", "params": {"tenant_id": "t1", "customer_id": "123"}}
Observation: {"email": "john@example.com", "preferences": {"email": true}}
Thought: Customer has valid email, now I'll generate personalized content
Action: {"tool": "generate_email_content", "params": {...}}
...
```

## Available Tools

### Perception Tools (8)
- `check_pending_jobs` - Check pending communication jobs
- `check_queue_items` - Check communication queue items
- `get_customer_context` - Fetch customer details and preferences
- `check_quiet_hours` - Check tenant quiet hours
- `get_tenant_config` - Fetch tenant configuration
- `find_service_reminder_candidates` - Find customers due for service
- `find_upcoming_appointments` - Find appointments needing confirmation
- `find_past_due_invoices` - Find invoices 30+ days past due

### Communication Tools (3)
- `send_email` - Send email via tenant's provider
- `send_sms` - Send SMS via Twilio
- `notify_customer` - Send notification via preferred channel

### Processing Tools (4)
- `generate_email_content` - Generate AI-powered email content
- `fetch_pdf_attachment` - Fetch PDF (work order or sales receipt)
- `get_work_order_details` - Fetch work order equipment details
- `calculate_days_past_due` - Calculate invoice days past due

### Persistence Tools (5)
- `create_communication_job` - Create new communication job
- `update_job_status` - Update job status
- `update_queue_item_status` - Update queue item status
- `check_job_exists` - Check if job already exists
- `save_agent_context` - Save agent session state

## Creating Agent Jobs

### Via Orchestrator

```python
from src.agent import get_orchestrator, start_orchestrator

start_orchestrator()
orchestrator = get_orchestrator()

job_id = orchestrator.create_agent_job(
    tenant_id="tenant-123",
    job_type="communication",
    goal="Send 2-year service reminder to customer C456 for Lawn Mower XL",
    checklist=[
        "Verify customer contact information",
        "Generate personalized reminder content",
        "Send email with service offer",
    ],
)
```

### Via Job Bridge

```python
from src.agent.job_bridge import get_job_bridge

bridge = get_job_bridge()

# Create service reminder job
job_id = bridge.create_service_reminder_job(
    tenant_id="tenant-123",
    customer_id="C456",
    customer_email="john@example.com",
    customer_name="John Doe",
    model="Lawn Mower XL",
    serial_number="SN12345",
)

# Create invoice reminder job
job_id = bridge.create_invoice_reminder_job(
    tenant_id="tenant-123",
    invoice_id="INV-789",
    customer_id="C456",
    customer_email="john@example.com",
    customer_name="John Doe",
    balance=150.00,
    due_date="2024-10-01",
)
```

## Agent Scheduler

The `AgentScheduler` automatically creates jobs for:

| Sweep | Frequency | Description |
|-------|-----------|-------------|
| Service Reminders | Daily at 14:00 UTC | Customers with 2-year-old equipment |
| Appointment Confirmations | Hourly | Appointments in next 24-25 hours |
| Invoice Reminders | Daily at 13:00 UTC | Invoices 30+ days past due |
| Queue Processing | Every 30 seconds | Pending communication queue items |

## Observability

### Health Endpoints

| Endpoint | Description |
|----------|-------------|
| `/health` | Basic liveness check |
| `/ready` | Readiness check (is agent running?) |
| `/status` | Detailed status JSON |
| `/metrics` | Prometheus-format metrics |

### Metrics Tracked

**Orchestrator Metrics:**
- `agent_cycles_total` - Total orchestrator cycles
- `agent_cycles_active` - Currently active cycles
- `agent_cycle_duration_seconds` - Cycle duration histogram

**Job Metrics:**
- `agent_jobs_total` - Total jobs processed (by job_type)
- `agent_jobs_active` - Active jobs
- `agent_jobs_completed_total` - Completed jobs
- `agent_jobs_failed_total` - Failed jobs
- `agent_job_duration_seconds` - Job processing duration

**Tool Metrics:**
- `agent_tool_calls_total` - Tool calls (by tool name)
- `agent_tool_errors_total` - Tool errors (by tool name)
- `agent_tool_duration_seconds` - Tool execution duration

**LLM Metrics:**
- `agent_llm_calls_total` - LLM API calls
- `agent_llm_errors_total` - LLM API errors
- `agent_llm_latency_seconds` - LLM call latency
- `agent_llm_tokens_total` - Total tokens used

**Scheduler Metrics:**
- `agent_scheduler_sweeps_total` - Scheduler sweeps (by type)
- `agent_scheduler_jobs_created_total` - Jobs created by scheduler

## Database Schema

The agent uses the `agent_jobs` table:

```sql
CREATE TABLE agent_jobs (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(100) NOT NULL,
    goal TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    current_step INTEGER DEFAULT 0,
    checklist JSONB DEFAULT '[]',
    context_summary TEXT,
    reasoning_trace JSONB DEFAULT '[]',
    session_state JSONB DEFAULT '{}',
    last_thoughts JSONB DEFAULT '[]',
    source_job_id INTEGER,
    source_reference VARCHAR(255),
    waiting_for_human BOOLEAN DEFAULT false,
    max_iterations INTEGER DEFAULT 20,
    last_error TEXT,
    scheduled_for TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MODE` | `legacy` | Run mode: legacy, level2, hybrid |
| `HEALTH_PORT` | `8080` | Health server port (0 to disable) |
| `DEEPSEEK_API_KEY` | - | DeepSeek API key (required for LLM) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API base URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model name |

## Testing

```bash
# Run unit tests
python scripts/test_agent.py

# Run end-to-end tests
python scripts/test_agent_e2e.py
```

## Adding New Tools

1. Create a tool function in the appropriate category file:

```python
# src/agent/tools/processing.py

def my_new_tool(param1: str, param2: int = 10) -> ToolResult:
    """Tool description."""
    try:
        # Tool logic here
        return ToolResult(
            success=True,
            data={"result": "value"},
            side_effects=["Created record"],
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=str(e),
            needs_retry=True,
        )
```

2. Register the tool in the category's register function:

```python
def register_processing_tools(registry: ToolRegistry):
    # ... existing tools ...

    registry.register(FunctionTool(
        name="my_new_tool",
        description="Description for the LLM",
        function=my_new_tool,
        category=ToolCategory.PROCESSING,
        parameters=[
            ToolParameter("param1", "string", "Parameter description", required=True),
            ToolParameter("param2", "integer", "Optional parameter", required=False),
        ],
    ))
```

## Troubleshooting

### Job stuck in "in_progress"
Check the `last_error` field and reasoning trace:
```sql
SELECT id, goal, last_error, reasoning_trace
FROM agent_jobs
WHERE status = 'in_progress'
ORDER BY updated_at DESC;
```

### High LLM latency
Check the `/metrics` endpoint for `agent_llm_latency_seconds` histogram.

### Tool failures
Check metrics for tool-specific errors:
```
agent_tool_errors_total{tool="send_email"} 5
```

### Scheduler not creating jobs
1. Check if tenants are active: `SELECT * FROM tenants WHERE status = 'Active'`
2. Check scheduler sweep logs for errors
3. Verify source_reference uniqueness (jobs won't be recreated if one exists)
