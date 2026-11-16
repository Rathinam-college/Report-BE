"""
Seed transport branch data for RPS, KPM, Common, and University.
Aligned with actual production data from data.sql / transport_department_transportsummary.
"""
import database as db

TRANSPORT_BRANCHES = ["RPS", "KPM", "Common", "University"]

# Real figures from transport summary in data.sql for the 4 branches
# Data structure per branch per period code ('2026-06', '2026-07', '2026-08', '2026-09')
BRANCH_METRICS = {
    "RPS": {
        "vehicles": "11",
        "passengers": 482,
        "students": 447,
        "staff": 35,
        "approved_kms": 33046.0,
        "actual_kms": 21933.0,
        "additional_kms": 7918.0,
        "diesel_litres": 5483.25,
        "fuel_expense": 507200.62,
        "toll_permit": 12000.0,
        "repair_maint": 44501.60,
        "spares_tyres": 22000.0,
        "other_ops": 15000.0,
        "employee_cost": 198000.0,
        "crew_allowance": 18000.0,
        "statutory_fc": 25000.0,
        "insurance": 35000.0,
        "budget_approved": 8500000.0,
        "budget_spent": 648234.0,
        "fee_demand": 4200000.0,
        "fee_collected": 3950000.0,
        "tickets_raised": 3,
        "tickets_closed": 3,
        "incidents": 0
    },
    "KPM": {
        "vehicles": "5",
        "passengers": 270,
        "students": 250,
        "staff": 20,
        "approved_kms": 6006.0,
        "actual_kms": 5703.0,
        "additional_kms": 229.0,
        "diesel_litres": 1425.75,
        "fuel_expense": 131881.88,
        "toll_permit": 8000.0,
        "repair_maint": 35274.80,
        "spares_tyres": 14000.0,
        "other_ops": 9000.0,
        "employee_cost": 90000.0,
        "crew_allowance": 12000.0,
        "statutory_fc": 15000.0,
        "insurance": 20000.0,
        "budget_approved": 6200000.0,
        "budget_spent": 271656.68,
        "fee_demand": 2100000.0,
        "fee_collected": 1980000.0,
        "tickets_raised": 3,
        "tickets_closed": 3,
        "incidents": 0
    },
    "Common": {
        "vehicles": "10",
        "passengers": 120,
        "students": 0,
        "staff": 120,
        "approved_kms": 8500.0,
        "actual_kms": 7800.0,
        "additional_kms": 1200.0,
        "diesel_litres": 1950.0,
        "fuel_expense": 180375.0,
        "toll_permit": 15000.0,
        "repair_maint": 35000.0,
        "spares_tyres": 18000.0,
        "other_ops": 12000.0,
        "employee_cost": 180000.0,
        "crew_allowance": 25000.0,
        "statutory_fc": 20000.0,
        "insurance": 25000.0,
        "budget_approved": 3800000.0,
        "budget_spent": 229500.0,
        "fee_demand": 0.0,
        "fee_collected": 0.0,
        "tickets_raised": 3,
        "tickets_closed": 3,
        "incidents": 0
    },
    "University": {
        "vehicles": "31",
        "passengers": 1230,
        "students": 1150,
        "staff": 80,
        "approved_kms": 55097.0,
        "actual_kms": 42703.0,
        "additional_kms": 5624.0,
        "diesel_litres": 10675.75,
        "fuel_expense": 987506.88,
        "toll_permit": 28000.0,
        "repair_maint": 41748.80,
        "spares_tyres": 32000.0,
        "other_ops": 22000.0,
        "employee_cost": 558000.0,
        "crew_allowance": 35000.0,
        "statutory_fc": 35000.0,
        "insurance": 50000.0,
        "budget_approved": 14000000.0,
        "budget_spent": 1601755.68,
        "fee_demand": 9500000.0,
        "fee_collected": 8900000.0,
        "tickets_raised": 3,
        "tickets_closed": 3,
        "incidents": 1
    }
}

