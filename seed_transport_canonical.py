import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

CANONICAL_TRANSPORT_PARAMETERS = [
    # Section 1: Fleet Operations & Distance (White)
    ('1', 'vehicles_count', 'Number of vehicles', 'Fleet Operations & Distance', 1, 1, 'text', 'Fleet', None),
    ('2', 'passengers_count', 'Number of students & staff travelling', 'Fleet Operations & Distance', 1, 2, 'single_count', 'Persons', None),
    ('3', 'approved_kms', 'Approved trip KMs', 'Fleet Operations & Distance', 1, 3, 'single_number', 'KMs', None),
    ('4', 'actual_kms', 'Actual trip KMs', 'Fleet Operations & Distance', 1, 4, 'single_number', 'KMs', None),
    ('5', 'excess_minus_kms_rps', 'Execess/ minus KMs run for RPS', 'Fleet Operations & Distance', 1, 5, 'single_number', 'KMs', 'actual_kms - approved_kms'),
    ('6', 'excess_kms_billed_rps', 'Execess KM to be billed for RPS', 'Fleet Operations & Distance', 1, 6, 'single_number', 'KMs', None),
    ('7', 'additional_kms', 'Additional KMs run', 'Fleet Operations & Distance', 1, 7, 'single_number', 'KMs', None),

    # Section 2: Fleet Expenses & Operations (Orange, lime green total)
    ('8', 'fuel_expenses', 'Fuel expenses (Rs)', 'Fleet Expenses & Operations', 2, 8, 'cost', 'INR (₹)', None),
    ('9', 'fc_cost', 'FC 2025-2026', 'Fleet Expenses & Operations', 2, 9, 'cost', 'INR (₹)', None),
    ('10', 'statutory_cost', 'Vehicle Statutory', 'Fleet Expenses & Operations', 2, 10, 'cost', 'INR (₹)', None),
    ('11', 'repair_maintenance_cost', 'Repair & Maintenance', 'Fleet Expenses & Operations', 2, 11, 'cost', 'INR (₹)', None),
    ('12', 'other_cost', 'Others', 'Fleet Expenses & Operations', 2, 12, 'cost', 'INR (₹)', None),
    ('13', 'employee_cost', 'Transport Employees Cost', 'Fleet Expenses & Operations', 2, 13, 'cost', 'INR (₹)', None),
    ('14', 'total_expenses', 'Total Expenses', 'Fleet Expenses & Operations', 2, 14, 'cost', 'INR (₹)', 'SUM(Fuel + FC + Statutory + Repair + Others + Employees Cost)'),

    # Section 3: Revenue, Deductions & Income (Tan)
    ('15', 'students_count_income', 'Students count', 'Revenue, Deductions & Income', 3, 15, 'single_count', 'Students', None),
    ('16', 'staff_count_income', 'Staff Count', 'Revenue, Deductions & Income', 3, 16, 'single_count', 'Staff', None),
    ('17', 'fee_demand', 'Demand', 'Revenue, Deductions & Income', 3, 17, 'cost', 'INR (₹)', None),
    ('18', 'fee_collected', 'Paid', 'Revenue, Deductions & Income', 3, 18, 'cost', 'INR (₹)', None),
    ('19', 'fee_unpaid', 'Unpaid', 'Revenue, Deductions & Income', 3, 19, 'cost', 'INR (₹)', 'Demand - Paid'),
    ('20', 'rps_monthly_billing', 'RPS monthly billing', 'Revenue, Deductions & Income', 3, 20, 'cost', 'INR (₹)', None),
    ('21', 'staff_travel_deduction', 'Staff Travel Deduction', 'Revenue, Deductions & Income', 3, 21, 'cost', 'INR (₹)', None),
    ('22', 'additional_kms_billed_rps', 'Additional KMs Billed for RPS', 'Revenue, Deductions & Income', 3, 22, 'cost', 'INR (₹)', None),
    ('23', 'additional_kms_others_billing', 'Additional KMs run for others Billing', 'Revenue, Deductions & Income', 3, 23, 'cost', 'INR (₹)', None),
    ('24', 'cumulative_income', 'Cumulative Income', 'Revenue, Deductions & Income', 3, 24, 'cost', 'INR (₹)', 'Paid + RPS Billing + Staff Deduction + Addl KMs + Cab Billing'),

    # Section 4: Operating Budget & Balance (Light Green, lime green balance)
    ('25', 'approved_budget', 'Approved Budget', 'Operating Budget & Balance', 4, 25, 'cost', 'INR (₹)', None),
    ('26', 'cumulative_budget_spent', 'Cumulative Budget spent (Actual expenses) till now', 'Operating Budget & Balance', 4, 26, 'cost', 'INR (₹)', None),
    ('27', 'balance', 'Balance', 'Operating Budget & Balance', 4, 27, 'cost', 'INR (₹)', 'Approved Budget - Cumulative Budget Spent'),

    # Section 5: Service Tickets & Compliance (Purple)
    ('30', 'service_tickets_raised', 'No. of Service Tickets Raised', 'Service Tickets & Compliance', 5, 28, 'single_count', 'Tickets', None),
    ('31', 'service_tickets_closed', 'No. of Service Tickets closed', 'Service Tickets & Compliance', 5, 29, 'single_count', 'Tickets', None),
    ('32', 'service_tickets_open', 'No. of Service Tickets in Open', 'Service Tickets & Compliance', 5, 30, 'single_count', 'Tickets', 'Raised - Closed'),
    ('33', 'quality_issues_received', 'No. of Quality issues Received', 'Service Tickets & Compliance', 5, 31, 'single_count', 'Issues', None),
    ('34', 'quality_issues_closed', 'No. of Quality issues Closed', 'Service Tickets & Compliance', 5, 32, 'single_count', 'Issues', None),
    ('35', 'quality_issues_open', 'No. of Quality issues in Open', 'Service Tickets & Compliance', 5, 33, 'single_count', 'Issues', 'Received - Closed'),
    ('28', 'statutory_compliance', 'Statuory compliance', 'Service Tickets & Compliance', 5, 34, 'single_count', 'Score', None),
    ('29', 'incidents_count', 'No. of Incidents', 'Service Tickets & Compliance', 5, 35, 'single_count', 'Incidents', None),

    # Section 6: Fuel & Energy Consumption (White)
    ('36', 'diesel_litres', 'Diesel Purchase Qty (Litres)', 'Fuel & Energy Consumption', 6, 36, 'single_number', 'Litres', None),

    # Section 7: Student Transport Fee Analytics (Yellow)
    ('29', 'students_count_fee', 'Students count', 'Student Transport Fee Analytics', 7, 37, 'single_count', 'Students', None),
    ('30', 'demand_fee', 'Demand', 'Student Transport Fee Analytics', 7, 38, 'cost', 'INR (₹)', None),
    ('31', 'fee_discount', 'Discount', 'Student Transport Fee Analytics', 7, 39, 'cost', 'INR (₹)', None),
    ('32', 'paid_fee', 'Paid', 'Student Transport Fee Analytics', 7, 40, 'cost', 'INR (₹)', None),
    ('33', 'unpaid_fee', 'Unpaid', 'Student Transport Fee Analytics', 7, 41, 'cost', 'INR (₹)', 'Demand - Discount - Paid'),
    ('34', 'per_student_cost_expenses', 'Per student cost expenses', 'Student Transport Fee Analytics', 7, 42, 'cost', 'INR (₹)', 'Total Expenses / Students Count'),
    ('', 'per_student_fee_year', 'per student fee per year', 'Student Transport Fee Analytics', 7, 43, 'cost', 'INR (₹)', 'Demand / Students Count'),
    ('', 'demand_per_km_day', 'Demand per km per day', 'Student Transport Fee Analytics', 7, 44, 'cost', 'INR (₹)', 'Demand / (Actual KMs * 30)'),
    ('', 'km_per_veh_day', 'km/veh/day', 'Student Transport Fee Analytics', 7, 45, 'single_number', 'KM/Veh/Day', 'Actual KMs / (Vehicles * 30)'),
    ('', 'cumulative_demand_per_km', 'Cumulative demand per KM', 'Student Transport Fee Analytics', 7, 46, 'cost', 'INR (₹)', 'Demand / Actual KMs'),
    ('37', 'cab_billing', 'Cab request Billing', 'Student Transport Fee Analytics', 7, 47, 'cost', 'INR (₹)', None)
]

