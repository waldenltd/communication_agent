# Message Templates UI Requirements

## Overview

This document specifies the requirements for building a UI to view and manage message templates used by the Communication Agent. Templates control the content of automated emails and SMS messages sent to customers.

## Database Schema

The `message_templates` table exists in the central database (`dms_admin_db`) with the following structure:

```sql
CREATE TABLE message_templates (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(100),              -- NULL for global templates, tenant_id string for tenant-specific
    event_type VARCHAR(100) NOT NULL,    -- e.g., 'welcome_message', 'seven_day_checkin'
    communication_type VARCHAR(20) NOT NULL DEFAULT 'email',  -- 'email' or 'sms'
    subject_template TEXT,               -- Subject line with {{variables}} (email only)
    body_text_template TEXT NOT NULL,    -- Plain text body with {{variables}}
    body_html_template TEXT,             -- HTML body with {{variables}} (email only)
    variables JSONB DEFAULT '{}',        -- Documentation of available variables
    description TEXT,                    -- Human-readable description of template purpose
    ai_enhance BOOLEAN DEFAULT false,    -- Whether to pass through AI for personalization
    ai_instructions TEXT,                -- Custom instructions for AI enhancement
    is_active BOOLEAN DEFAULT true,      -- Soft delete / disable flag
    version INTEGER DEFAULT 1,           -- Version number for tracking changes
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT message_templates_unique UNIQUE (tenant_id, event_type, communication_type)
);
```

### Key Concepts

1. **Global Templates**: Templates with `tenant_id = NULL` are available to all tenants as defaults
2. **Tenant-Specific Templates**: Templates with a `tenant_id` value override the global template for that tenant
3. **Template Variables**: Use `{{variable_name}}` syntax for dynamic content substitution
4. **AI Enhancement**: When enabled, the rendered template is passed to AI for tone/personalization improvements

## Event Types

The following event types are currently supported:

| Event Type | Description | Communication Type |
|------------|-------------|-------------------|
| `welcome_message` | Sent after new equipment purchase | email |
| `work_order_receipt` | Receipt for work order creation | email |
| `sales_order_receipt` | Receipt for sales order | email |
| `service_reminder` | Reminder for scheduled maintenance | email |
| `appointment_confirmation` | Confirm upcoming appointment | email, sms |
| `invoice_reminder` | Payment reminder for past-due invoices | email |
| `estimate_followup` | Follow-up on provided estimates | email |
| `job_complete` | Notification when service is complete | email |
| `contact_form_buying` | Auto-response to purchase inquiries | email |
| `contact_form_repairing` | Auto-response to repair inquiries | email |
| `seven_day_checkin` | Check-in 7 days after purchase | email |
| `post_service_survey` | Survey request after service completion | email |
| `annual_tuneup` | Annual maintenance reminder | email |
| `ready_for_pickup` | Equipment ready for customer pickup | email, sms |
| `checkin_confirmation` | Equipment check-in confirmation | email |

## Common Template Variables

