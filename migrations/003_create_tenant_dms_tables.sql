-- Migration: 003_create_tenant_dms_tables
-- Description: Create customers, sales, appointments, and invoices tables
-- Target Database: Tenant DMS Database (run on each tenant's database)
-- Created: 2024-12-20
--
-- NOTE: This script should be run on each tenant's DMS database, NOT the central DB.
-- These tables store tenant-specific data for service reminders, appointments, and invoices.

-- ============================================================================
-- CUSTOMERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone_mobile VARCHAR(20),
    phone_home VARCHAR(20),
    phone_work VARCHAR(20),
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'USA',
    contact_preference VARCHAR(50) DEFAULT 'email',
    do_not_disturb_until TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_customers_contact_preference CHECK (
        contact_preference IN ('email', 'sms', 'phone', 'mail', 'do_not_contact')
    )
);

COMMENT ON TABLE public.customers IS 'Customer master table for tenant DMS';
COMMENT ON COLUMN public.customers.contact_preference IS 'Preferred contact method: email, sms, phone, mail, do_not_contact';
COMMENT ON COLUMN public.customers.do_not_disturb_until IS 'Suppress all communications until this date';

-- Customer indexes
CREATE INDEX IF NOT EXISTS idx_customers_email ON public.customers (email);
CREATE INDEX IF NOT EXISTS idx_customers_phone_mobile ON public.customers (phone_mobile);
CREATE INDEX IF NOT EXISTS idx_customers_name ON public.customers (last_name, first_name);

-- ============================================================================
-- SALES TABLE
-- Used for service reminders (2-year equipment tune-up notifications)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.sales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    sale_number VARCHAR(50),
    purchase_date TIMESTAMP WITH TIME ZONE NOT NULL,
    model VARCHAR(255),
    serial_number VARCHAR(100),
    manufacturer VARCHAR(255),
    product_category VARCHAR(100),
    sale_amount NUMERIC(12, 2),
    salesperson VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_sales_customer
        FOREIGN KEY (customer_id)
        REFERENCES public.customers (id)
        ON DELETE CASCADE
);

COMMENT ON TABLE public.sales IS 'Equipment sales records for service reminder tracking';
COMMENT ON COLUMN public.sales.purchase_date IS 'Used to calculate 2-year service reminder window';
COMMENT ON COLUMN public.sales.model IS 'Equipment model for personalized service reminders';
COMMENT ON COLUMN public.sales.serial_number IS 'Equipment serial number for identification';

-- Sales indexes
CREATE INDEX IF NOT EXISTS idx_sales_customer_id ON public.sales (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_purchase_date ON public.sales (purchase_date);
CREATE INDEX IF NOT EXISTS idx_sales_serial_number ON public.sales (serial_number);

-- Index for service reminder query (purchases 23-25 months ago)
CREATE INDEX IF NOT EXISTS idx_sales_service_reminder
    ON public.sales (purchase_date, customer_id)
    WHERE purchase_date IS NOT NULL;

-- ============================================================================
-- APPOINTMENTS TABLE
-- Used for appointment confirmation notifications (24 hours before)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    appointment_number VARCHAR(50),
    scheduled_start TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    appointment_type VARCHAR(100),
    service_advisor VARCHAR(100),
    technician VARCHAR(100),
    equipment_id UUID,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'scheduled',
    confirmation_sent BOOLEAN DEFAULT FALSE,
    reminder_sent BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_appointments_customer
        FOREIGN KEY (customer_id)
        REFERENCES public.customers (id)
        ON DELETE CASCADE,

    CONSTRAINT chk_appointments_status CHECK (
        status IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show')
    )
);

COMMENT ON TABLE public.appointments IS 'Service appointments for confirmation notifications';
COMMENT ON COLUMN public.appointments.scheduled_start IS 'Appointment start time - used for 24-hour confirmation window';
COMMENT ON COLUMN public.appointments.confirmation_sent IS 'Flag to prevent duplicate confirmation messages';

-- Appointments indexes
CREATE INDEX IF NOT EXISTS idx_appointments_customer_id ON public.appointments (customer_id);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled_start ON public.appointments (scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON public.appointments (status);

-- Index for appointment confirmation query (scheduled 24-25 hours from now)
CREATE INDEX IF NOT EXISTS idx_appointments_confirmation_window
    ON public.appointments (scheduled_start, customer_id)
    WHERE status = 'scheduled' AND confirmation_sent = FALSE;

-- ============================================================================
-- INVOICES TABLE
-- Used for past-due payment reminder notifications (30+ days overdue)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    invoice_number VARCHAR(50),
    invoice_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    amount_paid NUMERIC(12, 2) NOT NULL DEFAULT 0,
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    work_order_id UUID,
    sales_order_id UUID,
    payment_terms VARCHAR(50),
    notes TEXT,
    last_reminder_sent_at TIMESTAMP WITH TIME ZONE,
    reminder_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_invoices_customer
        FOREIGN KEY (customer_id)
        REFERENCES public.customers (id)
        ON DELETE CASCADE,

    CONSTRAINT chk_invoices_status CHECK (
        status IN ('draft', 'open', 'paid', 'partial', 'overdue', 'void', 'collections')
    )
);

COMMENT ON TABLE public.invoices IS 'Customer invoices for payment reminder notifications';
COMMENT ON COLUMN public.invoices.due_date IS 'Payment due date - used to calculate 30-day overdue window';
COMMENT ON COLUMN public.invoices.balance IS 'Outstanding balance - reminders only sent when balance > 0';
COMMENT ON COLUMN public.invoices.last_reminder_sent_at IS 'Track when last reminder was sent to prevent spam';
COMMENT ON COLUMN public.invoices.reminder_count IS 'Number of reminders sent for this invoice';

-- Invoices indexes
CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON public.invoices (customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date ON public.invoices (due_date);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON public.invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_balance ON public.invoices (balance) WHERE balance > 0;

-- Index for past-due invoice query (30+ days overdue with balance > 0)
CREATE INDEX IF NOT EXISTS idx_invoices_past_due
    ON public.invoices (due_date, customer_id)
    WHERE balance > 0 AND status NOT IN ('paid', 'void');

-- ============================================================================
-- TRIGGERS FOR AUTO-UPDATING updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Customers trigger
DROP TRIGGER IF EXISTS update_customers_updated_at ON public.customers;
CREATE TRIGGER update_customers_updated_at
    BEFORE UPDATE ON public.customers
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- Sales trigger
DROP TRIGGER IF EXISTS update_sales_updated_at ON public.sales;
CREATE TRIGGER update_sales_updated_at
    BEFORE UPDATE ON public.sales
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- Appointments trigger
DROP TRIGGER IF EXISTS update_appointments_updated_at ON public.appointments;
CREATE TRIGGER update_appointments_updated_at
    BEFORE UPDATE ON public.appointments
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- Invoices trigger
DROP TRIGGER IF EXISTS update_invoices_updated_at ON public.invoices;
CREATE TRIGGER update_invoices_updated_at
    BEFORE UPDATE ON public.invoices
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
