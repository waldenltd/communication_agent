# Tenant Database Schema Validation Report

## Summary

**Database Inspected:** YearRound (localhost)

**Result:** The actual tenant database schema **aligns well** with the Communication Agent plan. The migration 003 was a simplified test schema - the real database has the required tables.

---

## Schema Validation Results

### 1. Equipment Table ✓ EXISTS

| Plan Expects | Actual Schema | Status |
|--------------|---------------|--------|
| `equipment_id` | `equipment_id` (bigint, PK) | ✓ Match |
| `customer_id` | `customer_id` (bigint, FK) | ✓ Match |
| `equipment_type` | `equipment_type` (text) | ✓ Match |
| `equipment_make` | `equipment_make` (text) | ✓ Match |
| `equipment_model` | `equipment_model` (text) | ✓ Match |
| `date_sold` | `date_sold` (date) | ✓ Match |
| `machine_hours` | `machine_hours` (numeric) | ✓ Match |
| `warranty_end_date` | ❌ Not present | ⚠️ Phase 4 |

**Additional useful columns:**
- `last_service_date` (date)
- `last_service_hours` (numeric)
- `equipment_serial_number` (text)
- `engine_make`, `engine_model`, `engine_type`

**Data Quality Note:**
- 14,791 total equipment records
- Only 33 have `date_sold` populated (0.2%)
- All have `machine_hours` (defaults to 0)

---

### 2. Work Orders Table ✓ EXISTS

| Plan Expects | Actual Schema | Status |
|--------------|---------------|--------|
| `service_record_id` | `service_record_id` (bigint, PK) | ✓ Match |
| `work_order_number` | `work_order_number` (varchar) | ✓ Match |
| `customer_id` | `customer_id` (bigint, FK) | ✓ Match |
| `equipment_id` | `equipment_id` (bigint, FK) | ✓ Match |
| `picked_up_at` | `picked_up_at` (timestamp) | ✓ Match |

**Additional useful columns:**
- `completed_at` (timestamp)
- `date_completed` (date)
- `detailed_status` (varchar) - e.g., 'Received', 'In Progress', 'Ready', 'Picked Up'
- `ready_notified_at` (timestamp) - when customer was notified ready
- `checked_in_at` (timestamp)

**Data Quality Note:**
- 122,105 total work orders
- 0 have `picked_up_at` populated
- Only 10 have `completed_at` populated
- Post-service survey will need `picked_up_at` or `detailed_status = 'Picked Up'`

---

### 3. Customers Table ✓ EXISTS

| Plan Expects | Actual Schema | Status |
|--------------|---------------|--------|
| `customer_id` | `customer_id` (bigint, PK) | ✓ Match |
| `first_name` | `first_name` (text) | ✓ Match |
| `last_name` | `last_name` (text) | ✓ Match |
| `email` | `email_address` (text) | ⚠️ Different name |

**Additional useful columns:**
- `business_name` (text)
- `last_order_date` (timestamp) - useful for ghost customer detection
- `customer_score` (integer)
- `lifetime_value` (numeric)
- `total_orders` (integer)

**Note:** No `contact_preference` or `do_not_disturb_until` columns. May need to add or use `customer_settings` table.

---

### 4. Phones Table ✓ EXISTS (instead of emails table)

| Plan Expects | Actual Schema | Status |
|--------------|---------------|--------|
| Separate `emails` table | `phones` table | ⚠️ Different |
| Multiple emails per customer | Multiple phones per customer | Similar pattern |

**Phone Types Available:**
- Cell, Mobile, Home, Work, Daytime, Fax, Other

**For SMS:** Query phones table for `phone_type IN ('Cell', 'Mobile')`

---

### 5. Email Templates Table ✓ EXISTS

| Plan Expects | Actual Schema | Status |
|--------------|---------------|--------|
| Template storage | `email_templates` table | ✓ Exists |

**Schema:**
- `template_code` (varchar) - unique identifier
- `subject` (varchar) - with `{{variables}}`
- `body_html` (text)
- `body_text` (text)
- `available_variables` (text[])
- `tenant_id` (varchar) - multi-tenant support
- `category` (varchar) - reminder, marketing, transactional

**Existing Templates:**
| Code | Category | Subject |
|------|----------|---------|
| `service_reminder` | reminder | Time for your {{equipment_name}} service! |
| `spring_tuneup` | marketing | Get Your Equipment Ready for Spring! |
| `winterization` | marketing | Prepare Your Equipment for Winter |
| `win_back` | marketing | We Miss You, {{customer_name}}! |
| `post_purchase` | transactional | Thank You for Choosing {{dealer_name}}! |

---

## Column Name Mapping

For implementation, use these actual column names:

| Plan Reference | Actual Column |
|----------------|---------------|
| `equipment.equipment_id` | `equipment.equipment_id` |
| `equipment.date_sold` | `equipment.date_sold` |
| `equipment.equipment_make` | `equipment.equipment_make` |
| `equipment.equipment_model` | `equipment.equipment_model` |
| `equipment.equipment_type` | `equipment.equipment_type` |
| `work_orders.service_record_id` | `work_orders.service_record_id` |
| `work_orders.picked_up_at` | `work_orders.picked_up_at` |
| `customers.customer_id` | `customers.customer_id` |
| `customers.email` | `customers.email_address` |
| `emails.email` | `customers.email_address` (on customers table) |

---

## Data Quality Issues to Address

### 1. Equipment `date_sold` - Critical for 7-Day Check-In

Only 33 of 14,791 equipment records have `date_sold` populated.

**Impact:** Seven-day check-in job will find very few candidates.

**Recommendation:** Backfill `date_sold` from sales history or work order creation dates.

### 2. Work Orders `picked_up_at` - Critical for Post-Service Survey

Zero work orders have `picked_up_at` populated.

**Impact:** Post-service survey job will find no candidates.

**Alternative Approaches:**
1. Use `detailed_status = 'Picked Up'` with `last_status_change_at`
2. Use `date_completed` + delay
3. Start populating `picked_up_at` going forward

### 3. Customer Contact Preferences

No `contact_preference` column on customers table.

**Options:**
1. Add column to customers table
2. Use `customer_settings` table
3. Default to email if `email_address` exists

---

## Recommended Query Patterns

### Seven Day Check-In
```sql
SELECT e.equipment_id,
       e.customer_id,
       e.equipment_type,
       e.equipment_make,
       e.equipment_model,
       c.first_name,
       c.last_name,
       c.email_address
FROM equipment e
JOIN customers c ON c.customer_id = e.customer_id
WHERE e.date_sold = CURRENT_DATE - INTERVAL '7 days'
  AND c.email_address IS NOT NULL
  AND c.email_address != '';
```

### Post-Service Survey (using status)
```sql
SELECT wo.service_record_id,
       wo.work_order_number,
       wo.customer_id,
       wo.last_status_change_at AS picked_up_at,
       c.first_name,
       c.last_name,
       c.email_address
FROM work_orders wo
JOIN customers c ON c.customer_id = wo.customer_id
WHERE wo.detailed_status = 'Picked Up'
  AND wo.last_status_change_at >= NOW() - INTERVAL '72 hours'
  AND wo.last_status_change_at <= NOW() - INTERVAL '48 hours'
  AND c.email_address IS NOT NULL;
```

### Annual Tune-Up Reminder
```sql
SELECT e.equipment_id,
       e.customer_id,
       e.date_sold,
       EXTRACT(YEAR FROM AGE(e.date_sold)) AS years_owned,
       c.first_name,
       c.last_name,
       c.email_address
FROM equipment e
JOIN customers c ON c.customer_id = e.customer_id
WHERE DATE_PART('month', e.date_sold) = DATE_PART('month', CURRENT_DATE + INTERVAL '14 days')
  AND DATE_PART('day', e.date_sold) = DATE_PART('day', CURRENT_DATE + INTERVAL '14 days')
  AND e.date_sold < CURRENT_DATE - INTERVAL '1 year'
  AND c.email_address IS NOT NULL;
```

### Ghost Customer Detection
```sql
SELECT c.customer_id,
       c.first_name,
       c.last_name,
       c.email_address,
       c.last_order_date
FROM customers c
WHERE c.last_order_date < NOW() - INTERVAL '12 months'
  AND c.email_address IS NOT NULL
  AND c.total_orders > 0;
```

### Get Primary Phone (for SMS)
```sql
SELECT phone_number
FROM phones
WHERE customer_id = $1
  AND phone_type IN ('Cell', 'Mobile')
ORDER BY created_at DESC
LIMIT 1;
```

---

## Implementation Readiness

| Job | Schema Ready | Data Ready | Notes |
|-----|--------------|------------|-------|
| Seven Day Check-In | ✓ | ⚠️ | Need `date_sold` populated |
| Post-Service Survey | ✓ | ⚠️ | Use `detailed_status` instead of `picked_up_at` |
| Annual Tune-Up | ✓ | ⚠️ | Need `date_sold` populated |
| Seasonal Reminders | ✓ | ✓ | Can query all equipment |
| Ghost Customer | ✓ | ✓ | `last_order_date` exists |
| Usage-Based Alerts | ✓ | ✓ | `machine_hours` exists |
| Warranty Expiration | ❌ | ❌ | Need `warranty_end_date` column |

---

## Next Steps

1. **Proceed with implementation** using actual schema
2. **Update tenant_data_gateway.py** with correct column names
3. **Address data quality:**
   - Backfill `date_sold` on equipment
   - Start tracking `picked_up_at` on work orders
4. **Add `warranty_end_date`** column if needed (Phase 4)
5. **Leverage existing `email_templates`** table for template storage