These variables are commonly available depending on the event type:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{customer_name}}` | Customer's full name | JOHN SMITH |
| `{{first_name}}` | Customer's first name | John |
| `{{company_name}}` | Tenant's company name | Year Round Power Equipment |
| `{{equipment_make}}` | Equipment manufacturer | ARIENS |
| `{{equipment_model}}` | Equipment model | 920025 |
| `{{equipment_type}}` | Type of equipment | SNOW BLOWER |
| `{{work_order_number}}` | Work order reference | 160133 |
| `{{serial_number}}` | Equipment serial number | 123456 |
| `{{appointment_date}}` | Scheduled appointment date | January 25, 2026 |
| `{{invoice_number}}` | Invoice reference | INV-2026-001 |
| `{{amount_due}}` | Outstanding balance | $150.00 |

---

## UI Requirements

### 1. Template List View

**Purpose**: Display all templates with filtering and search capabilities.

#### Layout
- Table/grid view with sortable columns
- Pagination (20 items per page default)

#### Columns to Display
| Column | Description | Sortable |
|--------|-------------|----------|
| Event Type | The event trigger | Yes |
| Communication Type | email/sms badge | Yes |
| Tenant | "Global" or tenant name | Yes |
| Subject | Subject line preview (truncated) | No |
| AI Enhanced | Yes/No indicator | Yes |
| Status | Active/Inactive badge | Yes |
| Version | Version number | Yes |
| Updated | Last modified date | Yes |
| Actions | Edit, Duplicate, Delete buttons | No |

#### Filters
- **Tenant**: Dropdown - "All", "Global Only", or specific tenant
- **Event Type**: Dropdown with all event types
- **Communication Type**: "All", "Email", "SMS"
- **Status**: "All", "Active", "Inactive"
- **AI Enhanced**: "All", "Yes", "No"

#### Search
- Free-text search across: event_type, description, subject_template, body_text_template

#### Actions
- **Create New Template** button (prominent, top-right)
- **Bulk Actions**: Activate, Deactivate, Delete selected

---

### 2. Template Create/Edit Form

**Purpose**: Create new templates or edit existing ones.

#### Form Sections

##### Section 1: Basic Information
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| Tenant | Dropdown (NULL=Global, or tenant list) | Yes | Must select |
| Event Type | Dropdown with predefined options | Yes | Must select |
| Communication Type | Radio: Email / SMS | Yes | Default: Email |
| Description | Text input | No | Max 500 chars |
| Active | Toggle switch | Yes | Default: true |

##### Section 2: Template Content

**For Email:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Subject Template | Text input | Yes | Show variable helper |
| Body (Plain Text) | Textarea | Yes | Show variable helper, monospace font |
| Body (HTML) | Rich text editor or code editor | No | Toggle between WYSIWYG and HTML |

**For SMS:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Body (Plain Text) | Textarea | Yes | Show character count, warn at 160 chars |

##### Section 3: Variables Documentation
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Variables | Key-value editor | No | Add/remove variable names and descriptions |

**Variable Helper Panel** (sidebar or collapsible):
- List of common variables with "Insert" button
- When clicked, inserts `{{variable_name}}` at cursor position

##### Section 4: AI Enhancement
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Enable AI Enhancement | Toggle switch | No | Default: false |
| AI Instructions | Textarea | No | Only shown when AI enabled |

**AI Instructions Help Text:**
> "Provide specific instructions for how AI should enhance this template. Example: 'Make the tone warmer and more personal. Add a seasonal greeting if appropriate.'"

#### Form Actions
- **Save** - Save and return to list
- **Save & Continue Editing** - Save and stay on form
- **Preview** - Show rendered preview with sample data
- **Cancel** - Return to list without saving

#### Validation Rules
1. Combination of (tenant_id, event_type, communication_type) must be unique
2. Subject template required for email type
3. Body text template always required
4. Warn if template contains undefined variables (not in variables JSONB)

---

### 3. Template Preview

**Purpose**: Preview how a template will render with sample data.

#### Features
- Split view: Template on left, rendered output on right
- Sample data input form to customize preview
- Toggle between plain text and HTML preview (for email)
- Mobile preview option for SMS

#### Sample Data
Pre-populate with realistic sample values:
```json
{
  "customer_name": "John Smith",
  "first_name": "John",
  "company_name": "Year Round Power Equipment",
  "equipment_make": "TORO",
  "equipment_model": "20444",
  "equipment_type": "LAWN MOWER",
  "work_order_number": "160133"
}
```

---

### 4. Template Duplication

**Purpose**: Create a new template based on an existing one.

#### Workflow
1. User clicks "Duplicate" on a template
2. Form opens pre-filled with all values from source template
3. User must change at least one of: tenant_id, event_type, or communication_type
4. Version resets to 1 for new template

---

### 5. Template History/Versioning (Future Enhancement)

**Purpose**: Track changes to templates over time.

#### Requirements
- Increment `version` on each save
- Store previous versions in a `message_template_versions` table
- Allow viewing and restoring previous versions

---

## API Endpoints

The UI should interact with these API endpoints:

### Templates CRUD

```
GET    /api/templates                 - List all templates (with filters)
GET    /api/templates/:id             - Get single template
POST   /api/templates                 - Create new template
PUT    /api/templates/:id             - Update template
DELETE /api/templates/:id             - Delete template (soft delete: set is_active=false)
```

### Additional Endpoints

```
GET    /api/templates/event-types     - List available event types
GET    /api/templates/variables       - List common variables with descriptions
POST   /api/templates/:id/duplicate   - Duplicate a template
POST   /api/templates/preview         - Preview template with sample data
GET    /api/tenants                   - List tenants for dropdown
```

### Query Parameters for List Endpoint

```
GET /api/templates?tenant_id=yearround&event_type=welcome_message&communication_type=email&is_active=true&search=welcome&page=1&limit=20&sort=updated_at&order=desc
```

---

## Data Flow

### Template Rendering Flow (for context)

```
1. Event occurs (e.g., equipment purchased)
2. Communication Agent receives event with message_params
3. Agent queries message_templates:
   a. First tries tenant-specific template
   b. Falls back to global template (tenant_id IS NULL)