def ensure_and_seed_transport_parameters():
    """
    Ensures transport_master_parameters table exists with all required columns
    and populates the 47 canonical parameters.
    """
    try:
        # 1. Create table if not exists
        db.execute_commit("""
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
        """)

        # 2. Add s_no column if missing
        db.execute_commit("ALTER TABLE transport_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';")

        # 3. Add custom_metrics and branch to transport_census_entries
        db.execute_commit("ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;")
        db.execute_commit("ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) DEFAULT 'Common';")

        # 4. Remove any test rows
        db.execute_commit("DELETE FROM transport_master_parameters WHERE param_key ILIKE %s;", ('%test%',))

        # 5. Upsert 47 canonical parameters
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for s_no, key, name, sec, sec_ord, disp_ord, in_type, unit, formula in CANONICAL_TRANSPORT_PARAMETERS:
                    cur.execute('''
                        INSERT INTO transport_master_parameters (
                            s_no, param_key, param_name, section, section_order, display_order, input_type, unit, formula, is_system, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE)
                        ON CONFLICT (param_key) DO UPDATE SET
                            s_no = EXCLUDED.s_no,
                            param_name = EXCLUDED.param_name,
                            section = EXCLUDED.section,
                            section_order = EXCLUDED.section_order,
                            display_order = EXCLUDED.display_order,
                            input_type = EXCLUDED.input_type,
                            unit = EXCLUDED.unit,
                            formula = EXCLUDED.formula,
                            is_active = TRUE;
                    ''', (s_no, key, name, sec, sec_ord, disp_ord, in_type, unit, formula))
                conn.commit()
        finally:
            db.release_db_connection(conn)

        print("[TransportSync] Verified and synced 47 canonical parameters.")
        return True
    except Exception as e:
        print(f"[TransportSync] Error: {e}")
        return False

if __name__ == '__main__':
    ensure_and_seed_transport_parameters()
