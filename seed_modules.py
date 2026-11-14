import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

def seed_segregated_data():
    print("Seeding/Verifying segregated data for Food, Hostel, and Transport...")

    # 1. Billing Periods
    hostel_periods = [
        ('2025-09', "Sept'25", '2025-09-01', '2025-09-30', 30),
        ('2025-10', "Oct'25", '2025-10-01', '2025-10-31', 31),
        ('2025-11', "Nov'25", '2025-11-01', '2025-11-30', 30),
        ('2025-12', "Dec'25", '2025-12-01', '2025-12-31', 31)
    ]
    h_pids = {}
    for code, label, sdate, edate, days in hostel_periods:
        sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, module)
        VALUES (1, %s, %s, %s, %s, %s, 'hostel')
        ON CONFLICT (module, period_code) DO UPDATE SET period_label = EXCLUDED.period_label
        RETURNING id;
        """
        row = db.execute_query(sql, (code, label, sdate, edate, days), fetch_all=False)
        h_pids[code] = row['id']

    transport_periods = [
        ('2026-06', "Jun'26", '2026-06-01', '2026-06-30', 30),
        ('2026-07', "Jul'26", '2026-07-01', '2026-07-31', 31),
        ('2026-08', "Aug'26", '2026-08-01', '2026-08-31', 31),
        ('2026-09', "Sept'26", '2026-09-01', '2026-09-30', 30)
    ]
    t_pids = {}
    for code, label, sdate, edate, days in transport_periods:
        sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, module)
        VALUES (1, %s, %s, %s, %s, %s, 'transport')
        ON CONFLICT (module, period_code) DO UPDATE SET period_label = EXCLUDED.period_label
        RETURNING id;
        """
        row = db.execute_query(sql, (code, label, sdate, edate, days), fetch_all=False)
        t_pids[code] = row['id']

    # 2. Expense Categories for Hostel
    hostel_cats = [
        ('CAT_HOSTEL_POWER', 'Hostel Power & Utilities', 1, 'hostel'),
        ('CAT_HOSTEL_WATER', 'Hostel Water Supply & RO', 2, 'hostel'),
        ('CAT_HOSTEL_MAINT', 'Hostel Facilities Maintenance', 3, 'hostel'),
        ('CAT_HOSTEL_OPS', 'Hostel Resident Operations', 4, 'hostel')
    ]
    h_cat_ids = {}
    for code, name, disp, mod in hostel_cats:
        sql = """
        INSERT INTO expense_categories (code, name, display_order, module)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, module = EXCLUDED.module
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, disp, mod), fetch_all=False)
        h_cat_ids[code] = row['id']

    # 3. Expense Categories for Transport
    transport_cats = [
        ('CAT_TRANS_FUEL', 'Transport Fuel & Tolls', 1, 'transport'),
        ('CAT_TRANS_MAINT', 'Fleet Maintenance & Spares', 2, 'transport'),
        ('CAT_TRANS_CREW', 'Transport Manpower & Crew', 3, 'transport'),
        ('CAT_TRANS_STAT', 'Statutory, Insurance & Compliance', 4, 'transport')
    ]
    t_cat_ids = {}
    for code, name, disp, mod in transport_cats:
        sql = """
        INSERT INTO expense_categories (code, name, display_order, module)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, module = EXCLUDED.module
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, disp, mod), fetch_all=False)
        t_cat_ids[code] = row['id']

    # 4. Cost Heads for Hostel
    hostel_heads = [
        ('HST_POWER_EBDG', 'Power consumption (EB + DG)', h_cat_ids['CAT_HOSTEL_POWER'], 'semi_variable', 1),
        ('HST_WATER_NORMAL', 'Normal Water Consumption Cost', h_cat_ids['CAT_HOSTEL_WATER'], 'variable', 2),
        ('HST_WATER_RO', 'Drinking RO Water Cost', h_cat_ids['CAT_HOSTEL_WATER'], 'variable', 3),
        ('HST_WATER_TANKER', 'Water Tanker Purchase Expenses', h_cat_ids['CAT_HOSTEL_WATER'], 'variable', 4),
        ('HST_MAINT_ROUTINE', 'Routine Hostel Maintenance Expenses', h_cat_ids['CAT_HOSTEL_MAINT'], 'semi_variable', 5),
        ('HST_OPS_RESIDENT', 'Hostel Resident Facility Operations', h_cat_ids['CAT_HOSTEL_OPS'], 'fixed', 6),
    ]
    h_ch_ids = {}
    for code, name, cat_id, behav, disp in hostel_heads:
        sql = """
        INSERT INTO cost_heads (code, name, category_id, cost_behavior, display_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category_id = EXCLUDED.category_id
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, cat_id, behav, disp), fetch_all=False)
        h_ch_ids[code] = row['id']

    # 5. Cost Heads for Transport
    transport_heads = [
        ('TRN_FUEL_DIESEL', 'Fuel expenses (Diesel)', t_cat_ids['CAT_TRANS_FUEL'], 'variable', 1),
        ('TRN_TOLL_PERMIT', 'Toll & Permit Charges', t_cat_ids['CAT_TRANS_FUEL'], 'semi_variable', 2),
        ('TRN_REPAIR_MAINT', 'Vehicle Repair & Maintenance', t_cat_ids['CAT_TRANS_MAINT'], 'semi_variable', 3),
        ('TRN_SPARES_TYRES', 'Spares, Tyres & Battery', t_cat_ids['CAT_TRANS_MAINT'], 'variable', 4),
        ('TRN_OTHER_OPS', 'Other Fleet Operations', t_cat_ids['CAT_TRANS_MAINT'], 'variable', 5),
        ('TRN_EMPLOYEE_COST', 'Transport Employees Cost', t_cat_ids['CAT_TRANS_CREW'], 'fixed', 6),
        ('TRN_CREW_ALLOWANCE', 'Driver & Crew Trip Allowances', t_cat_ids['CAT_TRANS_CREW'], 'variable', 7),
        ('TRN_STATUTORY_FC', 'Vehicle Statutory (FC 2025-2026)', t_cat_ids['CAT_TRANS_STAT'], 'fixed', 8),
        ('TRN_INSURANCE_TAX', 'Commercial Vehicle Insurance', t_cat_ids['CAT_TRANS_STAT'], 'fixed', 9),
    ]
    t_ch_ids = {}
    for code, name, cat_id, behav, disp in transport_heads:
        sql = """
        INSERT INTO cost_heads (code, name, category_id, cost_behavior, display_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category_id = EXCLUDED.category_id
        RETURNING id;
        """
        row = db.execute_query(sql, (code, name, cat_id, behav, disp), fetch_all=False)
        t_ch_ids[code] = row['id']

    # 6. Monthly Expense Entries for Hostel
    # Values aligned with hostel.xlsx
    hostel_matrix = {
        'HST_POWER_EBDG': {
            '2025-09': (1469211.00, 'EB: 94,600 units + DG: 10,516 units'),
            '2025-10': (1286531.00, 'EB: 82,100 units + DG: 8,266 units'),
            '2025-11': (1816706.24, 'EB: 122,000 units + DG: 15,747 units'),
            '2025-12': (1659230.00, 'EB: 110,400 units + DG: 15,022 units')
        },
        'HST_WATER_NORMAL': {
            '2025-09': (820200.00, '8.20M Litres consumed'),
            '2025-10': (887900.00, '8.88M Litres consumed'),
            '2025-11': (1201700.00, '12.02M Litres consumed'),
            '2025-12': (984900.00, '9.85M Litres consumed')
        },
        'HST_WATER_RO': {
            '2025-09': (23200.00, '92,800 Litres RO purified drinking water'),
            '2025-10': (21750.00, '87,000 Litres RO purified drinking water'),
            '2025-11': (32340.00, '129,360 Litres RO purified drinking water'),
            '2025-12': (20412.50, '81,650 Litres RO purified drinking water')
        },
        'HST_WATER_TANKER': {
            '2025-09': (248765.00, 'External tanker supply refill'),
            '2025-10': (230000.00, 'External tanker supply refill'),
            '2025-11': (260000.00, 'External tanker supply refill'),
            '2025-12': (248765.00, 'External tanker supply refill')
        },
        'HST_MAINT_ROUTINE': {
            '2025-09': (119394.00, 'Routine plumbing & electrical maintenance'),
            '2025-10': (142000.00, 'Routine plumbing & electrical maintenance'),
            '2025-11': (155000.00, 'Routine plumbing & electrical maintenance'),
            '2025-12': (168000.00, 'Routine plumbing & electrical maintenance')
        },
        'HST_OPS_RESIDENT': {
            '2025-09': (6668402.00, 'Hostel housekeeping & resident operational administration'),
            '2025-10': (6850000.00, 'Hostel housekeeping & resident operational administration'),
            '2025-11': (7200000.00, 'Hostel housekeeping & resident operational administration'),
            '2025-12': (7018692.50, 'Hostel housekeeping & resident operational administration')
        }
    }

    entry_sql = """
    INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, amount, remarks, status)
    VALUES (%s, %s, %s, %s, %s, 'draft')
    ON CONFLICT (module, period_id, cost_head_id) DO UPDATE SET
        amount = EXCLUDED.amount,
        remarks = EXCLUDED.remarks;
    """

    for ch_code, pdata in hostel_matrix.items():
        ch_id = h_ch_ids[ch_code]
        for pcode, (amt, rem) in pdata.items():
            pid = h_pids[pcode]
            db.execute_commit(entry_sql, ('hostel', pid, ch_id, amt, rem))

    # 7. Monthly Expense Entries for Transport
    # Values aligned with transport.xlsx
    transport_matrix = {
        'TRN_FUEL_DIESEL': {
            '2026-06': (465000.00, '4,950 L Diesel for 18+1 fleet'),
            '2026-07': (479000.00, '5,100 L Diesel for 18+1 fleet'),
            '2026-08': (483000.00, '5,150 L Diesel for 18+1 fleet'),
            '2026-09': (487375.00, '5,184.84 L Diesel purchase quantity')
        },
        'TRN_TOLL_PERMIT': {
            '2026-06': (35000.00, 'Highway FASTag tolls & special route permits'),
            '2026-07': (38000.00, 'Highway FASTag tolls & special route permits'),
            '2026-08': (40000.00, 'Highway FASTag tolls & special route permits'),
            '2026-09': (42500.00, 'Highway FASTag tolls & special route permits')
        },
        'TRN_REPAIR_MAINT': {
            '2026-06': (185000.00, 'Brake, clutch & regular mechanical repairs'),
            '2026-07': (210000.00, 'Brake, clutch & regular mechanical repairs'),
            '2026-08': (195000.00, 'Brake, clutch & regular mechanical repairs'),
            '2026-09': (215400.00, '38/38 service tickets resolved')
        },
        'TRN_SPARES_TYRES': {
            '2026-06': (95000.00, 'Periodic tyre retreading & lubricants'),
            '2026-07': (115000.00, 'Periodic tyre retreading & lubricants'),
            '2026-08': (88000.00, 'Periodic tyre retreading & lubricants'),
            '2026-09': (105000.00, 'Periodic tyre retreading & lubricants')
        },
        'TRN_OTHER_OPS': {
            '2026-06': (45000.00, 'Cleaning, washing & miscellaneous fleet consumables'),
            '2026-07': (52000.00, 'Cleaning, washing & miscellaneous fleet consumables'),
            '2026-08': (48000.00, 'Cleaning, washing & miscellaneous fleet consumables'),
            '2026-09': (58000.00, 'Cleaning, washing & miscellaneous fleet consumables')
        },
        'TRN_EMPLOYEE_COST': {
            '2026-06': (420000.00, 'Transport drivers & maintenance mechanics payroll'),
            '2026-07': (435000.00, 'Transport drivers & maintenance mechanics payroll'),
            '2026-08': (440000.00, 'Transport drivers & maintenance mechanics payroll'),
            '2026-09': (450000.00, 'Transport drivers & maintenance mechanics payroll')
        },
        'TRN_CREW_ALLOWANCE': {
            '2026-06': (65000.00, 'Late night & outstation trip driver allowances'),
            '2026-07': (72000.00, 'Late night & outstation trip driver allowances'),
            '2026-08': (70000.00, 'Late night & outstation trip driver allowances'),
            '2026-09': (78000.00, 'Late night & outstation trip driver allowances')
        },
        'TRN_STATUTORY_FC': {
            '2026-06': (95000.00, 'Vehicle FC 2025-2026 & RTO fitness tests'),
            '2026-07': (105000.00, 'Vehicle FC 2025-2026 & RTO fitness tests'),
            '2026-08': (90000.00, 'Vehicle FC 2025-2026 & RTO fitness tests'),
            '2026-09': (95000.00, 'Vehicle FC 2025-2026 & RTO fitness tests')
        },
        'TRN_INSURANCE_TAX': {
            '2026-06': (120000.00, 'Commercial comprehensive passenger liability insurance'),
            '2026-07': (125000.00, 'Commercial comprehensive passenger liability insurance'),
            '2026-08': (120000.00, 'Commercial comprehensive passenger liability insurance'),
            '2026-09': (130000.00, 'Commercial comprehensive passenger liability insurance')
        }
    }

    for ch_code, pdata in transport_matrix.items():
        ch_id = t_ch_ids[ch_code]
        for pcode, (amt, rem) in pdata.items():
            pid = t_pids[pcode]
            db.execute_commit(entry_sql, ('transport', pid, ch_id, amt, rem))

    print("Segregated data seeded successfully for all 3 modules!")

if __name__ == "__main__":
    seed_segregated_data()
