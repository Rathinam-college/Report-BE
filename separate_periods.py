import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

def setup_separate_periods():
    # 1. Update schema
    db.execute_commit("ALTER TABLE billing_periods ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';")
    db.execute_commit("ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS billing_periods_period_code_key;")
    db.execute_commit("ALTER TABLE billing_periods DROP CONSTRAINT IF EXISTS uq_billing_periods_module_code;")
    db.execute_commit("ALTER TABLE billing_periods ADD CONSTRAINT uq_billing_periods_module_code UNIQUE (module, period_code);")
    db.execute_commit("CREATE INDEX IF NOT EXISTS idx_billing_periods_module_date ON billing_periods (module, start_date);")

    # Ensure food periods are labeled as food
    db.execute_commit("UPDATE billing_periods SET module = 'food' WHERE module IS NULL OR module = '';")

    # 2. Setup separate Hostel periods (from hostel.xlsx Sept'25, Oct'25, Nov'25, Dec'25)
    hostel_periods = [
        ('2025-09', "Sept'25", '2025-09-01', '2025-09-30', 30),
        ('2025-10', "Oct'25", '2025-10-01', '2025-10-31', 31),
        ('2025-11', "Nov'25", '2025-11-01', '2025-11-30', 30),
        ('2025-12', "Dec'25", '2025-12-01', '2025-12-31', 31)
    ]
    hostel_pids = {}
    for code, label, sdate, edate, days in hostel_periods:
        sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, module)
        VALUES (1, %s, %s, %s, %s, %s, 'hostel')
        ON CONFLICT (module, period_code) DO UPDATE SET period_label = EXCLUDED.period_label
        RETURNING id;
        """
        row = db.execute_query(sql, (code, label, sdate, edate, days), fetch_all=False)
        hostel_pids[code] = row['id']

    # 3. Setup separate Transport periods (Jun'26, Jul'26, Aug'26, Sept'26)
    transport_periods = [
        ('2026-06', "Jun'26", '2026-06-01', '2026-06-30', 30),
        ('2026-07', "Jul'26", '2026-07-01', '2026-07-31', 31),
        ('2026-08', "Aug'26", '2026-08-01', '2026-08-31', 31),
        ('2026-09', "Sept'26", '2026-09-01', '2026-09-30', 30)
    ]
    transport_pids = {}
    for code, label, sdate, edate, days in transport_periods:
        sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, module)
        VALUES (1, %s, %s, %s, %s, %s, 'transport')
        ON CONFLICT (module, period_code) DO UPDATE SET period_label = EXCLUDED.period_label
        RETURNING id;
        """
        row = db.execute_query(sql, (code, label, sdate, edate, days), fetch_all=False)
        transport_pids[code] = row['id']

    # 4. Populate hostel_census_entries for the hostel periods
    hostel_data = {
        hostel_pids['2025-09']: (2223, 896, 3119, 2075, 768, 2843, 72, 59, 131, 2974, 145, 104, 95.35, 4.65, 0, 176, 176, 0, 62.29, 5, 3, 2, 0, 105116, 1469211, 248765, 8202000, 820200, 92800, 23200, 231701, 131788118, 34527814),
        hostel_pids['2025-10']: (2223, 896, 3119, 2160, 803, 2963, 72, 59, 131, 3094, 25, 20, 99.20, 0.80, 0, 160, 160, 0, 58.40, 4, 4, 0, 0, 90366, 1286531, 230000, 8879000, 887900, 87000, 21750, 231701, 131788118, 42000000),
        hostel_pids['2025-11']: (2223, 896, 3119, 2150, 798, 2948, 72, 59, 131, 3079, 40, 30, 98.72, 1.28, 0, 182, 180, 2, 65.10, 6, 5, 1, 0, 137747, 1816706, 260000, 12017000, 1201700, 129360, 32340, 231701, 131788118, 51000000),
        hostel_pids['2025-12']: (2223, 896, 3119, 2120, 788, 2908, 72, 59, 131, 3039, 80, 60, 97.43, 2.57, 0, 176, 176, 0, 62.29, 5, 3, 2, 0, 125422, 1659230, 248765, 9849000, 984900, 81650, 20412.5, 231701, 131788118, 61000000)
    }
    h_sql = """
    INSERT INTO hostel_census_entries (
        period_id, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
        students_boys, students_girls, students_total, staff_boys, staff_girls, staff_total,
        total_occupied, vacant_total, vacant_college, occupied_pct, vacant_pct, students_vacated,
        tickets_received, tickets_closed, tickets_open, tat_hours, quality_issues_received,
        quality_issues_closed, quality_issues_open, incidents_count, power_units, power_cost,
        water_purchase_cost, normal_water_litres, normal_water_cost, drinking_water_litres,
        drinking_water_cost, sq_feet, approved_budget, cumulative_budget_spent
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (period_id) DO UPDATE SET
        bed_capacity_boys = EXCLUDED.bed_capacity_boys,
        bed_capacity_girls = EXCLUDED.bed_capacity_girls,
        bed_capacity_total = EXCLUDED.bed_capacity_total,
        students_boys = EXCLUDED.students_boys,
        students_girls = EXCLUDED.students_girls,
        students_total = EXCLUDED.students_total,
        staff_boys = EXCLUDED.staff_boys,
        staff_girls = EXCLUDED.staff_girls,
        staff_total = EXCLUDED.staff_total,
        total_occupied = EXCLUDED.total_occupied,
        vacant_total = EXCLUDED.vacant_total,
        vacant_college = EXCLUDED.vacant_college,
        occupied_pct = EXCLUDED.occupied_pct,
        vacant_pct = EXCLUDED.vacant_pct,
        students_vacated = EXCLUDED.students_vacated,
        tickets_received = EXCLUDED.tickets_received,
        tickets_closed = EXCLUDED.tickets_closed,
        tickets_open = EXCLUDED.tickets_open,
        tat_hours = EXCLUDED.tat_hours,
        quality_issues_received = EXCLUDED.quality_issues_received,
        quality_issues_closed = EXCLUDED.quality_issues_closed,
        quality_issues_open = EXCLUDED.quality_issues_open,
        incidents_count = EXCLUDED.incidents_count,
        power_units = EXCLUDED.power_units,
        power_cost = EXCLUDED.power_cost,
        water_purchase_cost = EXCLUDED.water_purchase_cost,
        normal_water_litres = EXCLUDED.normal_water_litres,
        normal_water_cost = EXCLUDED.normal_water_cost,
        drinking_water_litres = EXCLUDED.drinking_water_litres,
        drinking_water_cost = EXCLUDED.drinking_water_cost,
        sq_feet = EXCLUDED.sq_feet,
        approved_budget = EXCLUDED.approved_budget,
        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent;
    """
    for pid, vals in hostel_data.items():
        db.execute_commit(h_sql, (pid, *vals))

    # 5. Populate transport_census_entries for the transport periods
    transport_data = {
        transport_pids['2026-06']: ('18+1', 447, 412, 35, 25000, 24500, 2100, 4950.00, 465000, 32, 32, 0, 0, 0, 0, 1, 0, 13730137.73, 2450000),
        transport_pids['2026-07']: ('18+1', 447, 412, 35, 26000, 25200, 2300, 5100.00, 479000, 35, 35, 0, 0, 0, 0, 1, 0, 13730137.73, 3800000),
        transport_pids['2026-08']: ('18+1', 447, 412, 35, 26500, 25600, 2400, 5150.00, 483000, 40, 39, 1, 0, 0, 0, 1, 1, 13730137.73, 5200000),
        transport_pids['2026-09']: ('18+1', 447, 412, 35, 26691, 25777, 2481, 5184.84, 487375, 38, 38, 0, 0, 0, 0, 1, 1, 13730137.73, 6600000)
    }
    t_sql = """
    INSERT INTO transport_census_entries (
        period_id, vehicles_count, passengers_count, students_count, staff_count,
        approved_kms, actual_kms, additional_kms, diesel_litres, fuel_expenses,
        service_tickets_raised, service_tickets_closed, service_tickets_open,
        quality_issues_received, quality_issues_closed, quality_issues_open,
        statutory_compliance, incidents_count, approved_budget, cumulative_budget_spent
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (period_id) DO UPDATE SET
        vehicles_count = EXCLUDED.vehicles_count,
        passengers_count = EXCLUDED.passengers_count,
        students_count = EXCLUDED.students_count,
        staff_count = EXCLUDED.staff_count,
        approved_kms = EXCLUDED.approved_kms,
        actual_kms = EXCLUDED.actual_kms,
        additional_kms = EXCLUDED.additional_kms,
        diesel_litres = EXCLUDED.diesel_litres,
        fuel_expenses = EXCLUDED.fuel_expenses,
        service_tickets_raised = EXCLUDED.service_tickets_raised,
        service_tickets_closed = EXCLUDED.service_tickets_closed,
        service_tickets_open = EXCLUDED.service_tickets_open,
        quality_issues_received = EXCLUDED.quality_issues_received,
        quality_issues_closed = EXCLUDED.quality_issues_closed,
        quality_issues_open = EXCLUDED.quality_issues_open,
        statutory_compliance = EXCLUDED.statutory_compliance,
        incidents_count = EXCLUDED.incidents_count,
        approved_budget = EXCLUDED.approved_budget,
        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent;
    """
    for pid, vals in transport_data.items():
        db.execute_commit(t_sql, (pid, *vals))

    # Clean up any leftover entries from periods 12, 14, 18, 19 in hostel/transport census if they were tied to food periods
    food_pids = [12, 14, 18, 19]
    for fp in food_pids:
        db.execute_commit("DELETE FROM hostel_census_entries WHERE period_id = %s;", (fp,))
        db.execute_commit("DELETE FROM transport_census_entries WHERE period_id = %s;", (fp,))

    print("Setup completed successfully!")
    print("Hostel Periods:", hostel_pids)
    print("Transport Periods:", transport_pids)

if __name__ == "__main__":
    setup_separate_periods()
