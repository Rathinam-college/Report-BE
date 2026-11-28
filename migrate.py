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
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS cctv_replacement NUMERIC(14, 2) DEFAULT 0.00;
        ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS parking_fastag NUMERIC(14, 2) DEFAULT 0.00;
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
        ALTER TABLE transport_vehicle_entries ADD COLUMN IF NOT EXISTS cctv_replacement NUMERIC(15, 2) DEFAULT 0.0;
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
        ALTER TABLE cctv_monthly_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'all';
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
        INSERT INTO food_budget_tracking (
            s_no, budget_head, sanctioned_amount, month_limit,
            jun_26_actual, jul_26_actual, aug_26_actual, sep_26_actual, oct_26_actual
        )
        VALUES
            (1, 'Food Material', 126608030.0, 0.0, 6686557.0, 8319829.0, 7667497.0, 10934147.0, 10123675.0),
            (2, 'Food Team Salary', 23020132.0, 0.0, 1694705.0, 1628691.0, 1862412.0, 1834324.0, 1988139.0),
            (3, 'Contract Labour Expenses', 11292833.0, 0.0, 699188.0, 828184.0, 805171.0, 960290.0, 1020122.0),
            (4, 'Catering Vendor Expenses', 5486000.0, 0.0, 260700.0, 410500.0, 299600.0, 515200.0, 498600.0),
            (5, 'FC Maintenance/Power/Water/Vehicle', 6170173.0, 0.0, 426223.0, 321543.0, 532933.0, 495861.0, 459483.0),
            (6, 'Event/Additional Food', 2263630.0, 0.0, 254495.0, 217870.0, 114490.0, 76775.0, 210525.0),
            (7, 'Food Festival', 2531639.0, 0.0, 0.0, 0.0, 551639.0, 0.0, 0.0),
            (8, 'Staff Welfare', 325000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ON CONFLICT (budget_head) DO UPDATE SET
            s_no = EXCLUDED.s_no,
            sanctioned_amount = EXCLUDED.sanctioned_amount,
            month_limit = EXCLUDED.month_limit,
            jun_26_actual = EXCLUDED.jun_26_actual,
            jul_26_actual = EXCLUDED.jul_26_actual,
            aug_26_actual = EXCLUDED.aug_26_actual,
            sep_26_actual = EXCLUDED.sep_26_actual,
            oct_26_actual = EXCLUDED.oct_26_actual,
            updated_at = CURRENT_TIMESTAMP;
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
    ),
    (
        "Food Power & Water Entries Table",
        """
        CREATE TABLE IF NOT EXISTS food_power_water_entries (
            id SERIAL PRIMARY KEY,
            period_id INT UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            power_units NUMERIC(14,2) DEFAULT 0.0,
            power_cost NUMERIC(14,2) DEFAULT 0.0,
            students_staff_count NUMERIC(14,2) DEFAULT 0.0,
            normal_water_litres NUMERIC(14,2) DEFAULT 0.0,
            normal_water_cost NUMERIC(14,2) DEFAULT 0.0,
            students_count NUMERIC(14,2) DEFAULT 0.0,
            drinking_water_litres NUMERIC(14,2) DEFAULT 0.0,
            drinking_water_cost NUMERIC(14,2) DEFAULT 0.0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    ),
    (
        "Audit 4-Topic Tables (Non-Academic Report, Schedule, NC Tracker, Internal Report)",
        """
        CREATE TABLE IF NOT EXISTS audit_non_academic_reports (
            id SERIAL PRIMARY KEY,
            period_id INT REFERENCES billing_periods(id) ON DELETE CASCADE,
            s_no INT DEFAULT 1,
            department VARCHAR(200) NOT NULL,
            auditees TEXT DEFAULT '',
            admin_score VARCHAR(30) DEFAULT '',
            maintenance_support VARCHAR(30) DEFAULT '',
            equipment_maintenance VARCHAR(30) DEFAULT '',
            cafeteria VARCHAR(30) DEFAULT '',
            site_infra VARCHAR(30) DEFAULT '',
            transport VARCHAR(30) DEFAULT '',
            security VARCHAR(30) DEFAULT '',
            restroom VARCHAR(30) DEFAULT '',
            sick_bay VARCHAR(30) DEFAULT '',
            library VARCHAR(30) DEFAULT '',
            total_score NUMERIC(10,2) DEFAULT 0.0,
            score_pct NUMERIC(6,2) DEFAULT 0.0,
            remarks TEXT DEFAULT '',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE audit_non_academic_reports ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT '';
        CREATE TABLE IF NOT EXISTS audit_non_academic_schedules (
            id SERIAL PRIMARY KEY,
            period_id INT REFERENCES billing_periods(id) ON DELETE CASCADE,
            s_no INT DEFAULT 1,
            department VARCHAR(200) NOT NULL,
            auditees TEXT DEFAULT '',
            planned_date VARCHAR(120) DEFAULT '',
            time_slot VARCHAR(120) DEFAULT '',
            auditors TEXT DEFAULT '',
            status VARCHAR(150) DEFAULT '',
            remarks TEXT DEFAULT '',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_nc_tracker (
            id SERIAL PRIMARY KEY,
            period_id INT REFERENCES billing_periods(id) ON DELETE CASCADE,
            s_no INT DEFAULT 1,
            nc_no VARCHAR(80) DEFAULT '',
            department VARCHAR(200) NOT NULL,
            area VARCHAR(200) DEFAULT '',
            nc_description TEXT DEFAULT '',
            severity VARCHAR(50) DEFAULT 'Minor',
            root_cause TEXT DEFAULT '',
            corrective_action TEXT DEFAULT '',
            responsible_person VARCHAR(150) DEFAULT '',
            target_date VARCHAR(80) DEFAULT '',
            closed_date VARCHAR(80) DEFAULT '',
            status VARCHAR(80) DEFAULT 'Open',
            remarks TEXT DEFAULT '',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_internal_reports (
            id SERIAL PRIMARY KEY,
            period_id INT REFERENCES billing_periods(id) ON DELETE CASCADE,
            cycle_no VARCHAR(50) DEFAULT '',
            criteria VARCHAR(200) DEFAULT 'QMS - 9001:2015',
            s_no INT DEFAULT 1,
            department VARCHAR(200) NOT NULL,
            status VARCHAR(100) DEFAULT '',
            total_scores NUMERIC(10,2) DEFAULT 0.0,
            remarks TEXT DEFAULT '',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_master_departments (
            id SERIAL PRIMARY KEY,
            topic VARCHAR(60) NOT NULL DEFAULT 'internal_report',
            s_no INT NOT NULL DEFAULT 1,
            department VARCHAR(200) NOT NULL,
            default_auditees TEXT DEFAULT '',
            default_criteria VARCHAR(200) DEFAULT 'QMS - 9001:2015',
            default_cycle_no VARCHAR(50) DEFAULT '12',
            display_order INT NOT NULL DEFAULT 1,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (topic, department)
        );
        """
    ),
    (
        "Transport Per-Fleet Separate Tables (KPM, RPS, University, Common)",
        "\n".join([
            f"""
            CREATE TABLE IF NOT EXISTS transport_census_{fk} (LIKE transport_census_entries INCLUDING DEFAULTS);
            ALTER TABLE transport_census_{fk} ADD COLUMN IF NOT EXISTS cctv_replacement NUMERIC(14, 2) DEFAULT 0.00;
            ALTER TABLE transport_census_{fk} ADD COLUMN IF NOT EXISTS parking_fastag NUMERIC(14, 2) DEFAULT 0.00;
            ALTER TABLE transport_census_{fk} DROP CONSTRAINT IF EXISTS uq_transport_census_{fk}_period;
            ALTER TABLE transport_census_{fk} ADD CONSTRAINT uq_transport_census_{fk}_period UNIQUE (period_id);
            INSERT INTO transport_census_{fk}
            SELECT * FROM transport_census_entries WHERE LOWER(branch) = '{fk}'
            ON CONFLICT (period_id) DO NOTHING;

            CREATE TABLE IF NOT EXISTS transport_vehicles_{fk} (LIKE transport_vehicle_entries INCLUDING DEFAULTS);
            ALTER TABLE transport_vehicles_{fk} ADD COLUMN IF NOT EXISTS cctv_replacement NUMERIC(15, 2) DEFAULT 0.0;
            INSERT INTO transport_vehicles_{fk}
            SELECT * FROM transport_vehicle_entries
            WHERE LOWER(branch) = '{fk}'
              AND NOT EXISTS (SELECT 1 FROM transport_vehicles_{fk} LIMIT 1);

            CREATE TABLE IF NOT EXISTS transport_expenses_{fk} (
                id BIGINT PRIMARY KEY,
                period_id INT,
                cost_head_id INT,
                vendor_id INT,
                amount NUMERIC(15, 2) DEFAULT 0.0,
                status VARCHAR(50),
                remarks TEXT,
                recorded_by VARCHAR(100),
                audited_at TIMESTAMP,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                module VARCHAR(50),
                branch VARCHAR(50)
            );
            INSERT INTO transport_expenses_{fk}
            SELECT id, period_id, cost_head_id, vendor_id, amount, status::text, remarks, recorded_by, audited_at, created_at, updated_at, module, branch
            FROM transport_expense_entries WHERE LOWER(branch) = '{fk}'
            ON CONFLICT (id) DO NOTHING;
            """
            for fk in ("kpm", "rps", "university", "common")
        ])
    ),
    (
        "Hostel Daily Institute Occupancy & Bed Summary Tables",
        """
        CREATE TABLE IF NOT EXISTS hostel_daily_institute_occupancy (
            id SERIAL PRIMARY KEY,
            s_no INT NOT NULL DEFAULT 1,
            institute VARCHAR(100) UNIQUE NOT NULL,
            boys INT NOT NULL DEFAULT 0,
            girls INT NOT NULL DEFAULT 0,
            updated_date DATE NOT NULL DEFAULT CURRENT_DATE,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO hostel_daily_institute_occupancy (s_no, institute, boys, girls)
        SELECT v.s_no, v.institute, v.boys, v.girls
        FROM (VALUES
            (1, 'RTC', 1400, 596),
            (2, 'RGU', 1204, 405),
            (3, 'RCP', 27, 34),
            (4, 'RPhar', 47, 33),
            (5, 'Law', 17, 6),
            (6, 'RPS', 1, 0),
            (7, 'KPM', 34, 0)
        ) AS v(s_no, institute, boys, girls)
        WHERE NOT EXISTS (SELECT 1 FROM hostel_daily_institute_occupancy LIMIT 1);

        CREATE TABLE IF NOT EXISTS hostel_daily_bed_summary (
            id SERIAL PRIMARY KEY,
            s_no INT NOT NULL DEFAULT 1,
            metric_key VARCHAR(100) UNIQUE NOT NULL,
            metric_label VARCHAR(150) NOT NULL,
            boys INT NOT NULL DEFAULT 0,
            girls INT NOT NULL DEFAULT 0,
            updated_date DATE NOT NULL DEFAULT CURRENT_DATE,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO hostel_daily_bed_summary (s_no, metric_key, metric_label, boys, girls)
        SELECT v.s_no, v.metric_key, v.metric_label, v.boys, v.girls
        FROM (VALUES
            (1, 'college_bc', 'College BC', 2895, 1304),
            (2, 'college_students_occ', 'College Students Occ', 2623, 1074),
            (3, 'staff_occ', 'Staff Occ', 82, 73),
            (4, 'college_sports_bc', 'College Sports Students BC', 96, 0),
            (5, 'college_sports_occ', 'College Sports Students Occ', 72, 0),
            (6, 'kpm_hostel_staff_occ', 'KPM Hostel Staff Occ', 20, 0),
            (7, 'school_students_bc', 'School Students BC', 46, 0),
            (8, 'school_students_occ', 'School Students Occ', 34, 0)
        ) AS v(s_no, metric_key, metric_label, boys, girls)
        WHERE NOT EXISTS (SELECT 1 FROM hostel_daily_bed_summary LIMIT 1);
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

    try:
        sync_all_transport_fleet_tables()
    except Exception as sf_e:
        print(f"  [WARNING] Transport Per-Fleet Sync skipped: {sf_e}")

    try:
        seed_audit_master_and_initial_data()
    except Exception as au_e:
        print(f"  [WARNING] Audit Master Seeding skipped: {au_e}")

    return True


def seed_audit_master_and_initial_data():
    """Seeds audit_master_departments and initial Oct-26 Internal Audit rows if empty."""
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            internal_depts = [
                (1, "Hostel - 1 (Sabari Hospitality)", "", "QMS - 9001:2015", "12"),
                (2, "Hostel - 2 (Clean 4 U)", "", "QMS - 9001:2015", "12"),
                (3, "Food", "", "QMS - 9001:2015", "12"),
                (4, "Transport", "", "QMS - 9001:2015", "12"),
            ]
            for s_no, dept, auditees, criteria, cyc in internal_depts:
                cur.execute(
                    """
                    INSERT INTO audit_master_departments (topic, s_no, department, default_auditees, default_criteria, default_cycle_no, display_order)
                    VALUES ('internal_report', %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (topic, department) DO NOTHING;
                    """,
                    (s_no, dept, auditees, criteria, cyc, s_no),
                )

            na_depts = [
                (1, "KPM", "Mrs.Akhilaa Vellalar / Mrs.Kanimozhi"),
                (2, "RPS", "Mrs.Sankari KN / Mr. William Ebenezar"),
                (3, "RCAS (Chanakya & CV raman block)", "Mr.Dhinakaran / Mr.Balasubramanian"),
                (4, "RTC (A,B&C block)", "Mrs.K Geetha /Mr.Jayabal"),
                (5, "PHARMACY", "Dr.Syed Shajahan /Mr.Adarvana Sampath / Mr.Balakrishnan N"),
                (6, "PHYSIOTHERAPHY", "Dr.Syed Shajahan / Mr.Syed Abudaheer / Mrs.Umadevi"),
                (7, "TIPS", "Mr.Syed Shajahan / Mr.Chandrasekar"),
                (8, "ZIA", "Mrs.Abinaya / Mrs.Sharon"),
                (9, "HR", "Mr.Vanji Muthu Kumar K"),
                (10, "Stores", "Mrs.Nageshwari/ Mr. William Ebenezar/ Mrs. Abinaya"),
                (11, "IT&CCTV", "Mr. Sunil / Mr. Senthil Kumar / Mr. Ramakrishnan Babu/ Mr. Manimaran"),
            ]
            for topic in ("non_academic_report", "non_academic_schedule"):
                for s_no, dept, auditees in na_depts:
                    cur.execute(
                        """
                        INSERT INTO audit_master_departments (topic, s_no, department, default_auditees, default_criteria, default_cycle_no, display_order)
                        VALUES (%s, %s, %s, %s, 'Non-Academic Audit', '', %s)
                        ON CONFLICT (topic, department) DO NOTHING;
                        """,
                        (topic, s_no, dept, auditees, s_no),
                    )

            # Ensure Audit module has its own billing_periods (Jun'26 - Oct'26)
            audit_months = [
                ("2026-06", "Jun'26", "2026-06-01", "2026-06-30", 30),
                ("2026-07", "Jul'26", "2026-07-01", "2026-07-31", 31),
                ("2026-08", "Aug'26", "2026-08-01", "2026-08-31", 31),
                ("2026-09", "Sept'26", "2026-09-01", "2026-09-30", 30),
                ("2026-10", "Oct'26", "2026-10-01", "2026-10-31", 31),
            ]
            cur.execute("SELECT id FROM fiscal_years ORDER BY id DESC LIMIT 1;")
            fy_row = cur.fetchone()
            fy_id = fy_row[0] if fy_row else 1
            for p_code, p_lbl, s_dt, e_dt, op_days in audit_months:
                cur.execute(
                    "SELECT id FROM billing_periods WHERE module = 'audit' AND period_code = %s LIMIT 1;",
                    (p_code,),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, is_closed, module, branch)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE, 'audit', 'all');
                        """,
                        (fy_id, p_code, p_lbl, s_dt, e_dt, op_days),
                    )

            # Seed Oct-26 Internal Audit Consolidated Report rows on Audit's 2026-10 period if empty or still on food period
            cur.execute(
                "SELECT id FROM billing_periods WHERE module = 'audit' AND period_code = '2026-10' ORDER BY id LIMIT 1;"
            )
            p_row = cur.fetchone()
            if p_row:
                oct_pid = p_row[0]
                cur.execute("SELECT COUNT(*) FROM audit_internal_reports WHERE period_id = %s;", (oct_pid,))
                if cur.fetchone()[0] == 0:
                    cur.execute("DELETE FROM audit_internal_reports WHERE period_id = 311 AND cycle_no = '12';")
                    seed_int = [
                        (1, "Hostel - 1 (Sabari Hospitality)", "Completed", 90),
                        (2, "Hostel - 2 (Clean 4 U)", "Completed", 88),
                        (3, "Food", "", 0),
                        (4, "Transport", "", 0),
                    ]
                    for s_no, dept, status, score in seed_int:
                        cur.execute(
                            """
                            INSERT INTO audit_internal_reports (period_id, cycle_no, criteria, s_no, department, status, total_scores, remarks)
                            VALUES (%s, '12', 'QMS - 9001:2015', %s, %s, %s, %s, '');
                            """,
                            (oct_pid, s_no, dept, status, score),
                        )

                # Seed Oct-26 Non-Academic Audit Consolidated Report rows if empty for oct_pid
                cur.execute("SELECT COUNT(*) FROM audit_non_academic_reports WHERE period_id = %s;", (oct_pid,))
                if cur.fetchone()[0] == 0:
                    seed_na_rep = [
                        (1, "KPM", "Mrs.Akhilaa Vellalar / Mrs.Kanimozhi", "98", "100", "100", "N/A", "100", "96", "97", "100", "N/A", "100", 791, 99),
                        (2, "RPS", "Mrs.Sankari KN / Mr. William Ebenezar", "98", "97", "100", "70", "100", "95", "97", "98", "100", "100", 956, 96),
                        (3, "RCAS (Chanakya & CV raman block)", "Mr.Dhinakaran / Mr.Balasubramanian", "98", "99", "97", "100", "100", "96", "97", "100", "N/A", "100", 887, 99),
                        (4, "RTC (A,B&C block)", "Mrs.K Geetha /Mr.Jayabal", "100", "100", "100", "100", "100", "96", "100", "100", "N/A", "100", 896, 100),
                        (5, "PHARMACY", "Mr.Syed Shajahan /Mr.Adarvana Sampath / Mr.Balakrishnan N", "97", "100", "N/A", "N/A", "100", "98", "N/A", "100", "N/A", "100", 595, 99),
                        (6, "PHYSIOTHERAPHY", "Mr.Syed Shajahan / Mr.Syed Abudaheer / Mrs.Umadevi", "97", "100", "100", "N/A", "N/A", "98", "100", "100", "100", "100", 795, 99),
                        (7, "TIPS", "Mr.Syed Shajahan / Mr.Chandrasekar", "N/A", "N/A", "N/A", "N/A", "N/A", "69", "N/A", "N/A", "N/A", "N/A", 69, 69),
                        (8, "ZIA", "Mrs.Abinaya / Mrs.Sharon", "87", "97", "93", "N/A", "100", "90", "89", "100", "100", "N/A", 756, 95),
                        (9, "HR", "Mr.Vanji Muthu Kumar K", "", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", 0, 0),
                        (10, "Stores", "Mrs.Nageshwari/ Mr. William Ebenezar/ Mrs. Abinaya", "90", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", 90, 90),
                        (11, "IT&CCTV", "Mr. Sunil / Mr. Senthil Kumar / Mr. Ramakrishnan Babu/ Mr. Manimaran", "89", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", 89, 89),
                    ]
                    for (s_no, dept, aud, adm, mnt, eqp, caf, sinf, trp, sec, rst, sb, lib, tot, pct) in seed_na_rep:
                        cur.execute(
                            """
                            INSERT INTO audit_non_academic_reports (
                                period_id, s_no, department, auditees,
                                admin_score, maintenance_support, equipment_maintenance, cafeteria,
                                site_infra, transport, security, restroom, sick_bay, library,
                                total_score, score_pct
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (oct_pid, s_no, dept, aud, adm, mnt, eqp, caf, sinf, trp, sec, rst, sb, lib, tot, pct),
                        )

                # Seed Oct-26 Non-Academic Audit Schedule rows if empty for oct_pid
                cur.execute("SELECT COUNT(*) FROM audit_non_academic_schedules WHERE period_id = %s;", (oct_pid,))
                if cur.fetchone()[0] == 0:
                    seed_na_sch = [
                        (1, "KPM", "Mrs.Akhilaa Vellalar / Mrs.Kanimozhi", "06.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "07.10.2026 / completed", ""),
                        (2, "RPS", "Mrs.Sankari KN / Mr. William Ebenezar", "07.10.2026 & 08.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "09.10.2026 / completed", ""),
                        (3, "RGU (Chanakya & CV raman block)", "Dr Krishnaraj C /Dr.Dhinakaran / Mr. Subhash", "09.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "28.10.2026/ completed", ""),
                        (4, "RTC (A,B&C block)", "Dr.K Geetha /Mr.Jayabal", "10.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "15.10.2026 / completed", ""),
                        (5, "PHARMACY", "Dr.Syed Shajahan /Mr.Adarvana Sampath / Mr.Balakrishnan N", "12.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "12.10.2026 / completed", ""),
                        (6, "PHYSIOTHERAPHY", "Dr.Syed Shajahan / Mr.Syed Abudaheer / Mrs.Umadevi", "13.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "14.10.2026 / completed", ""),
                        (7, "HR", "Mr.Vanji Muthu Kumar K / Mr. yogeshwaran", "14.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "In-progress", ""),
                        (8, "Stores", "Mr.Kannappan", "15.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "24.10.2026 / completed", ""),
                        (9, "IT & CCTV", "Mr. Sunil / Mr. Senthil Kumar / Mr. Ramakrishnan Babu/ Mr. Manimaran", "16.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "22.10.2026 / completed", ""),
                        (10, "TIPS", "Mr.Chandrasekar / Amul K", "17.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "17.10.2026 / completed", ""),
                        (11, "ZIA", "Mrs. Andrea Gabrielia Lazarus / Mrs.Abinaya", "21.10.2026", "10 am - 5pm", "Sriram/ Kiruthika", "30.10.2026/ completed", ""),
                    ]
                    for s_no, dept, aud, p_dt, tm, audr, st, rem in seed_na_sch:
                        cur.execute(
                            """
                            INSERT INTO audit_non_academic_schedules (
                                period_id, s_no, department, auditees, planned_date, time_slot, auditors, status, remarks
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (oct_pid, s_no, dept, aud, p_dt, tm, audr, st, rem),
                        )

                # Seed Oct-26 NA - Non-Conformity Consolidated Tracker 2026 if empty for oct_pid
                cur.execute("SELECT COUNT(*) FROM audit_nc_tracker WHERE period_id = %s;", (oct_pid,))
                if cur.fetchone()[0] == 0:
                    seed_nc = [
                        (1, "KPM", "09.10.2026", "Housekeeping staff accommodation near the KPM classroom, including the restrooms, surrounding area, and washing area, was found to be poorly maintained and unhygienic.", "Kanimozhi", "Area was cleaned and accommodated staffs will be shifted soon", "31.10.2026", "In Progress"),
                        (2, "KPM", "09.10.2026", "Open of wires in principal office,Inside the School Permises Wiring to be Done.", "Kanimozhi", "Maintenance team reviewed and waiting for quotation", "31.10.2026", "In Progress"),
                        (3, "KPM", "09.10.2026", "Antiskid tape need to placed on staircase(Quote Received ,After Board Exams Will be Completed )", "Kanimozhi", "Anti skip tape is waiting for principal mam approval. Rubber mats is planned to buy by next month", "31.10.2026", "In Progress"),
                        (4, "KPM", "09.10.2026", "Drivers Uniforms not given for KPM Drivers", "Nandha Kumar", "Uniform measurement taken for New Drivers .Waiting to recieve uniform from Vendor", "20.11.2026", "Closed"),
                        (5, "RPS", "10.10.2026", "Medicine stock list with expiry date need to update & maintain", "Wiilams", "medicine list is maintained & register is maintained", "31.10.2026", "Closed"),
                        (6, "RPS", "10.10.2026", "Emergenct contact no need to Display in security cabin", "Wiilams", "Emergency contact number is displayed", "31.10.2026", "Closed"),
                        (7, "RPS", "10.10.2026", "For girls restroom checklist isupdated & maintained. But boys restroom checklist not updated for first, second floor", "Wiilams", "Boys restroom checklist is updated and it will be followup for upcoming months", "31.10.2026", "Closed"),
                        (8, "RPS", "10.10.2026", "Daily Taste report need to update & maintain", "Wiilams", "Taste register is updated and maintained", "31.10.2026", "Closed"),
                        (9, "RPS", "10.10.2026", "Daily food Temperature Monitoring report need to create & maintain", "Wiilams", "Food temperature register is implemented and maintained", "31.10.2026", "Closed"),
                        (10, "RPS", "10.10.2026", "Vehicle no: 8174,2061, 7922, 8947 - camera not working, 8636 - cable problem", "Henry", "Quotation got from vendor. waiting for processing", "31.10.2026", "In Progress"),
                        (11, "RPS", "10.10.2026", "Drivers details need to display in all vehicle", "Henry", "Drivers details is maintained but need to display", "31.10.2026", "In Progress"),
                        (12, "RPS", "10.10.2026", "TN 99 Z 4505 - Insurance & fitness copy not available in the vehicle", "Henry", "TN 99 Z 4505 - Insurance & fitness copy available in the vehicle", "31.10.2026", "In Progress"),
                        (13, "RPS", "10.10.2026", "TN 99 AC 2234 - Insurance, Pollution & fitness copy not available in the vehicle", "Henry", "TN 99 AC 2234 - Insurance, Pollution & fitness copy available in the vehicle", "31.10.2026", "In Progress"),
                        (14, "RPS", "10.10.2026", "TN 99 AB 8636 - Fitness copy not available in the vehicle", "Henry", "TN 99 AB 8636 - Fitness copy available in the vehicle", "31.10.2026", "In Progress"),
                        (15, "RPS", "10.10.2026", "TN 99 AA 8200 - Insurance & fitness copy not available in the vehicle", "Henry", "TN 99 AA 8200 - Insurance & fitness copy available in the vehicle", "31.10.2026", "In Progress"),
                        (16, "RPS", "10.10.2026", "TN 99 X 1663 - Insurance, fitness & permit copy not available in the vehicle", "Henry", "TN 99 X 1663 - Insurance, fitness & permit copy available in the vehicle", "31.10.2026", "In Progress"),
                        (17, "RPS", "10.10.2026", "TN 99 A 8174 & TN 37 BX 5141 - Fitness copy not available in the vehicle", "Henry", "TN 99 A 8174 & TN 37 BX 5141 - Fitness copy available in the vehicle", "31.10.2026", "In Progress"),
                        (18, "RPS", "10.10.2026", "observation: Allergy details are available in the respective students' admission forms. However, a separate allergy list for students should be maintained", "Wiilams", "In Admission forms mentioned the allergy details of concern students but list not taken", "31.10.2026", "In Progress"),
                        (19, "RPS", "10.10.2026", "Observation: Anti skid tape & Rubber mats need to placed at Swimming Pool", "Wiilams", "Anti skip tape is waiting for principal mam approval.", "30.01.2026", "In Progress"),
                        (20, "RPS", "10.10.2026", "Observation: SOP for admin process need to implement & maintain", "Wiilams", "Created draft copy and it will be implemented soon", "30.11.2026", "In Progress"),
                        (21, "RPS", "10.10.2026", "Observation: Depth Marks of Pool are Not Marked", "Wiilams", "It will be marked when water is fully removed from the pool", "30.01.2026", "In Progress"),
                        (22, "RPS", "10.10.2026", "Observation: water sample is given for lab test", "Wiilams", "Report will be received by this month", "30.11.2026", "In Progress"),
                        (23, "RPS", "10.10.2026", "Observation:The Anti-Ragging, POSH, and Food Committee lists are available; however, they need to be updated with the names of the currently available staff members with updated dates.", "Wiilams", "Updated all list with currently available staffs", "31.10.2026", "In Progress"),
                        (24, "RTC", "15.10.2026", "Observation: Floor Wise Evacuation Map to be Maintained", "Jayabal", "Evacuation Map is on Progress will be Displayed", "30.12.2026", "In Progress"),
                        (25, "RTC", "15.10.2026", "Observation: First aid medicine tracker need to update & maintain", "Jayabal", "First aid Box placed register Will be Maintained", "31.10.2026", "Closed"),
                        (26, "RTC", "15.10.2026", "Student Details route wise need to display in all vehicle", "Jayabal& Nandhakumar", "Student Details route wise is under preparation", "31.10.2026", "Closed"),
                        (27, "RTC", "15.10.2026", "Driver's details need to displayed", "Jayabal& Nandhakumar", "Driver's details need to prepared and maintained", "31.10.2026", "Closed"),
                        (28, "RTC", "15.10.2026", "CCTV recording need to checked and maintained all vehicles", "Jayabal& Nandhakumar", "CCTV recording checked by manager", "31.10.2026", "Closed"),
                        (29, "Physio", "14.10.2026", "In ladies restrooms -> Health faucet need to cleaned and maintained", "Uma", "Health faucet has been cleaned and Maintained", "30.10.2026", "Closed"),
                        (30, "Physio", "14.10.2026", "Floor Wise Evacuation Map need to create and display on each floor", "Uma", "Floor Wise Evacuation Map need is under preparation & implemented soon", "30.12.2026", "In Progress"),
                        (31, "Physio", "14.10.2026", "Observation: Antiskid tape to be placed waiting for approval", "Uma", "After approval it will be implemented", "30.12.2026", "In Progress"),
                        (32, "Physio", "14.10.2026", "Driver's details need to display", "Uma", "Drivers details is maintained but need to display", "30.10.2026", "Closed"),
                        (33, "RGU", "28.10.2026", "Observation - Due to Manpower Shortage, cleaning work not carried out properly. Class room cleaning is done but mopping not done", "Subhash", "Concern entity incharge informed to HK manager about the concern. It will be followed & rectified soon", "31.10.2026", "Closed"),
                        (34, "RGU", "28.10.2026", "Observation: Floor Wise Evacuation Map need to be displayed", "Subhash", "Floor Wise Evacuation Map need is under preparation & implemented soon", "31.10.2026", "In Progress"),
                        (35, "RGU", "28.10.2026", "Emergency Contact Numbers to be Displayed at staff room & labs", "Subhash", "Emeregency contact is Prepared & will be displayed by next month", "31.10.2026", "In Progress"),
                        (36, "RGU", "28.10.2026", "Common area checklist need to be followed", "Subhash", "Checklist need to Update and Implemented", "31.10.2026", "Closed"),
                        (37, "RGU", "28.10.2026", "HK Cleaning Checklist not Updated for CV Raman Block", "Subhash", "HK Cleaning Checklist will be Updated for October Month", "31.10.2026", "Closed"),
                        (38, "RGU", "28.10.2026", "Class room keys maintained by dept heads. List need to maintained by admin", "Subhash", "Class room keys list will be taken & maintained", "31.10.2026", "In Progress"),
                        (39, "RGU", "28.10.2026", "Authorized list need to be displayed in electrical panel door in groundfloor", "Subhash", "Authorized Display board need to displayed", "31.10.2026", "In Progress"),
                        (40, "RGU", "28.10.2026", "Drivers details need to display", "Balaji", "Drivers details need to diplayed", "31.10.2026", "Closed"),
                        (41, "Pharmacy", "12.10.2026", "Floor wise evacuation map need to create and displayed on each floor", "Sampath", "Floor Wise Evacuation Map need is under preparation & implemented soon", "31.11.2026", "In Progress"),
                        (42, "Pharmacy", "12.10.2026", "Weekly once review done by AO & Ticketing sytem is maintained as record. 1. In first floor, Near to the lift, open space area door jamb found broken. Need to be fixed", "Sampath", "Ticket is raised and it will closed soon", "31.10.2026", "Closed"),
                        (43, "Pharmacy", "12.10.2026", "Driver's details need to display in the bus", "Sampath", "Drivers details is maintained but need to display", "31.10.2026", "Closed"),
                        (64, "ZIA", "31.10.2026", "Security Training Records and Calender to be Updated", "Abinaya", "Security Training has been Given Record Not Found", "15.11.2026", "In Progress"),
                        (65, "ZIA", "31.10.2026", "Floorwise Evacuation map not Available", "Abinaya", "Fire evacuation plan need to prepared and maintain", "15.11.2026", "In Progress"),
                        (66, "ZIA", "31.10.2026", "Fire Extinguisher Awareness to be Done Properly", "Abinaya", "Fire Extinguisher Training Will be Provided within this Month Discussion With Vendor", "15.11.2026", "In Progress"),
                        (67, "ZIA", "31.10.2026", "Pool Depth Mark not done", "Abinaya", "Maintenance Ticket has been Raised", "15.11.2026", "In Progress"),
                        (68, "ZIA", "31.10.2026", "Agreement Copies of Buildings are not available", "Abinaya", "Agreement copies of building available with management", "15.11.2026", "In Progress"),
                        (69, "ZIA", "31.10.2026", "Construction ,Fire Safety Drawing not available", "Abinaya", "Construction ,Fire Safety Drawing available with management", "15.11.2026", "In Progress"),
                        (71, "ZIA", "31.10.2026", "Building insurance not avaialable ,", "Abinaya", "Building Insurance copy has been Requested With Mr. Vijayakumar .Follow up on Progress", "15.11.2026", "In Progress"),
                        (72, "ZIA", "31.10.2026", "Housekeeping Training and schedule not followed", "Abinaya", "Housekeeping Training and schedule need to implement", "15.11.2026", "In Progress"),
                        (73, "ZIA", "31.10.2026", "MOM With Security staff to be Updated", "Abinaya", "MOM record to be updated", "15.11.2026", "In Progress"),
                        (74, "ZIA", "31.10.2026", "CCTV Not Available", "Abinaya", "CCTV Will be Installed in Every cabs after discussion with vendors", "15.11.2026", "In Progress"),
                        (75, "ZIA", "31.10.2026", "Route List not Displayed", "Abinaya", "Route List Will be Displayed in Every Vehicle", "15.11.2026", "In Progress"),
                        (76, "ZIA", "31.10.2026", "Rules and Regulations not displayed", "Abinaya", "Rules and Regulations will be Displayed at Cabs", "15.11.2026", "In Progress"),
                        (78, "TIPS", "17.10.2026", "TN 38 CQ 4848 ,TN 38 DF 6112,-TN 99 Q 8166, TN 41 AD 3600,TN 38 CT 0037 - CCTV Not in working", "Chandrasekar", "Informed to Transport Manager", "30.11.2026", "In Progress"),
                        (79, "TIPS", "17.10.2026", "Copy of RC book not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (80, "TIPS", "17.10.2026", "Copy of Vehicle Insurance not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (81, "TIPS", "17.10.2026", "Copy of Vehicle Road Tax Paid not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (82, "TIPS", "17.10.2026", "Copy of Vehicle Fitness certificate not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (83, "TIPS", "17.10.2026", "Copy of Vehicle Permit copy not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (84, "TIPS", "17.10.2026", "Copy of PUC-Pollution under Control certificate not available in any vehicle", "Chandrasekar", "Updated Soft Copy will be Kept in vehicle", "15.11.2026", "In Progress"),
                        (85, "TIPS", "17.10.2026", "Incident register not available", "Chandrasekar", "Incident register Format Given and Explained", "15.11.2026", "In Progress"),
                        (86, "TIPS", "17.10.2026", "MOM with Drivers & Vendor need to maintain", "Chandrasekar", "Minutes of Meeting has been Conducted .Record will be updated after next meeting", "15.11.2026", "In Progress"),
                        (87, "TIPS", "17.10.2026", "Log Book / Feedback Register need to maintain", "Chandrasekar", "Feedback register Available .Will be Maintained", "15.11.2026", "In Progress"),
                        (88, "IT &CCTV", "22.10.2026", "Rack Dressing and Cable Tagging work inprogress", "Prabhu", "Rack Dressing on Progress", "30.11.2026", "In Progress"),
                        (89, "IT &CCTV", "22.10.2026", "Tempreature to be Monitor", "Prabhu", "Install & maintain a suitable temperature monitoring system and record server-room temperature.", "30.11.2026", "In Progress"),
                        (90, "IT &CCTV", "22.10.2026", "5 Cameras recording are not Done", "Manimaran", "Vendor Working on Progress need to Verify 5 Cameras", "30.11.2026", "In Progress"),
                        (91, "Stores", "24.10.2026", "Material Requistion slip: 1. Indent no: 1459 date: 26.09.2026, dept: Project, Surface light 18W - 12 qty. 2. Indent no: 1452 date: 11.09.2026, dept: Project, Tube light - 4qty. 3. Indent no: 1319 date: 25.09.2026, 3M cover plate - Havelles- 1qty, Maintenance dept, location: Kings 4. 4. Indent no: 1316 date: 11.09.2026, dept: maintenance, Location: Kings2, Fan head - 3qty. Observation: Issued by sign need to be followed in all Material requisition slip.", "Kannappan", "Issued sign is done and it will be followed & maintained", "30.10.2026", "Closed"),
                        (92, "Stores", "24.10.2026", "Security and stores inward seal is followed in all inward documents but for outward seal is not maintained.", "Kannappan", "Outward seal maintained in main gate. Need to get approval for maintaining in stores", "30.10.2026", "In Progress"),
                    ]
                    for s_no, dept, nc_dt, desc, resp, act, t_dt, st in seed_nc:
                        cur.execute(
                            """
                            INSERT INTO audit_nc_tracker (
                                period_id, s_no, nc_no, department, area, nc_description,
                                corrective_action, responsible_person, target_date, status
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (oct_pid, s_no, f"NC-{s_no}", dept, nc_dt, desc, act, resp, t_dt, st),
                        )
        conn.commit()
        print("  [OK] Audit Master Departments & Initial Oct-26 Data Seeded")
    finally:
        db.release_db_connection(conn)


def sync_all_transport_fleet_tables():
    """
    Filters existing Transport data by fleet (KPM, RPS, University, Common) from the
    shared tables and upserts/refreshes all 16 per-fleet tables:
      - transport_census_{fleet}
      - transport_vehicles_{fleet}
      - transport_expenses_{fleet}
      - transport_budget_{fleet}
    """
    fleets = [
        ("kpm", "KPM"),
        ("rps", "RPS"),
        ("university", "University"),
        ("common", "Common"),
    ]
    conn = db.get_db_connection()
    summary = {}
    try:
        with conn.cursor() as cur:
            # 0. Ensure census parking_fastag & cctv_replacement reflect vehicle ledger sums when census is 0
            cur.execute("""
                UPDATE transport_census_entries tce
                SET parking_fastag = CASE WHEN COALESCE(tce.parking_fastag, 0) = 0 THEN v.sum_park ELSE tce.parking_fastag END,
                    cctv_replacement = CASE WHEN COALESCE(tce.cctv_replacement, 0) = 0 THEN v.sum_cctv ELSE tce.cctv_replacement END
                FROM (
                    SELECT period_id, LOWER(branch) AS lbranch,
                           COALESCE(SUM(parking_fastag), 0) AS sum_park,
                           COALESCE(SUM(cctv_replacement), 0) AS sum_cctv
                    FROM transport_vehicle_entries
                    GROUP BY period_id, LOWER(branch)
                ) v
                WHERE tce.period_id = v.period_id
                  AND LOWER(tce.branch) = v.lbranch
                  AND ((COALESCE(tce.parking_fastag, 0) = 0 AND v.sum_park > 0)
                    OR (COALESCE(tce.cctv_replacement, 0) = 0 AND v.sum_cctv > 0));
            """)

            for fk, b_name in fleets:
                # 1. Census: refresh matching period rows from transport_census_entries
                cur.execute(
                    f"""
                    DELETE FROM transport_census_{fk}
                    WHERE period_id IN (
                        SELECT period_id FROM transport_census_entries WHERE LOWER(branch) = %s
                    );
                    INSERT INTO transport_census_{fk}
                    SELECT * FROM transport_census_entries WHERE LOWER(branch) = %s;
                    """,
                    (fk, fk),
                )

                # 2. Vehicles: refresh from transport_vehicle_entries
                cur.execute(f"DELETE FROM transport_vehicles_{fk};")
                cur.execute(
                    f"""
                    INSERT INTO transport_vehicles_{fk}
                    SELECT * FROM transport_vehicle_entries WHERE LOWER(branch) = %s;
                    """,
                    (fk,),
                )

                # 3. Expenses: refresh from transport_expense_entries
                cur.execute(f"DELETE FROM transport_expenses_{fk};")
                cur.execute(
                    f"""
                    INSERT INTO transport_expenses_{fk}
                    SELECT id, period_id, cost_head_id, vendor_id, amount, status::text, remarks,
                           recorded_by, audited_at, created_at, updated_at, module, branch
                    FROM transport_expense_entries WHERE LOWER(branch) = %s;
                    """,
                    (fk,),
                )

                # 4. Budget: sync sanctioned amounts from transport_budget_tracking where present
                cur.execute(
                    f"""
                    UPDATE transport_budget_{fk} fb
                    SET sanctioned_amount = tbt.sanctioned_amount,
                        updated_at = CURRENT_TIMESTAMP
                    FROM transport_budget_tracking tbt
                    WHERE LOWER(tbt.branch) = %s
                      AND LOWER(TRIM(tbt.param_name)) = LOWER(TRIM(fb.param_name));
                    """,
                    (fk,),
                )

                cur.execute(f"SELECT COUNT(*) FROM transport_census_{fk};")
                c_cnt = cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM transport_vehicles_{fk};")
                v_cnt = cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM transport_expenses_{fk};")
                e_cnt = cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM transport_budget_{fk};")
                b_cnt = cur.fetchone()[0]

                summary[b_name] = {
                    "census": c_cnt,
                    "vehicles": v_cnt,
                    "expenses": e_cnt,
                    "budget": b_cnt,
                }
        conn.commit()
        print("  [OK] Synced & Filtered All 16 Per-Fleet Transport Tables:", summary)
        return summary
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        db.release_db_connection(conn)


if __name__ == "__main__":
    ok = run_migrations()
    if not ok:
        sys.exit(1)
