import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

CANONICAL_HOSTEL_PARAMETERS = [
    # Section 1: Occupancy & Census (Excel Rows 1 - 7 + Sub-rows)
    ('1', 'bed_capacity', 'Bed Capacity', 'Occupancy & Census', 1, 1, 'boys_girls_total', 'Beds', 'Boys + Girls'),
    ('2', 'students_count', 'No. of students', 'Occupancy & Census', 1, 2, 'boys_girls_total', 'Persons', 'Boys + Girls'),
    ('3', 'staff_count', 'No. of staffs', 'Occupancy & Census', 1, 3, 'boys_girls_total', 'Staff', 'Boys + Girls'),
    ('4', 'total_occupied', 'Total Occupied', 'Occupancy & Census', 1, 4, 'boys_girls_total', 'Occupants', 'Students + Staffs'),
    ('5', 'vacant', 'Vacant', 'Occupancy & Census', 1, 5, 'boys_girls_total', 'Beds', 'Bed Capacity - Total Occupied'),
    ('6', 'vacant_college', 'Vacant for college students', 'Occupancy & Census', 1, 6, 'boys_girls_total', 'Beds', None),
    ('', 'vacant_sports', 'Vacant for college sports students (KPM hostel)', 'Occupancy & Census', 1, 7, 'boys_girls_total', 'Beds', None),
    ('', 'vacant_school', 'Vacant for school students', 'Occupancy & Census', 1, 8, 'boys_girls_total', 'Beds', None),
    ('', 'occupied_pct', 'Occupied %', 'Occupancy & Census', 1, 9, 'percentage', '%', '(Total Occupied / Bed Capacity) * 100'),
    ('', 'vacant_pct', 'Vacant %', 'Occupancy & Census', 1, 10, 'percentage', '%', '(Vacant / Bed Capacity) * 100'),
    ('', 'students_vacated', 'Students Vacated', 'Occupancy & Census', 1, 11, 'single_count', 'Students', None),

    # Section 2: Maintenance & Quality Tickets (Excel Rows 8 - 16)
    ('8', 'tickets_received', 'No. of Maintenance Tickets Received', 'Maintenance & Quality Tickets', 2, 12, 'single_count', 'Tickets', None),
    ('9', 'tickets_closed', 'No. of Maintenance Tickets closed', 'Maintenance & Quality Tickets', 2, 13, 'single_count', 'Tickets', None),
    ('10', 'tickets_open', 'No. of Maintenance Tickets in Open', 'Maintenance & Quality Tickets', 2, 14, 'single_count', 'Tickets', 'Tickets Received - Tickets Closed'),
    ('11', 'total_hours_close', 'Total Hours taken to close the tickets', 'Maintenance & Quality Tickets', 2, 15, 'single_number', 'Hours', None),
    ('12', 'tat_hours', 'TAT (Turnaround Time)Hours', 'Maintenance & Quality Tickets', 2, 16, 'single_number', 'Hours', 'Total Hours / Tickets Closed'),
    ('13', 'quality_issues_received', 'No. of Quality issues Received', 'Maintenance & Quality Tickets', 2, 17, 'single_count', 'Issues', None),
    ('14', 'quality_issues_closed', 'No. of Quality issues Closed', 'Maintenance & Quality Tickets', 2, 18, 'single_count', 'Issues', None),
    ('15', 'quality_issues_open', 'No. of Quality issues in Open', 'Maintenance & Quality Tickets', 2, 19, 'single_count', 'Issues', 'Received - Closed'),
    ('16', 'incidents_count', 'No. of Incidents', 'Maintenance & Quality Tickets', 2, 20, 'single_count', 'Incidents', None),

    # Section 3: Utilities & Operational Expenses (Excel Rows 17 - 20)
    ('17', 'power_consumption', 'Power Consumption', 'Utilities & Operational Expenses', 3, 21, 'units_and_cost', 'kWh & ₹', None),
    ('18', 'water_purchase_cost', 'Water Purchase Expenses', 'Utilities & Operational Expenses', 3, 22, 'cost', 'INR (₹)', None),
    ('', 'maintenance_expenses', 'Maintenance Expenses', 'Utilities & Operational Expenses', 3, 23, 'cost', 'INR (₹)', None),
    ('20', 'expenses_occurred', 'Expenses occurred (Total Spend)', 'Utilities & Operational Expenses', 3, 24, 'cost', 'INR (₹)', 'Sum of Monthly Operational Expenses'),

    # Section 4: Budget & Financial Balance (Excel Rows 22 - 24)
    ('22', 'approved_budget', 'Approved Budget', 'Budget & Financial Balance', 4, 25, 'cost', 'INR (₹)', None),
    ('23', 'cumulative_budget_spent', 'Cumulative Budget spent (Actual expenses) till now', 'Budget & Financial Balance', 4, 26, 'cost', 'INR (₹)', None),
    ('24', 'balance', 'Balance', 'Budget & Financial Balance', 4, 27, 'cost', 'INR (₹)', 'Approved Budget - Cumulative Budget Spent'),

    # Section 5: Per Student & Area Metrics (Excel Rows 25 - 28)
    ('25', 'students_kpi', 'Number of students', 'Per Student & Area Metrics', 5, 28, 'single_count', 'Students', 'Total Students in Hostel'),
    ('26', 'per_student_cost_month', 'Per student cost per month', 'Per Student & Area Metrics', 5, 29, 'cost', 'INR (₹)', 'Expenses occurred / Number of students'),
    ('27', 'per_student_cost_day', 'Per student cost per day', 'Per Student & Area Metrics', 5, 30, 'cost', 'INR (₹)', 'Per student cost per month / 30'),
    ('', 'sq_feet', 'Sq feet (Hostel Area)', 'Per Student & Area Metrics', 5, 31, 'single_number', 'sq.ft', None),
    ('', 'sq_feet_per_occupant', 'Sq feet per occupant in hostel', 'Per Student & Area Metrics', 5, 32, 'single_number', 'sq.ft/occ', 'Sq feet / Total Occupied'),
    ('28', 'normal_water_student_month', 'Normal water per student per month (Ltrs & cost)', 'Per Student & Area Metrics', 5, 33, 'units_and_cost', 'Ltr & ₹', None),

    # Section 6: Water & Utilities Deep Dive (Excel Rows 38 - 54)
    ('', 'power_cost_sqft', 'Power cost per sq feet', 'Water & Utilities Deep Dive', 6, 34, 'cost', '₹/sq.ft', 'Power cost / Sq feet'),
    ('', 'units_per_occupant', 'Units per occupant per month - Hostel', 'Water & Utilities Deep Dive', 6, 35, 'single_number', 'kWh/occ', 'Power units / Total Occupied'),
    ('', 'power_cost_occupant', 'Power cost Per occupant per month - Hostel', 'Water & Utilities Deep Dive', 6, 36, 'cost', '₹/occ', 'Power cost / Total Occupied'),
    ('', 'normal_water_litres', 'Normal Water Consumption Ltr Hostels', 'Water & Utilities Deep Dive', 6, 37, 'single_number', 'Litres', None),
    ('', 'normal_water_cost', 'Normal Water Consumption Cost Hostels', 'Water & Utilities Deep Dive', 6, 38, 'cost', 'INR (₹)', None),
    ('', 'normal_water_ltr_day', 'Normal water Ltr per student per day - Hostels', 'Water & Utilities Deep Dive', 6, 39, 'single_number', 'L/day', 'Normal Water Ltr / Total Students / 30'),
    ('', 'normal_water_cost_day', 'Normal Water cost Per student per day Hostels', 'Water & Utilities Deep Dive', 6, 40, 'cost', '₹/day', 'Normal Water Cost / Total Students / 30'),
    ('', 'drinking_water_litres', 'Drinking Water Consumption Litres Hostels', 'Water & Utilities Deep Dive', 6, 41, 'single_number', 'Litres', None),
    ('', 'drinking_water_cost', 'Drinking Water Consumption Cost Hostels', 'Water & Utilities Deep Dive', 6, 42, 'cost', 'INR (₹)', None),
    ('', 'drinking_water_ltr_day', 'Drinking water Litres per student per day- Hostels', 'Water & Utilities Deep Dive', 6, 43, 'single_number', 'L/day', 'Drinking Water Ltr / Total Students / 30'),
    ('', 'drinking_water_cost_day', 'Drinking Water cost Per student per day Hostels', 'Water & Utilities Deep Dive', 6, 44, 'cost', '₹/day', 'Drinking Water Cost / Total Students / 30')
]

def ensure_and_seed_hostel_parameters():
    """
    Ensures hostel_master_parameters table exists with all required columns
    and populates the 44 canonical parameters if empty or missing.
    """
    try:
        # 1. Create table if not exists
        db.execute_commit("""
        CREATE TABLE IF NOT EXISTS hostel_master_parameters (
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
        db.execute_commit("ALTER TABLE hostel_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';")

        # 3. Add custom_metrics to hostel_census_entries
        db.execute_commit("ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;")

        # 4. Upsert canonical parameters
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for s_no, key, name, sec, sec_ord, disp_ord, in_type, unit, formula in CANONICAL_HOSTEL_PARAMETERS:
                    cur.execute('''
                        INSERT INTO hostel_master_parameters (
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
                            formula = COALESCE(hostel_master_parameters.formula, EXCLUDED.formula),
                            is_active = TRUE;
                    ''', (s_no, key, name, sec, sec_ord, disp_ord, in_type, unit, formula))
                conn.commit()
        finally:
            db.release_db_connection(conn)

        print("[HostelSync] Verified and synced 44 canonical parameters.")
        return True
    except Exception as e:
        print(f"[HostelSync] Error: {e}")
        return False

if __name__ == '__main__':
    ensure_and_seed_hostel_parameters()