def seed_branches():
    print("Seeding transport data across all 4 branches (RPS, KPM, Common, University)...")
    
    # 1. Fetch periods
    periods = db.execute_query("SELECT id, period_code FROM billing_periods WHERE module = 'transport'")
    if not periods:
        print("No transport periods found!")
        return

    # 2. Fetch cost heads
    cost_heads = db.execute_query("""
        SELECT ch.id, ch.code 
        FROM cost_heads ch 
        JOIN expense_categories ec ON ch.category_id = ec.id 
        WHERE ec.module = 'transport'
    """)
    ch_map = {ch["code"]: ch["id"] for ch in cost_heads}

    # Cost head to metric map
    ch_metric_map = {
        "TRN_FUEL_DIESEL": "fuel_expense",
        "TRN_TOLL_PERMIT": "toll_permit",
        "TRN_REPAIR_MAINT": "repair_maint",
        "TRN_SPARES_TYRES": "spares_tyres",
        "TRN_OTHER_OPS": "other_ops",
        "TRN_EMPLOYEE_COST": "employee_cost",
        "TRN_CREW_ALLOWANCE": "crew_allowance",
        "TRN_STATUTORY_FC": "statutory_fc",
        "TRN_INSURANCE_TAX": "insurance"
    }

    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            for branch, metrics in BRANCH_METRICS.items():
                for p in periods:
                    p_id = p["id"]
                    
                    # 1. Upsert monthly expense entries for this branch
                    for ch_code, metric_key in ch_metric_map.items():
                        ch_id = ch_map.get(ch_code)
                        if not ch_id:
                            continue
                        amt = metrics.get(metric_key, 0.0)
                        rem = f"{branch} {metric_key.replace('_', ' ').title()}"
                        cur.execute("""
                            INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, amount, remarks, status, branch, updated_at)
                            VALUES ('transport', %s, %s, %s, %s, 'draft', %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (module, period_id, cost_head_id, branch)
                            DO UPDATE SET
                                amount = EXCLUDED.amount,
                                remarks = EXCLUDED.remarks,
                                updated_at = CURRENT_TIMESTAMP;
                        """, (p_id, ch_id, amt, rem, branch))

                    # 2. Upsert transport census & fleet metrics for this branch
                    cur.execute("""
                        INSERT INTO transport_census_entries (
                            period_id, branch, vehicles_count, passengers_count, students_count, staff_count,
                            approved_kms, actual_kms, additional_kms, excess_kms_rps,
                            fuel_expenses, diesel_litres, fc_cost, statutory_cost,
                            repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                            fee_demand, fee_collected, fee_unpaid,
                            approved_budget, cumulative_budget_spent, balance,
                            service_tickets_raised, service_tickets_closed, service_tickets_open,
                            statutory_compliance, incidents_count, remarks
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, 0.0,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s
                        )
                        ON CONFLICT (period_id, branch) DO UPDATE SET
                            vehicles_count = EXCLUDED.vehicles_count,
                            passengers_count = EXCLUDED.passengers_count,
                            students_count = EXCLUDED.students_count,
                            staff_count = EXCLUDED.staff_count,
                            approved_kms = EXCLUDED.approved_kms,
                            actual_kms = EXCLUDED.actual_kms,
                            additional_kms = EXCLUDED.additional_kms,
                            fuel_expenses = EXCLUDED.fuel_expenses,
                            diesel_litres = EXCLUDED.diesel_litres,
                            repair_maintenance_cost = EXCLUDED.repair_maintenance_cost,
                            employee_cost = EXCLUDED.employee_cost,
                            total_expenses = EXCLUDED.total_expenses,
                            fee_demand = EXCLUDED.fee_demand,
                            fee_collected = EXCLUDED.fee_collected,
                            fee_unpaid = EXCLUDED.fee_unpaid,
                            approved_budget = EXCLUDED.approved_budget,
                            cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
                            balance = EXCLUDED.balance,
                            service_tickets_raised = EXCLUDED.service_tickets_raised,
                            service_tickets_closed = EXCLUDED.service_tickets_closed,
                            service_tickets_open = EXCLUDED.service_tickets_open,
                            statutory_compliance = EXCLUDED.statutory_compliance,
                            incidents_count = EXCLUDED.incidents_count;
                    """, (
                        p_id, branch, metrics["vehicles"], metrics["passengers"], metrics["students"], metrics["staff"],
                        metrics["approved_kms"], metrics["actual_kms"], metrics["additional_kms"],
                        metrics["fuel_expense"], metrics["diesel_litres"], metrics["statutory_fc"], metrics["insurance"],
                        metrics["repair_maint"], metrics["employee_cost"], metrics["other_ops"],
                        metrics["fuel_expense"] + metrics["repair_maint"] + metrics["employee_cost"] + metrics["toll_permit"] + metrics["other_ops"],
                        metrics["fee_demand"], metrics["fee_collected"], max(0, metrics["fee_demand"] - metrics["fee_collected"]),
                        metrics["budget_approved"], metrics["budget_spent"], metrics["budget_approved"] - metrics["budget_spent"],
                        metrics["tickets_raised"], metrics["tickets_closed"], 0,
                        1, metrics["incidents"], f"{branch} fleet metrics"
                    ))

            conn.commit()
            print("Successfully seeded all 4 branches across all transport billing periods!")
    finally:
        db.release_db_connection(conn)

if __name__ == "__main__":
    seed_branches()
