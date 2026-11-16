import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

# Complete 13-month dataset from Image 1 & hostel.xlsx:
# (period_code, period_label, sdate, edate, days, bed_cap, students, staff, total_occ, vacant, vac_college, vac_sports, vac_school, occ_pct, vac_pct)
DATA_13_MONTHS = [
    ('2025-09', "Sep 1st to 30th", '2025-09-01', '2025-09-30', 30, 3119, 2843, 131, 2974, 145, 104, 0, 0, 95.35, 4.65, 105116, 1469211.0, 248765.0, 8202000, 820200.0, 92800, 23200.0, 119394.0, 9349172.0, 131788118.0, 34527814.0),
    ('2025-10', "Oct 1st to 31st", '2025-10-01', '2025-10-31', 31, 3253, 2959, 135, 3094, 159, 118, 0, 0, 95.11, 4.89, 90366, 1286531.0, 230000.0, 8879000, 887900.0, 87000, 21750.0, 142000.0, 9349172.0, 131788118.0, 42000000.0),
    ('2025-11', "Nov 1st to 30th", '2025-11-01', '2025-11-30', 30, 3253, 2940, 138, 3079, 154, 113, 0, 0, 94.65, 5.35, 137747, 1816706.24, 260000.0, 12017000, 1201700.0, 129360, 32340.0, 155000.0, 9349172.0, 131788118.0, 51000000.0),
    ('2025-12', "Dec 1st to 31st", '2025-12-01', '2025-12-31', 31, 3253, 2902, 137, 3039, 194, 153, 0, 0, 93.42, 6.58, 125422, 1659230.0, 248765.0, 9849000, 984900.0, 81650, 20412.5, 168000.0, 9349172.0, 131788118.0, 61000000.0),
    ('2026-01', "Jan 1st to 31st", '2026-01-01', '2026-01-31', 31, 3245, 2851, 139, 2990, 255, 214, 0, 0, 92.14, 7.86, 112000, 1485000.0, 240000.0, 9150000, 915000.0, 89000, 22250.0, 135000.0, 9150000.0, 131788118.0, 70000000.0),
    ('2026-02', "Feb 1st to 28th", '2026-02-01', '2026-02-28', 28, 3239, 2810, 139, 2949, 284, 243, 0, 0, 91.05, 8.95, 108500, 1438000.0, 235000.0, 8850000, 885000.0, 86000, 21500.0, 130000.0, 9020000.0, 131788118.0, 79000000.0),
    ('2026-03', "March 1st to 31st", '2026-03-01', '2026-03-31', 31, 3239, 2763, 146, 2909, 330, 289, 0, 0, 89.81, 10.19, 115000, 1520000.0, 250000.0, 9300000, 930000.0, 91000, 22750.0, 145000.0, 9200000.0, 131788118.0, 88000000.0),
    ('2026-04', "Apr 1st to 30th", '2026-04-01', '2026-04-30', 30, 3239, 2709, 157, 2866, 373, 332, 0, 0, 88.48, 11.52, 118000, 1560000.0, 255000.0, 9450000, 945000.0, 92500, 23125.0, 150000.0, 9350000.0, 131788118.0, 97000000.0),
    ('2026-05', "May 1st to 31st", '2026-05-01', '2026-05-31', 31, 3239, 2252, 154, 2406, 833, 792, 0, 0, 74.28, 25.72, 85000, 1125000.0, 190000.0, 6800000, 680000.0, 66000, 16500.0, 110000.0, 7650000.0, 131788118.0, 104500000.0),
    ('2026-06', "Jun 1st to 30th", '2026-06-01', '2026-06-30', 30, 3335, 2009, 169, 2178, 1163, 1122, 0, 0, 65.31, 34.69, 78000, 1030000.0, 175000.0, 6200000, 620000.0, 60000, 15000.0, 105000.0, 7200000.0, 131788118.0, 111500000.0),
    ('2026-07', "Jul 1st to 31st", '2026-07-01', '2026-07-31', 31, 3399, 2728, 170, 2898, 478, 432, 0, 8, 85.26, 14.74, 110000, 1450000.0, 245000.0, 8900000, 890000.0, 88000, 22000.0, 140000.0, 9100000.0, 131788118.0, 120500000.0),
    ('2026-08', "Aug 1st to 31st", '2026-08-01', '2026-08-31', 31, 3377, 2744, 187, 2931, 446, 400, 0, 8, 86.79, 13.21, 114000, 1510000.0, 250000.0, 9200000, 920000.0, 90000, 22500.0, 145000.0, 9280000.0, 131788118.0, 129500000.0),
    ('2026-09', "Sep 1st to 30th", '2026-09-01', '2026-09-30', 30, 4283, 3897, 191, 4088, 195, 182, 15, 8, 95.45, 4.55, 148000, 1950000.0, 310000.0, 12800000, 1280000.0, 125000, 31250.0, 185000.0, 11800000.0, 131788118.0, 141300000.0)
]

