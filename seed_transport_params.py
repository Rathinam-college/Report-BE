import sys
import os
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

TRANSPORT_MASTER_PARAMS = [
    # Section 1: Fleet Operations & Distance (Image lines 1-7)
    ('vehicles_count', 'Number of vehicles', 'Fleet Operations & Distance', 1, 'text', 'Fleet', None, 1),
    ('passengers_count', 'Number of students & staff travelling', 'Fleet Operations & Distance', 1, 'single_count', 'Persons', None, 2),
    ('approved_kms', 'Approved trip KMs', 'Fleet Operations & Distance', 1, 'single_number', 'KMs', None, 3),
    ('actual_kms', 'Actual trip KMs', 'Fleet Operations & Distance', 1, 'single_number', 'KMs', None, 4),
    ('excess_minus_kms_rps', 'Excess/ minus KMs run for RPS', 'Fleet Operations & Distance', 1, 'single_number', 'KMs', 'Actual trip KMs - Approved trip KMs', 5),
    ('excess_kms_billed_rps', 'Excess KM to be billed for RPS', 'Fleet Operations & Distance', 1, 'single_number', 'KMs', None, 6),
    ('additional_kms', 'Additional KMs run', 'Fleet Operations & Distance', 1, 'single_number', 'KMs', None, 7),

    # Section 2: Fleet Expenses & Operations (Image lines 8-14, Orange/Green block)
    ('fuel_expenses', 'Fuel expenses (Rs)', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 8),
    ('fc_cost', 'FC 2025-2026', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 9),
    ('statutory_cost', 'Vehicle Statutory', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 10),
    ('repair_maintenance_cost', 'Repair & Maintenance', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 11),
    ('other_cost', 'Others', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 12),
    ('employee_cost', 'Transport Employees Cost', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', None, 13),
    ('total_expenses', 'Total Expenses', 'Fleet Expenses & Operations', 2, 'cost', 'INR (₹)', 'Fuel + FC + Statutory + Repair & Maint + Others + Employees Cost', 14),

    # Section 3: Revenue, Deductions & Cumulative Income (Image lines 15-24, Tan block)
    ('students_count_income', 'Students count', 'Revenue, Deductions & Income', 3, 'single_count', 'Students', None, 15),
    ('staff_count_income', 'Staff Count', 'Revenue, Deductions & Income', 3, 'single_count', 'Staff', None, 16),
    ('fee_demand', 'Demand', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 17),
    ('fee_collected', 'Paid', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 18),
    ('fee_unpaid', 'Unpaid', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', 'Demand - Paid', 19),
    ('rps_monthly_billing', 'RPS monthly billing', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 20),
    ('staff_travel_deduction', 'Staff Travel Deduction', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 21),
    ('additional_kms_billed_rps', 'Additional KMs Billed for RPS', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 22),
    ('additional_kms_others_billing', 'Additional KMs run for others Billing', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', None, 23),
    ('cumulative_income', 'Cumulative Income', 'Revenue, Deductions & Income', 3, 'cost', 'INR (₹)', 'Paid + RPS monthly billing + Staff Travel Deduction + Additional KMs Billed', 24),

    # Section 4: Operating Budget & Financial Balance (Image lines 25-27, Light Green block)
    ('approved_budget', 'Approved Budget', 'Operating Budget & Balance', 4, 'cost', 'INR (₹)', None, 25),
    ('cumulative_budget_spent', 'Cumulative Budget spent (Actual expenses) till now', 'Operating Budget & Balance', 4, 'cost', 'INR (₹)', None, 26),
    ('balance', 'Balance', 'Operating Budget & Balance', 4, 'cost', 'INR (₹)', 'Approved Budget - Cumulative Budget spent', 27),

    # Section 5: Service Tickets & Quality Issues (Image lines 30-35, 28, 29, Purple block)
    ('service_tickets_raised', 'No. of Service Tickets Raised', 'Service Tickets & Compliance', 5, 'single_count', 'Tickets', None, 28),
    ('service_tickets_closed', 'No. of Service Tickets closed', 'Service Tickets & Compliance', 5, 'single_count', 'Tickets', None, 29),
    ('service_tickets_open', 'No. of Service Tickets in Open', 'Service Tickets & Compliance', 5, 'single_count', 'Tickets', 'Raised - Closed', 30),
    ('quality_issues_received', 'No. of Quality issues Received', 'Service Tickets & Compliance', 5, 'single_count', 'Issues', None, 31),
    ('quality_issues_closed', 'No. of Quality issues Closed', 'Service Tickets & Compliance', 5, 'single_count', 'Issues', None, 32),
    ('quality_issues_open', 'No. of Quality issues in Open', 'Service Tickets & Compliance', 5, 'single_count', 'Issues', 'Received - Closed', 33),
    ('statutory_compliance', 'Statutory compliance', 'Service Tickets & Compliance', 5, 'single_count', 'Score', None, 34),
    ('incidents_count', 'No. of Incidents', 'Service Tickets & Compliance', 5, 'single_count', 'Incidents', None, 35),

    # Section 6: Fuel Purchase & Energy Metrics (Image line 36, White block)
    ('diesel_litres', 'Diesel Purchase Qty (Litres)', 'Fuel & Energy Consumption', 6, 'single_number', 'Litres', None, 36),

    # Section 7: Student Fee Analytics & Unit Economics (Image lines 29-37, Yellow block)
    ('students_count_fee', 'Students count (Fee Register)', 'Student Transport Fee Analytics', 7, 'single_count', 'Students', None, 37),
    ('demand_fee', 'Demand (Fee Demand)', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 38),
    ('fee_discount', 'Discount', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 39),
    ('paid_fee', 'Paid (Collected)', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 40),
    ('unpaid_fee', 'Unpaid (Outstanding)', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', 'Demand - Discount - Paid', 41),
    ('per_student_cost_expenses', 'Per student cost expenses', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', 'Total Expenses / Students count', 42),
    ('per_student_fee_year', 'per student fee per year', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 43),
    ('demand_per_km_day', 'Demand per km per day', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', 'Demand / Actual trip KMs / 30', 44),
    ('km_per_veh_day', 'km/veh/day', 'Student Transport Fee Analytics', 7, 'single_number', 'KM/Veh/Day', 'Actual trip KMs / Vehicles / 30', 45),
    ('cumulative_demand_per_km', 'Cumulative demand per KM', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 46),
    ('cab_billing', 'Cab request Billing', 'Student Transport Fee Analytics', 7, 'cost', 'INR (₹)', None, 47)
]

def migrate_and_seed_transport_params():
    print("Setting up transport_master_parameters table and columns...")
    
    # 1. Add custom_metrics column to transport_census_entries
    try:
        db.execute_commit("ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;")
        print("  [OK] Added custom_metrics JSONB to transport_census_entries")
    except Exception as e:
        print(f"  Notice custom_metrics: {e}")

    # 2. Create transport_master_parameters table
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS transport_master_parameters (
        id SERIAL PRIMARY KEY,
        param_key VARCHAR(100) UNIQUE NOT NULL,
        param_name VARCHAR(255) NOT NULL,
        section VARCHAR(100) NOT NULL,
        section_order INT NOT NULL DEFAULT 1,
        input_type VARCHAR(50) NOT NULL DEFAULT 'cost',
        unit VARCHAR(50) DEFAULT '',
        formula TEXT DEFAULT NULL,
        display_order INT NOT NULL DEFAULT 1,
        is_system BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """
    db.execute_commit(create_table_sql)
    print("  [OK] Table transport_master_parameters verified")

    # 3. Seed parameters
    upsert_sql = """
    INSERT INTO transport_master_parameters (
        param_key, param_name, section, section_order,
        input_type, unit, formula, display_order, is_system, is_active
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE)
    ON CONFLICT (param_key) DO UPDATE SET
        param_name = EXCLUDED.param_name,
        section = EXCLUDED.section,
        section_order = EXCLUDED.section_order,
        input_type = EXCLUDED.input_type,
        unit = EXCLUDED.unit,
        formula = EXCLUDED.formula,
        display_order = EXCLUDED.display_order;
    """
    for p in TRANSPORT_MASTER_PARAMS:
        db.execute_commit(upsert_sql, p)
    
    print(f"  [OK] Seeded {len(TRANSPORT_MASTER_PARAMS)} parameters into transport_master_parameters")

if __name__ == "__main__":
    migrate_and_seed_transport_params()