4. If template found:
   a. Variables are substituted: {{customer_name}} -> "John Smith"
   b. If ai_enhance=true, rendered content passes through AI
5. If no template found:
   a. Falls back to pure AI generation
6. Email/SMS is sent
```

---

## UI/UX Guidelines

### Design Principles
1. **Clarity**: Template editing should feel like editing a document
2. **Safety**: Warn before destructive actions, show clear status indicators
3. **Efficiency**: Quick access to common variables, keyboard shortcuts for power users

### Variable Highlighting
- In the template editor, highlight `{{variables}}` with a distinct color
- Invalid/unknown variables should show a warning indicator

### Responsive Design
- Desktop: Side-by-side preview
- Tablet: Stacked layout with collapsible preview
- Mobile: Basic view/edit only (preview on separate screen)

---

## Error Handling

### Validation Errors
Display inline errors for:
- Missing required fields
- Duplicate template (tenant + event_type + communication_type)
- Invalid variable syntax (unclosed braces)

### API Errors
- Show toast notification for transient errors
- Show inline error for validation failures from API

---

## Sample Template Data

### Example: Welcome Message Template

```json
{
  "id": 1,
  "tenant_id": null,
  "event_type": "welcome_message",
  "communication_type": "email",
  "subject_template": "Welcome! Your New {{equipment_type}} Guide",
  "body_text_template": "Hi {{customer_name}},\n\nCongratulations on your new {{equipment_make}} {{equipment_model}} {{equipment_type}}! We're thrilled you chose us for this purchase.\n\nHere are a few tips to get the most out of your new equipment:\n\n• Read through the owner's manual for important safety and operating instructions\n• Check oil levels before first use and regularly thereafter\n• Keep your equipment clean and stored in a dry place when not in use\n• Schedule your first service after the initial break-in period\n\nIf you have any questions about your new equipment or need assistance, don't hesitate to reach out. We're here to help!\n\nBest regards,\n{{company_name}}",
  "body_html_template": "<p>Hi {{customer_name}},</p>\n<p>Congratulations on your new <strong>{{equipment_make}} {{equipment_model}} {{equipment_type}}</strong>!...</p>",
  "variables": {
    "customer_name": "Customer full name",
    "equipment_make": "Equipment manufacturer",
    "equipment_model": "Equipment model number/name",
    "equipment_type": "Type of equipment",
    "company_name": "Your company name"
  },
  "description": "Welcome email sent to customers after purchasing new equipment",
  "ai_enhance": false,
  "ai_instructions": null,
  "is_active": true,
  "version": 1
}
```

---

## Implementation Notes

### Database Connection
- Connect to `dms_admin_db` (central database)
- Connection string format: `postgres://user:password@host:port/dms_admin_db`

### Tenant List Source
- Query `tenants` table for dropdown: `SELECT tenant_id, tenant_name FROM tenants WHERE status = 'Active'`

### Timestamps
- Always update `updated_at` on save
- Use database timezone (TIMESTAMPTZ)

---

## Acceptance Criteria

### MVP (Phase 1)
- [ ] List view with basic filtering (tenant, event_type, status)
- [ ] Create new template form
- [ ] Edit existing template
- [ ] Delete template (soft delete)
- [ ] Basic preview with sample data

### Phase 2
- [ ] Advanced search across template content
- [ ] Template duplication
- [ ] Bulk actions (activate/deactivate)
- [ ] Rich text HTML editor

### Phase 3
- [ ] Version history and restore
- [ ] Template usage analytics
- [ ] A/B testing support
