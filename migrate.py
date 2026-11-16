"""
Database Migration Runner for Rathinam Operations Management System.
Idempotent, non-destructive migration script that updates the schema
to match the latest models, tables, columns, and views.

Usage:
    python migrate.py
"""
import sys
import os

# Ensure backend directory is in python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db

MIGRATION_STEPS = [
    (
        "Enum Types",
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cost_behavior_enum') THEN
                CREATE TYPE cost_behavior_enum AS ENUM ('variable', 'semi_variable', 'fixed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entry_status_enum') THEN
                CREATE TYPE entry_status_enum AS ENUM ('draft', 'audited', 'locked');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vendor_type_enum') THEN
                CREATE TYPE vendor_type_enum AS ENUM ('internal', 'catering', 'housekeeping', 'event_manpower', 'fuel_supplier', 'utility', 'maintenance');
            END IF;
        END $$;
        """
    ),
    (
        "Fiscal Years Table",
        """
        CREATE TABLE IF NOT EXISTS fiscal_years (
            id SERIAL PRIMARY KEY,
            year_code VARCHAR(10) NOT NULL UNIQUE,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
    (
        "Billing Periods Table & Module Scoping",
        """
        CREATE TABLE IF NOT EXISTS billing_periods (
            id SERIAL PRIMARY KEY,
            fiscal_year_id INT NOT NULL REFERENCES fiscal_years(id) ON DELETE RESTRICT,
            period_code VARCHAR(20) NOT NULL,
            period_label VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            operating_days INT NOT NULL DEFAULT 30,
            is_closed BOOLEAN NOT NULL DEFAULT false,
            module VARCHAR(50) NOT NULL DEFAULT 'food',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE billing_periods ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';
        ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS billing_periods_period_code_key;
        ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS uq_billing_periods_module_code;
        ALTER TABLE billing_periods ADD CONSTRAINT uq_billing_periods_module_code UNIQUE (module, period_code);
        CREATE INDEX IF NOT EXISTS idx_billing_periods_module_date ON billing_periods (module, start_date);
        """
    ),
    (
        "Vendors Table",
        """
        CREATE TABLE IF NOT EXISTS vendors (
            id SERIAL PRIMARY KEY,
            vendor_code VARCHAR(30) NOT NULL UNIQUE,
            name VARCHAR(150) NOT NULL,
            vendor_type vendor_type_enum NOT NULL DEFAULT 'internal',
            contact_person VARCHAR(100),
            phone VARCHAR(25),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
    (
        "Expense Categories Table & Module Column",
        """
        CREATE TABLE IF NOT EXISTS expense_categories (
            id SERIAL PRIMARY KEY,
            code VARCHAR(30) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            display_order INT NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';
        UPDATE expense_categories SET is_active = true WHERE is_active IS NOT TRUE;
        """
    ),
    (
        "Cost Heads Table",
        """
        CREATE TABLE IF NOT EXISTS cost_heads (
            id SERIAL PRIMARY KEY,
            category_id INT NOT NULL REFERENCES expense_categories(id) ON DELETE RESTRICT,
            default_vendor_id INT REFERENCES vendors(id) ON DELETE SET NULL,
            code VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            cost_behavior cost_behavior_enum NOT NULL DEFAULT 'variable',
            display_order INT NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        UPDATE cost_heads SET is_active = true WHERE is_active IS NOT TRUE;
        """
    ),
    (
        "Monthly Expense Entries Table & Module Segregation",
        """
        CREATE TABLE IF NOT EXISTS monthly_expense_entries (
            id SERIAL PRIMARY KEY,
            module VARCHAR(50) NOT NULL DEFAULT 'food',
            period_id INT NOT NULL REFERENCES billing_periods(id) ON DELETE CASCADE,
            cost_head_id INT NOT NULL REFERENCES cost_heads(id) ON DELETE CASCADE,
            vendor_id INT REFERENCES vendors(id) ON DELETE SET NULL,
            amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            remarks TEXT,
            status entry_status_enum NOT NULL DEFAULT 'draft',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_period_cost_head UNIQUE (period_id, cost_head_id)
        );
        ALTER TABLE monthly_expense_entries ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';
        UPDATE monthly_expense_entries m
        SET module = bp.module
        FROM billing_periods bp
        WHERE m.period_id = bp.id AND (m.module IS NULL OR m.module = 'food');
        ALTER TABLE monthly_expense_entries DROP CONSTRAINT IF EXISTS uq_period_cost_head;
        ALTER TABLE monthly_expense_entries DROP CONSTRAINT IF EXISTS uq_module_period_cost_head;
        ALTER TABLE monthly_expense_entries ADD CONSTRAINT uq_module_period_cost_head UNIQUE (module, period_id, cost_head_id);
        CREATE INDEX IF NOT EXISTS idx_monthly_expense_entries_mod_period ON monthly_expense_entries (module, period_id);
        
        -- Segregated Entry Views per Module
        CREATE OR REPLACE VIEW food_expense_entries AS
        SELECT * FROM monthly_expense_entries WHERE module = 'food';

        CREATE OR REPLACE VIEW hostel_expense_entries AS
        SELECT * FROM monthly_expense_entries WHERE module = 'hostel';

        CREATE OR REPLACE VIEW transport_expense_entries AS
        SELECT * FROM monthly_expense_entries WHERE module = 'transport';
        """
    ),
    (
        "Dining Census Entries Table & Headcount / Production Columns",
        """
        CREATE TABLE IF NOT EXISTS dining_census_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            active_students INT NOT NULL DEFAULT 0,
            active_staff INT NOT NULL DEFAULT 0,
            others_count INT NOT NULL DEFAULT 0,
            total_persons INT NOT NULL DEFAULT 0,
            production_meals INT NOT NULL DEFAULT 0,
            booked_tokens INT NOT NULL DEFAULT 0,
            scanned_tokens INT NOT NULL DEFAULT 0,
            unscanned_meals INT NOT NULL DEFAULT 0,
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS others_count INT NOT NULL DEFAULT 0;
        ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS total_persons INT NOT NULL DEFAULT 0;
        ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS production_meals INT NOT NULL DEFAULT 0;
        """
    ),
    (
        "Users & Page Permissions Tables",
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'viewer',
            full_name VARCHAR(100) DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS role_page_permissions (
            id SERIAL PRIMARY KEY,
            role VARCHAR(50) NOT NULL,
            page_key VARCHAR(50) NOT NULL,
            can_view BOOLEAN NOT NULL DEFAULT true,
            can_edit BOOLEAN NOT NULL DEFAULT false,
            can_delete BOOLEAN NOT NULL DEFAULT false,
            CONSTRAINT uq_role_page UNIQUE (role, page_key)
        );
        """
    ),
    (
        "Hostel Census & Operational Metrics Table",
        """
        CREATE TABLE IF NOT EXISTS hostel_census_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            bed_capacity_boys INT NOT NULL DEFAULT 0,
            bed_capacity_girls INT NOT NULL DEFAULT 0,
            bed_capacity_total INT NOT NULL DEFAULT 0,
            students_boys INT NOT NULL DEFAULT 0,
            students_girls INT NOT NULL DEFAULT 0,
            students_total INT NOT NULL DEFAULT 0,
            staff_boys INT NOT NULL DEFAULT 0,
            staff_girls INT NOT NULL DEFAULT 0,
            staff_total INT NOT NULL DEFAULT 0,
            total_occupied INT NOT NULL DEFAULT 0,
            vacant_total INT NOT NULL DEFAULT 0,
            vacant_college INT NOT NULL DEFAULT 0,
            occupied_pct NUMERIC(6, 2) NOT NULL DEFAULT 0.00,
            vacant_pct NUMERIC(6, 2) NOT NULL DEFAULT 0.00,
            students_vacated INT NOT NULL DEFAULT 0,
            tickets_received INT NOT NULL DEFAULT 0,
            tickets_closed INT NOT NULL DEFAULT 0,
            tickets_open INT NOT NULL DEFAULT 0,
            total_hours_close NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            tat_hours NUMERIC(8, 2) NOT NULL DEFAULT 0.00,
            quality_issues_received INT NOT NULL DEFAULT 0,
            quality_issues_closed INT NOT NULL DEFAULT 0,
            quality_issues_open INT NOT NULL DEFAULT 0,
            incidents_count INT NOT NULL DEFAULT 0,
            power_units INT NOT NULL DEFAULT 0,
            power_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            water_purchase_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            normal_water_litres BIGINT NOT NULL DEFAULT 0,
            normal_water_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            drinking_water_litres BIGINT NOT NULL DEFAULT 0,
            drinking_water_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            sq_feet NUMERIC(12, 2) NOT NULL DEFAULT 231701.00,
            approved_budget NUMERIC(14, 2) NOT NULL DEFAULT 131788118.00,
            cumulative_budget_spent NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_college_boys INT NOT NULL DEFAULT 35;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_college_girls INT NOT NULL DEFAULT 69;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_sports_boys INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_sports_girls INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_sports_total INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_school_boys INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_school_girls INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_school_total INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS maintenance_expenses NUMERIC(14, 2) NOT NULL DEFAULT 119394.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS expenses_occurred NUMERIC(14, 2) NOT NULL DEFAULT 9349172.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS normal_water_student_ltrs NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS normal_water_student_cost NUMERIC(10, 2) NOT NULL DEFAULT 88.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS total_occupied_boys INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS total_occupied_girls INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_boys INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_girls INT NOT NULL DEFAULT 0;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS occupied_pct_boys NUMERIC(6, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS occupied_pct_girls NUMERIC(6, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_pct_boys NUMERIC(6, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS vacant_pct_girls NUMERIC(6, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS per_student_cost_month NUMERIC(12, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS per_student_cost_day NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS sq_feet_per_occupant NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS power_cost_sqft NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS units_per_occupant NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS power_cost_occupant NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS normal_water_ltr_day NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS normal_water_cost_day NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS drinking_water_ltr_day NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS drinking_water_cost_day NUMERIC(10, 2) NOT NULL DEFAULT 0.00;
        """
    ),
    (
        "Transport Census & Fleet Metrics Table",
        """
        CREATE TABLE IF NOT EXISTS transport_census_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            vehicles_count VARCHAR(20) NOT NULL DEFAULT '18+1',
            passengers_count INT NOT NULL DEFAULT 447,
            students_count INT NOT NULL DEFAULT 0,
            staff_count INT NOT NULL DEFAULT 0,
            approved_kms NUMERIC(10, 2) NOT NULL DEFAULT 26691.00,
            actual_kms NUMERIC(10, 2) NOT NULL DEFAULT 25777.00,
            additional_kms NUMERIC(10, 2) NOT NULL DEFAULT 2481.00,
            excess_kms_rps NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            fuel_expenses NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            diesel_litres NUMERIC(10, 2) NOT NULL DEFAULT 5184.84,
            fc_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            statutory_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            repair_maintenance_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            employee_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            other_cost NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            total_expenses NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            fee_demand NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            fee_collected NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            fee_unpaid NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            service_tickets_raised INT NOT NULL DEFAULT 38,
            service_tickets_closed INT NOT NULL DEFAULT 38,
            service_tickets_open INT NOT NULL DEFAULT 0,
            quality_issues_received INT NOT NULL DEFAULT 0,
            quality_issues_closed INT NOT NULL DEFAULT 0,
            quality_issues_open INT NOT NULL DEFAULT 0,
            statutory_compliance INT NOT NULL DEFAULT 1,
            incidents_count INT NOT NULL DEFAULT 1,
            approved_budget NUMERIC(14, 2) NOT NULL DEFAULT 13730137.73,
            cumulative_budget_spent NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS excess_km_billed_rps NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS rps_monthly_billing NUMERIC(12, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS staff_travel_deduction NUMERIC(12, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS additional_kms_billed_rps NUMERIC(12, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS additional_kms_others_billing NUMERIC(12, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS cumulative_income NUMERIC(14, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS balance NUMERIC(14, 2) DEFAULT 13730137.73;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS fee_discount NUMERIC(12, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS per_student_cost_expenses NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS per_student_fee_year NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS demand_per_km_day NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS km_per_veh_day NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS fuel_cost_per_km NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS diesel_per_100km NUMERIC(10, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS cab_billing NUMERIC(12, 2) DEFAULT 0.00;
        """
    ),
    (
        "Category Formulas Table",
        """
        CREATE TABLE IF NOT EXISTS category_formulas (
            id SERIAL PRIMARY KEY,
            module VARCHAR(50) NOT NULL DEFAULT 'food',
            name VARCHAR(255) NOT NULL,
            expression TEXT NOT NULL,
            description TEXT DEFAULT '',
            unit_type VARCHAR(20) DEFAULT 'currency',
            display_order INT DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cat_formulas_module ON category_formulas(module);
        """
    )
]

def run_migrations():
    print("=" * 60)
    print("Starting Database Schema Migration...")
    print("=" * 60)
    success_count = 0

    for name, sql in MIGRATION_STEPS:
        try:
            db.execute_commit(sql)
            print(f"  [OK] {name}")
            success_count += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            return False

    print("=" * 60)
    print(f"Migration completed successfully! ({success_count}/{len(MIGRATION_STEPS)} steps verified)")
    print("=" * 60)

    try:
        import seed_modules
        seed_modules.seed_segregated_data()
        print("  [OK] Segregated Module Data Verified (Food, Hostel, Transport)")
    except Exception as e:
        print(f"  [WARNING] Segregated Data Seeding skipped: {e}")

    return True

if __name__ == "__main__":
    ok = run_migrations()
    if not ok:
        sys.exit(1)