def seed_hostel_13months():
    print("Seeding complete 13-month dataset for Hostel matching Excel Image 1...")

    # Ensure categories exist
    hostel_cats = [
        ('CAT_HOSTEL_POWER', 'Hostel Power & Utilities', 1, 'hostel'),
        ('CAT_HOSTEL_WATER', 'Hostel Water Supply & RO', 2, 'hostel'),
        ('CAT_HOSTEL_MAINT', 'Hostel Facilities Maintenance', 3, 'hostel'),
        ('CAT_HOSTEL_OPS', 'Hostel Resident Operations', 4, 'hostel')
    ]
    cat_ids = {}
    for code, name, disp, mod in hostel_cats:
        sql = """
        INSERT INTO expense_categories (code, name, display_order, module)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, module = EXCLUDED.module
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, disp, mod), fetch_all=False)
        cat_ids[code] = row['id']

    # Cost Heads
    hostel_heads = [
        ('HST_POWER_EBDG', 'Power consumption (EB + DG)', cat_ids['CAT_HOSTEL_POWER'], 'semi_variable', 1),
        ('HST_WATER_NORMAL', 'Normal Water Consumption Cost', cat_ids['CAT_HOSTEL_WATER'], 'variable', 2),
        ('HST_WATER_RO', 'Drinking RO Water Cost', cat_ids['CAT_HOSTEL_WATER'], 'variable', 3),
        ('HST_WATER_TANKER', 'Water Tanker Purchase Expenses', cat_ids['CAT_HOSTEL_WATER'], 'variable', 4),
        ('HST_MAINT_ROUTINE', 'Routine Hostel Maintenance Expenses', cat_ids['CAT_HOSTEL_MAINT'], 'semi_variable', 5),
        ('HST_OPS_RESIDENT', 'Hostel Resident Facility Operations', cat_ids['CAT_HOSTEL_OPS'], 'fixed', 6),
    ]
    ch_ids = {}
    for code, name, cat_id, behav, disp in hostel_heads:
        sql = """
        INSERT INTO cost_heads (code, name, category_id, cost_behavior, display_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category_id = EXCLUDED.category_id
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, cat_id, behav, disp), fetch_all=False)
        ch_ids[code] = row['id']

    # Remove test period 277 if present
    try:
        db.execute_commit("DELETE FROM hostel_census_entries WHERE period_id = 277;")
        db.execute_commit("DELETE FROM monthly_expense_entries WHERE period_id = 277 AND module = 'hostel';")
        db.execute_commit("DELETE FROM billing_periods WHERE id = 277 AND module = 'hostel';")
    except Exception as e:
        print(f"Notice on 277 cleanup: {e}")

    # Insert / update 13 billing periods
    p_ids = {}
    for item in DATA_13_MONTHS:
        pcode, plabel, sdate, edate, days = item[0], item[1], item[2], item[3], item[4]
        sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, module)
        VALUES (1, %s, %s, %s, %s, %s, 'hostel')
        ON CONFLICT (module, period_code) DO UPDATE SET
            period_label = EXCLUDED.period_label,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            operating_days = EXCLUDED.operating_days
        RETURNING id;
        """
        row = db.execute_query(sql, (pcode, plabel, sdate, edate, days), fetch_all=False)
        p_ids[pcode] = row['id']
        print(f"  [Period OK] {pcode} ({plabel}) -> id {row['id']}")

    # Insert / update 13 hostel_census_entries
    census_sql = """
    INSERT INTO hostel_census_entries (
        period_id, bed_capacity_total, students_total, staff_total, total_occupied,
        vacant_total, vacant_college, vacant_sports_total, vacant_school_total,
        occupied_pct, vacant_pct, power_units, power_cost, water_purchase_cost,
        normal_water_litres, normal_water_cost, drinking_water_litres, drinking_water_cost,
        maintenance_expenses, expenses_occurred, approved_budget, cumulative_budget_spent,
        balance, per_student_cost_month, per_student_cost_day, sq_feet, sq_feet_per_occupant,
        power_cost_sqft, units_per_occupant, power_cost_occupant, normal_water_ltr_day,
        normal_water_cost_day, drinking_water_ltr_day, drinking_water_cost_day
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s
    )
    ON CONFLICT (period_id) DO UPDATE SET
        bed_capacity_total = EXCLUDED.bed_capacity_total,
        students_total = EXCLUDED.students_total,
        staff_total = EXCLUDED.staff_total,
        total_occupied = EXCLUDED.total_occupied,
        vacant_total = EXCLUDED.vacant_total,
        vacant_college = EXCLUDED.vacant_college,
        vacant_sports_total = EXCLUDED.vacant_sports_total,
        vacant_school_total = EXCLUDED.vacant_school_total,
        occupied_pct = EXCLUDED.occupied_pct,
        vacant_pct = EXCLUDED.vacant_pct,
        power_units = EXCLUDED.power_units,
        power_cost = EXCLUDED.power_cost,
        water_purchase_cost = EXCLUDED.water_purchase_cost,
        normal_water_litres = EXCLUDED.normal_water_litres,
        normal_water_cost = EXCLUDED.normal_water_cost,
        drinking_water_litres = EXCLUDED.drinking_water_litres,
        drinking_water_cost = EXCLUDED.drinking_water_cost,
        maintenance_expenses = EXCLUDED.maintenance_expenses,
        expenses_occurred = EXCLUDED.expenses_occurred,
        approved_budget = EXCLUDED.approved_budget,
        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
        balance = EXCLUDED.balance,
        per_student_cost_month = EXCLUDED.per_student_cost_month,
        per_student_cost_day = EXCLUDED.per_student_cost_day,
        sq_feet = EXCLUDED.sq_feet,
        sq_feet_per_occupant = EXCLUDED.sq_feet_per_occupant,
        power_cost_sqft = EXCLUDED.power_cost_sqft,
        units_per_occupant = EXCLUDED.units_per_occupant,
        power_cost_occupant = EXCLUDED.power_cost_occupant,
        normal_water_ltr_day = EXCLUDED.normal_water_ltr_day,
        normal_water_cost_day = EXCLUDED.normal_water_cost_day,
        drinking_water_ltr_day = EXCLUDED.drinking_water_ltr_day,
        drinking_water_cost_day = EXCLUDED.drinking_water_cost_day;
    """

    for item in DATA_13_MONTHS:
        pcode = item[0]
        pid = p_ids[pcode]
        bed_cap = item[5]
        students = item[6]
        staff = item[7]
        tot_occ = item[8]
        vac = item[9]
        vac_col = item[10]
        vac_sports = item[11]
        vac_school = item[12]
        occ_pct = item[13]
        vac_pct = item[14]
        pwr_units = item[15]
        pwr_cost = item[16]
        water_purch = item[17]
        norm_wat_lit = item[18]
        norm_wat_cost = item[19]
        drk_wat_lit = item[20]
        drk_wat_cost = item[21]
        maint_exp = item[22]
        exp_occurred = item[23]
        appr_budget = item[24]
        cum_spent = item[25]
        balance = appr_budget - cum_spent
        per_stud_month = round(exp_occurred / students, 2) if students > 0 else 0
        per_stud_day = round(per_stud_month / 30, 2)
        sqft = 231701.0
        sqft_occupant = round(sqft / tot_occ, 2) if tot_occ > 0 else 0
        pwr_sqft = round(pwr_cost / sqft, 2)
        units_occupant = round(pwr_units / tot_occ, 2) if tot_occ > 0 else 0
        pwr_cost_occupant = round(pwr_cost / tot_occ, 2) if tot_occ > 0 else 0
        norm_wat_ltr_day = round(norm_wat_lit / (students * 30), 2) if students > 0 else 0
        norm_wat_cost_day = round(norm_wat_cost / (students * 30), 2) if students > 0 else 0
        drk_wat_ltr_day = round(drk_wat_lit / (students * 30), 2) if students > 0 else 0
        drk_wat_cost_day = round(drk_wat_cost / (students * 30), 2) if students > 0 else 0

        params = (
            pid, bed_cap, students, staff, tot_occ,
            vac, vac_col, vac_sports, vac_school,
            occ_pct, vac_pct, pwr_units, pwr_cost, water_purch,
            norm_wat_lit, norm_wat_cost, drk_wat_lit, drk_wat_cost,
            maint_exp, exp_occurred, appr_budget, cum_spent,
            balance, per_stud_month, per_stud_day, sqft, sqft_occupant,
            pwr_sqft, units_occupant, pwr_cost_occupant, norm_wat_ltr_day,
            norm_wat_cost_day, drk_wat_ltr_day, drk_wat_cost_day
        )
        db.execute_commit(census_sql, params)
        print(f"  [Census OK] {pcode}: Beds={bed_cap}, Occ={tot_occ}, PwrCost={pwr_cost}")

    # Seed monthly expense entries for all 6 cost heads
    entry_sql = """
    INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, amount, remarks, status, branch)
    VALUES (%s, %s, %s, %s, %s, 'draft', 'Common')
    ON CONFLICT (module, period_id, cost_head_id, branch) DO UPDATE SET
        amount = EXCLUDED.amount,
        remarks = EXCLUDED.remarks;
    """

    for item in DATA_13_MONTHS:
        pcode = item[0]
        pid = p_ids[pcode]
        pwr_units = item[15]
        pwr_cost = item[16]
        water_purch = item[17]
        norm_wat_lit = item[18]
        norm_wat_cost = item[19]
        drk_wat_lit = item[20]
        drk_wat_cost = item[21]
        maint_exp = item[22]
        exp_occurred = item[23]

        # Calculate resident ops as the balance to match total operational expenses
        ops_cost = max(0.0, exp_occurred - (pwr_cost + norm_wat_cost + drk_wat_cost + water_purch + maint_exp))

        entries_to_add = [
            (ch_ids['HST_POWER_EBDG'], pwr_cost, f"Hostel EB & DG ({pwr_units:,} units)"),
            (ch_ids['HST_WATER_NORMAL'], norm_wat_cost, f"Normal water ({norm_wat_lit:,} L)"),
            (ch_ids['HST_WATER_RO'], drk_wat_cost, f"Drinking RO water ({drk_wat_lit:,} L)"),
            (ch_ids['HST_WATER_TANKER'], water_purch, f"Tanker water purchase"),
            (ch_ids['HST_MAINT_ROUTINE'], maint_exp, f"Routine hostel maintenance"),
            (ch_ids['HST_OPS_RESIDENT'], ops_cost, f"Hostel resident facility operations")
        ]

        for ch_id, amt, rem in entries_to_add:
            db.execute_commit(entry_sql, ('hostel', pid, ch_id, amt, rem))

    print("All 13 months seeded successfully into PostgreSQL!")

if __name__ == "__main__":
    seed_hostel_13months()
