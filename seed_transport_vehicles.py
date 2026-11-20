import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

KPM_FLEET_VEHICLES = [
    {"vehicle_no": "TN 99 E 5395", "make": "ASHOK LEYAND LTD", "model": "May-16", "display_order": 1},
    {"vehicle_no": "TN 99 L 4791", "make": "ASHOK LEYAND LTD", "model": "Mar-18", "display_order": 2},
    {"vehicle_no": "TN 99 W 7827", "make": "EICHER", "model": "Apr-22", "display_order": 3},
    {"vehicle_no": "TN 99 X 0086", "make": "EICHER", "model": "Jul-22", "display_order": 4},
    {"vehicle_no": "TN 99 W 6511", "make": "EICHER", "model": "May-22", "display_order": 5}
]

def ensure_and_seed_transport_vehicles():
    """
    Ensures the official KPM fleet vehicles (and future branch fleets) are seeded
    in transport_vehicle_entries for all transport billing periods on any environment (local or live DB).
    """
    try:
        # Check transport billing periods
        periods = db.execute_query(
            "SELECT id, period_code FROM billing_periods WHERE module = 'transport' ORDER BY id;"
        )
        if not periods:
            return

        for p in periods:
            pid = p["id"]
            # Check existing vehicles for KPM
            existing = db.execute_query(
                "SELECT vehicle_no FROM transport_vehicle_entries WHERE period_id = %s AND branch = 'KPM';",
                (pid,)
            )
            existing_nos = {r["vehicle_no"].strip().upper() for r in (existing or [])}

            for v in KPM_FLEET_VEHICLES:
                if v["vehicle_no"].strip().upper() not in existing_nos:
                    db.execute_commit(
                        """
                        INSERT INTO transport_vehicle_entries (
                            period_id, branch, vehicle_no, make, model,
                            fuel_expenses, fc_cost, statutory_cost, repair_maintenance,
                            parking_fastag, employee_cost, other_cost, total_expenses,
                            diesel_litres, km_run, mileage, display_order, created_at, updated_at
                        ) VALUES (%s, 'KPM', %s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                        """,
                        (pid, v["vehicle_no"], v["make"], v["model"], v["display_order"])
                    )

        # Ensure Oct'26 period has vehicles_count='5' for KPM
        oct_period = db.execute_query(
            "SELECT id FROM billing_periods WHERE module = 'transport' AND (period_code = '2026-10' OR period_label ILIKE %s) LIMIT 1;",
            ('%oct%',),
            fetch_all=False
        )
        if oct_period:
            oct_id = oct_period["id"]
            db.execute_commit(
                """
                INSERT INTO transport_census_entries (period_id, branch, vehicles_count, created_at)
                VALUES (%s, 'KPM', '5', CURRENT_TIMESTAMP)
                ON CONFLICT (period_id, branch) DO UPDATE SET vehicles_count = '5';
                """,
                (oct_id,)
            )
        print("[TransportVehiclesSync] Verified and seeded KPM fleet vehicles.")
    except Exception as e:
        print(f"[TransportVehiclesSync Warning] {e}")

if __name__ == "__main__":
    ensure_and_seed_transport_vehicles()
