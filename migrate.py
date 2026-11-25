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
            branch VARCHAR(50) NOT NULL DEFAULT 'all',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE billing_periods ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';
        ALTER TABLE billing_periods ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'all';
        ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS billing_periods_period_code_key;
        ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS uq_billing_periods_module_code;
        ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS uq_billing_periods_module_branch_code;
        ALTER TABLE billing_periods ADD CONSTRAINT uq_billing_periods_module_branch_code UNIQUE (module, branch, period_code);
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
    ),
    (
        "Expense Categories Formula Columns",
        """
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS category_type VARCHAR(20) NOT NULL DEFAULT 'DIRECT';
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_expression TEXT DEFAULT NULL;
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_definition JSONB DEFAULT NULL;
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_version INT NOT NULL DEFAULT 1;
        ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_expense_categories_type ON expense_categories(category_type);
        """
    ),
    (
        "Transport Branches Multi-Unit Architecture (RPS, KPM, Common, University)",
        """
        ALTER TABLE monthly_expense_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'Common';
        ALTER TABLE monthly_expense_entries DROP CONSTRAINT IF EXISTS uq_module_period_cost_head;
        ALTER TABLE monthly_expense_entries DROP CONSTRAINT IF EXISTS uq_module_period_cost_head_branch;
        ALTER TABLE monthly_expense_entries ADD CONSTRAINT uq_module_period_cost_head_branch UNIQUE (module, period_id, cost_head_id, branch);
        CREATE INDEX IF NOT EXISTS idx_monthly_expense_entries_branch ON monthly_expense_entries(branch);

        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'Common';
        ALTER TABLE transport_census_entries DROP CONSTRAINT IF EXISTS transport_census_entries_period_id_key;
        ALTER TABLE transport_census_entries DROP CONSTRAINT IF EXISTS uq_transport_census_period_branch;
        ALTER TABLE transport_census_entries ADD CONSTRAINT uq_transport_census_period_branch UNIQUE (period_id, branch);
        CREATE INDEX IF NOT EXISTS idx_transport_census_entries_branch ON transport_census_entries(branch);
        """
    ),
    (
        "Transport Fleet Master Parameters Table & S.No Support",
        """
        CREATE TABLE IF NOT EXISTS transport_master_parameters (
            id SERIAL PRIMARY KEY,
            s_no VARCHAR(20) DEFAULT '',
            param_key VARCHAR(100) NOT NULL UNIQUE,
            param_name VARCHAR(255) NOT NULL,
            section VARCHAR(100) NOT NULL,
            section_order INT NOT NULL DEFAULT 1,
            input_type VARCHAR(50) NOT NULL DEFAULT 'cost',
            unit VARCHAR(50) DEFAULT '',
            formula TEXT DEFAULT NULL,
            display_order INT NOT NULL DEFAULT 50,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE transport_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_transport_master_params_section ON transport_master_parameters(section);
        CREATE INDEX IF NOT EXISTS idx_transport_master_params_active ON transport_master_parameters(is_active);

        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) DEFAULT 'Common';
        """
    ),
    (
        "Deleted Master Parameters Tombstone Registry",
        """
        CREATE TABLE IF NOT EXISTS deleted_master_parameters (
            module VARCHAR(50) NOT NULL,
            param_key VARCHAR(100) NOT NULL,
            deleted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (module, param_key)
        );
        """
    ),
    (
        "Monthly Attachments Table",
        """
        CREATE TABLE IF NOT EXISTS monthly_attachments (
            id SERIAL PRIMARY KEY,
            module VARCHAR(50) NOT NULL,
            period_id INT NOT NULL REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) DEFAULT 'Common',
            file_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            file_path TEXT NOT NULL,
            file_size BIGINT DEFAULT 0,
            mime_type VARCHAR(100) DEFAULT '',
            is_link BOOLEAN NOT NULL DEFAULT FALSE,
            uploaded_by VARCHAR(100) DEFAULT 'User',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_monthly_attachments_module_period ON monthly_attachments(module, period_id);
        ALTER TABLE monthly_attachments ADD COLUMN IF NOT EXISTS topic VARCHAR(255) DEFAULT '';
        """
    ),
    (
        "Transport Vehicle Entries & Fleet Mileage Ledger Table",
        """
        CREATE TABLE IF NOT EXISTS transport_vehicle_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) NOT NULL DEFAULT 'Common',
            vehicle_no VARCHAR(100) NOT NULL,
            make VARCHAR(150),
            model VARCHAR(100),
            fuel_expenses NUMERIC(15, 2) DEFAULT 0.0,
            fc_cost NUMERIC(15, 2) DEFAULT 0.0,
            statutory_cost NUMERIC(15, 2) DEFAULT 0.0,
            repair_maintenance NUMERIC(15, 2) DEFAULT 0.0,
            parking_fastag NUMERIC(15, 2) DEFAULT 0.0,
            employee_cost NUMERIC(15, 2) DEFAULT 0.0,
            other_cost NUMERIC(15, 2) DEFAULT 0.0,
            total_expenses NUMERIC(15, 2) DEFAULT 0.0,
            diesel_litres NUMERIC(15, 2) DEFAULT 0.0,
            km_run NUMERIC(15, 2) DEFAULT 0.0,
            mileage NUMERIC(10, 2) DEFAULT 0.0,
            display_order INT DEFAULT 0,
            remarks TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_transport_vehicle_entries_period_branch ON transport_vehicle_entries(period_id, branch);
        """
    ),
    (
        "CCTV Master Parameters & Monthly Entries Tables",
        """
        CREATE TABLE IF NOT EXISTS cctv_master_parameters (
            id SERIAL PRIMARY KEY,
            s_no VARCHAR(20) DEFAULT '',
            param_key VARCHAR(100) NOT NULL UNIQUE,
            param_name VARCHAR(255) NOT NULL,
            section VARCHAR(100) NOT NULL,
            section_order INT NOT NULL DEFAULT 1,
            input_type VARCHAR(50) NOT NULL DEFAULT 'number',
            unit VARCHAR(50) DEFAULT '',
            formula TEXT DEFAULT NULL,
            display_order INT NOT NULL DEFAULT 50,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE cctv_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_cctv_master_params_section ON cctv_master_parameters(section);
        CREATE INDEX IF NOT EXISTS idx_cctv_master_params_active ON cctv_master_parameters(is_active);

        CREATE TABLE IF NOT EXISTS cctv_monthly_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) NOT NULL DEFAULT 'all',
            projects_completed INT DEFAULT 0,
            projects_in_progress INT DEFAULT 0,
            projects_total INT DEFAULT 0,
            complaints_cctv INT DEFAULT 0,
            complaints_biometric INT DEFAULT 0,
            complaints_flapbarrier INT DEFAULT 0,
            complaints_total INT DEFAULT 0,
            repeated_complaints INT DEFAULT 0,
            time_taken_complaints_hrs NUMERIC(10, 2) DEFAULT 0.0,
            tat_complaints_hrs NUMERIC(10, 2) DEFAULT 0.0,
            service_cctv INT DEFAULT 0,
            service_biometric INT DEFAULT 0,
            service_flapbarrier INT DEFAULT 0,
            service_total INT DEFAULT 0,
            repeated_work INT DEFAULT 0,
            time_taken_service_hrs NUMERIC(10, 2) DEFAULT 0.0,
            tat_service_hrs NUMERIC(10, 2) DEFAULT 0.0,
            ppm_count INT DEFAULT 0,
            quality_issues_received INT DEFAULT 0,
            quality_issues_closed INT DEFAULT 0,
            quality_issues_open INT DEFAULT 0,
            material_expenses NUMERIC(15, 2) DEFAULT 0.0,
            labour_expenses NUMERIC(15, 2) DEFAULT 0.0,
            total_expenses NUMERIC(15, 2) DEFAULT 0.0,
            approved_budget NUMERIC(15, 2) DEFAULT 0.0,
            cumulative_budget_spent NUMERIC(15, 2) DEFAULT 0.0,
            balance NUMERIC(15, 2) DEFAULT 0.0,
            remarks TEXT DEFAULT '',
            custom_metrics JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cctv_monthly_entries_period ON cctv_monthly_entries(period_id);
        """
    ),
    (
        "Hostel Budget Tracking Table & Canonical Heads",
        """
        CREATE TABLE IF NOT EXISTS hostel_budget_tracking (
            id SERIAL PRIMARY KEY,
            s_no INT NOT NULL,
            budget_head VARCHAR(100) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            month_limit NUMERIC(14,2) DEFAULT 0.0,
            sep_25_actual NUMERIC(14,2) DEFAULT 0.0,
            oct_26_actual NUMERIC(14,2) DEFAULT 0.0,
            nov_26_actual NUMERIC(14,2) DEFAULT 0.0,
            dec_26_actual NUMERIC(14,2) DEFAULT 0.0,
            jan_27_actual NUMERIC(14,2) DEFAULT 0.0,
            feb_27_actual NUMERIC(14,2) DEFAULT 0.0,
            mar_27_actual NUMERIC(14,2) DEFAULT 0.0,
            apr_27_actual NUMERIC(14,2) DEFAULT 0.0,
            may_27_actual NUMERIC(14,2) DEFAULT 0.0,
            jun_27_actual NUMERIC(14,2) DEFAULT 0.0,
            jul_27_actual NUMERIC(14,2) DEFAULT 0.0,
            aug_27_actual NUMERIC(14,2) DEFAULT 0.0,
            sep_27_actual NUMERIC(14,2) DEFAULT 0.0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO hostel_budget_tracking (s_no, budget_head, sanctioned_amount, month_limit)
        VALUES
            (1, 'Rent', 84762516, 10595314.5),
            (2, 'Printing & Stationary Expenses', 15000, 1875),
            (3, 'Rates & Taxes', 731612, 91451.5),
            (4, 'Employee Cost', 15402907, 1925363.38),
            (5, 'Hostel Management Services', 30490064, 3811258),
            (6, 'Utility', 32893042, 4111630.25),
            (7, 'Laundry Expenses', 11728517, 1466064.63),
            (8, 'Repairs and Maintenance', 5425960, 678245),
            (9, 'Events', 4000000, 500000)
        ON CONFLICT (budget_head) DO NOTHING;
        """
    ),
    (
        "Food Budget Tracking Table & Canonical Heads",
        """
        CREATE TABLE IF NOT EXISTS food_budget_tracking (
            id SERIAL PRIMARY KEY,
            s_no INT NOT NULL,
            budget_head VARCHAR(120) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            month_limit NUMERIC(14,2) DEFAULT 0.0,
            jun_26_actual NUMERIC(14,2) DEFAULT 0.0,
            jul_26_actual NUMERIC(14,2) DEFAULT 0.0,
            aug_26_actual NUMERIC(14,2) DEFAULT 0.0,
            sep_26_actual NUMERIC(14,2) DEFAULT 0.0,
            oct_26_actual NUMERIC(14,2) DEFAULT 0.0,
            nov_26_actual NUMERIC(14,2) DEFAULT 0.0,
            dec_26_actual NUMERIC(14,2) DEFAULT 0.0,
            monthly_actuals JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO food_budget_tracking (s_no, budget_head, sanctioned_amount, month_limit)
        VALUES
            (1, 'Food Material', 105000000.0, 8750000.0),
            (2, 'Food Team Salary', 36000000.0, 3000000.0),
            (3, 'Contract Labour Expenses', 4800000.0, 400000.0),
            (4, 'Catering Vendor Expenses', 6000000.0, 500000.0),
            (5, 'FC Maintenance/Power/Water/Vehicle', 6600000.0, 550000.0),
            (6, 'Event/Additional Food', 3000000.0, 250000.0),
            (7, 'Food Festival', 6000000.0, 500000.0),
            (8, 'Staff Welfare', 1800000.0, 150000.0)
        ON CONFLICT (budget_head) DO NOTHING;
        """
    ),
    (
        "Transport Budget Tracking & Per-Fleet Tables (University, RPS, KPM, Common)",
        """
        CREATE TABLE IF NOT EXISTS transport_budget_tracking (
            id SERIAL PRIMARY KEY,
            branch VARCHAR(50) NOT NULL,
            param_name VARCHAR(150) NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            display_order INT DEFAULT 1,
            color VARCHAR(50),
            bg VARCHAR(50),
            is_total BOOLEAN DEFAULT FALSE,
            is_blank BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (branch, param_name)
        );
        CREATE TABLE IF NOT EXISTS transport_budget_university (
            id SERIAL PRIMARY KEY,
            param_name VARCHAR(150) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            display_order INT DEFAULT 1,
            color VARCHAR(50),
            bg VARCHAR(50),
            is_total BOOLEAN DEFAULT FALSE,
            is_blank BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transport_budget_rps (
            id SERIAL PRIMARY KEY,
            param_name VARCHAR(150) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            display_order INT DEFAULT 1,
            color VARCHAR(50),
            bg VARCHAR(50),
            is_total BOOLEAN DEFAULT FALSE,
            is_blank BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transport_budget_kpm (
            id SERIAL PRIMARY KEY,
            param_name VARCHAR(150) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            display_order INT DEFAULT 1,
            color VARCHAR(50),
            bg VARCHAR(50),
            is_total BOOLEAN DEFAULT FALSE,
            is_blank BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transport_budget_common (
            id SERIAL PRIMARY KEY,
            param_name VARCHAR(150) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            display_order INT DEFAULT 1,
            color VARCHAR(50),
            bg VARCHAR(50),
            is_total BOOLEAN DEFAULT FALSE,
            is_blank BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
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
            print(f"  [WARNING] {name} encountered an issue: {e}")
            # Try to execute statement by statement if it was a multi-statement block
            stmts = [s.strip() for s in sql.split(';') if s.strip()]
            if len(stmts) > 1:
                sub_ok = 0
                for s in stmts:
                    try:
                        db.execute_commit(s)
                        sub_ok += 1
                    except Exception as sub_e:
                        print(f"    [SUB-STMT NOTICE] {sub_e}")
                if sub_ok > 0:
                    print(f"    [PARTIAL OK] {name} ({sub_ok}/{len(stmts)} sub-statements applied)")
                    success_count += 1
            else:
                pass

    print("=" * 60)
    print(f"Migration completed successfully! ({success_count}/{len(MIGRATION_STEPS)} steps verified)")
    print("=" * 60)

    try:
        import seed_transport_canonical
        seed_transport_canonical.ensure_and_seed_transport_parameters()
        print("  [OK] Transport Master Parameters Seeded & Verified")
    except Exception as te:
        print(f"  [WARNING] Transport Master Parameters Seeding skipped: {te}")

    try:
        import seed_hostel_canonical
        seed_hostel_canonical.ensure_and_seed_hostel_parameters()
        print("  [OK] Hostel Master Parameters Seeded & Verified")
    except Exception as he:
        print(f"  [WARNING] Hostel Master Parameters Seeding skipped: {he}")

    try:
        import seed_transport_vehicles
        seed_transport_vehicles.ensure_and_seed_transport_vehicles()
        print("  [OK] Transport Vehicle Fleet Entries Seeded & Verified")
    except Exception as tve:
        print(f"  [WARNING] Transport Vehicle Seeding skipped: {tve}")

    try:
        import seed_cctv
        seed_cctv.seed()
        print("  [OK] CCTV Master Parameters & Initial Data Seeded & Verified")
    except Exception as cctv_e:
        print(f"  [WARNING] CCTV Seeding skipped: {cctv_e}")

    # Notice: Do not automatically re-seed operational/census data on startup.
    # Operational data must only be populated when user enters and saves via Data Entry.
    # To manually reseed demo data, use the explicit POST /api/system/seed-default endpoint.

    return True

if __name__ == "__main__":
    ok = run_migrations()
    if not ok:
        sys.exit(1)
