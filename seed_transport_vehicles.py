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

UNIVERSITY_FLEET_VEHICLES = [
    {"vehicle_no": "TN99 Q 3209", "make": "ASHOK LEYLAND", "model": "Oct-18", "display_order": 1},
    {"vehicle_no": "TN99 Q 4686", "make": "ASHOK LEYLAND", "model": "", "display_order": 2},
    {"vehicle_no": "TN99 Q 4696", "make": "ASHOK LEYLAND", "model": "Apr-19", "display_order": 3},
    {"vehicle_no": "TN99 P 2487", "make": "TATA", "model": "Apr-19", "display_order": 4},
    {"vehicle_no": "TN99 S 0255", "make": "SML MAZDA", "model": "Mar-19", "display_order": 5},
    {"vehicle_no": "TN99 S 0271", "make": "SML MAZDA", "model": "Jun-19", "display_order": 6},
    {"vehicle_no": "TN99 S 0216", "make": "SML MAZDA", "model": "Apr-19", "display_order": 7},
    {"vehicle_no": "TN99 S 0261", "make": "SML MAZDA", "model": "Apr-19", "display_order": 8},
    {"vehicle_no": "TN99 S 0281", "make": "SML MAZDA", "model": "Apr-19", "display_order": 9},
    {"vehicle_no": "TN99 S 0240", "make": "SML MAZDA", "model": "Apr-19", "display_order": 10},
    {"vehicle_no": "TN99 S 0250", "make": "SML MAZDA", "model": "Apr-19", "display_order": 11},
    {"vehicle_no": "TN99 P 2496", "make": "TATA", "model": "Apr-19", "display_order": 12},
    {"vehicle_no": "TN99 X 2669", "make": "SML MAZDA", "model": "Sep-22", "display_order": 13},
    {"vehicle_no": "TN99 X 2253", "make": "SML MAZDA", "model": "Sep-22", "display_order": 14},
    {"vehicle_no": "TN99 X 5181", "make": "SML MAZDA", "model": "Oct-22", "display_order": 15},
    {"vehicle_no": "TN99 Z 5467", "make": "TATA", "model": "Nov-22", "display_order": 16}
]

RPS_FLEET_VEHICLES = [
    {"vehicle_no": "TN 99 AC 2234", "make": "TATA MARCOPOLO", "model": "Jun-24", "display_order": 1},
    {"vehicle_no": "TN 99 P 5178", "make": "TATA MARCOPOLO", "model": "Jan-19", "display_order": 2},
    {"vehicle_no": "TN 99 M 6350", "make": "TATA MARCOPOLO", "model": "Sep-18", "display_order": 3},
    {"vehicle_no": "TN 99 X 1663", "make": "SML MAZDA", "model": "Aug-22", "display_order": 4},
    {"vehicle_no": "TN 99 AA 8174", "make": "EICHER", "model": "Feb-24", "display_order": 5},
    {"vehicle_no": "TN 99 W 6953", "make": "EICHER", "model": "May-22", "display_order": 6},
    {"vehicle_no": "TN 99 B 8947", "make": "TRAVELLER", "model": "Mar-15", "display_order": 7},
    {"vehicle_no": "TN 99 AB 8649", "make": "TATA WINGER", "model": "May-24", "display_order": 8},
    {"vehicle_no": "TN 37 CD 4998", "make": "WINGER", "model": "May-13", "display_order": 9},
    {"vehicle_no": "TN 99 AC 2281", "make": "TATA MARCOPOLO", "model": "Jun-24", "display_order": 10},
    {"vehicle_no": "TN 37 BX 5141", "make": "MAZDA", "model": "Feb-12", "display_order": 11},
    {"vehicle_no": "TN 37 BT 7922", "make": "TRAVELLER", "model": "Nov-11", "display_order": 12},
    {"vehicle_no": "TN 99 AA 8200", "make": "EICHER", "model": "Feb-24", "display_order": 13},
    {"vehicle_no": "TN 99 AB 8636", "make": "TATA WINGER", "model": "May-24", "display_order": 14},
    {"vehicle_no": "TN 99 Z 4505", "make": "TATA MARCOPOLO", "model": "Jun-11", "display_order": 15},
    {"vehicle_no": "TN 20 BF 0541", "make": "TATA", "model": "Jun-11", "display_order": 16},
    {"vehicle_no": "TN 99 AA 8140", "make": "EICHER", "model": "Feb-24", "display_order": 17},
    {"vehicle_no": "TN 99 X 2061", "make": "SML MAZDA", "model": "Sep-22", "display_order": 18},
    {"vehicle_no": "TN 99 AB 8674", "make": "TATA WINGER", "model": "May-24", "display_order": 19}
]

COMMON_FLEET_VEHICLES = [
    {"vehicle_no": "TN99 R 3333", "make": "TOYOTA", "model": "Innova", "display_order": 1},
    {"vehicle_no": "TN99 AA3333", "make": "BMW", "model": "BMW", "display_order": 2},
    {"vehicle_no": "TN99 AE 3333", "make": "LEXUS", "model": "LEXUS", "display_order": 3},
    {"vehicle_no": "TN99 AU 3333", "make": "MG", "model": "MG 9", "display_order": 4},
    {"vehicle_no": "TN99 Y 4726", "make": "TATA", "model": "TIAGOR EV ZIPTRON", "display_order": 5},
    {"vehicle_no": "TN99 Y 4767", "make": "TATA", "model": "TIAGOR EC ZIPTRON", "display_order": 6},
    {"vehicle_no": "TN99 Y 5016", "make": "TATA", "model": "TIAGO EV", "display_order": 7},
    {"vehicle_no": "TN99 Y 4718", "make": "TATA", "model": "TIAGO EV", "display_order": 8},
    {"vehicle_no": "TN99 AC 3877", "make": "TATA", "model": "TATA CURVV", "display_order": 9},
    {"vehicle_no": "TN99 AC 2695", "make": "TATA", "model": "TATA NEXON", "display_order": 10},
    {"vehicle_no": "TN 99 Y 4749", "make": "TATA", "model": "TIGOR EV", "display_order": 11},
    {"vehicle_no": "TN 99 AC 6941", "make": "TATA", "model": "TIGOR EV", "display_order": 12},
    {"vehicle_no": "TN 33 BC 2577", "make": "AUDI", "model": "AUDI", "display_order": 13},
    {"vehicle_no": "TN 99 AK 6689", "make": "FORCE", "model": "AMBULANCE", "display_order": 14},
    {"vehicle_no": "TN37 BL 8228", "make": "TATA MARCOPOLO", "model": "Admission - Tata Marcopolo", "display_order": 15},
    {"vehicle_no": "GOLF BATTERY - OLD Main", "make": "ELECTRIC GOLF CART", "model": "Admission", "display_order": 16},
    {"vehicle_no": "GOLF BATTERY - NEW - Main", "make": "ELECTRIC GOLF CART", "model": "Admission", "display_order": 17},
    {"vehicle_no": "Golf Battery - Aqualia", "make": "ELECTRIC GOLF CART", "model": "Admission", "display_order": 18}
]

FLEET_ROSTERS = {
    "KPM": KPM_FLEET_VEHICLES,
    "University": UNIVERSITY_FLEET_VEHICLES,
    "RPS": RPS_FLEET_VEHICLES,
    "Common": COMMON_FLEET_VEHICLES
}

def ensure_and_seed_transport_vehicles():
    """
    Ensures official fleet vehicles for all branches (KPM, University, RPS, Common)
    are seeded in transport_vehicle_entries for all transport billing periods.
    """
    try:
        periods = db.execute_query(
            "SELECT id, period_code FROM billing_periods WHERE module = 'transport' ORDER BY id;"
        )
        if not periods:
            return

        for branch_name, vehicles_list in FLEET_ROSTERS.items():
            for p in periods:
                pid = p["id"]
                existing = db.execute_query(
                    "SELECT vehicle_no FROM transport_vehicle_entries WHERE period_id = %s AND branch = %s;",
                    (pid, branch_name)
                )
                existing_nos = {r["vehicle_no"].strip().upper().replace(" ", "") for r in (existing or [])}

                for v in vehicles_list:
                    clean_vno = v["vehicle_no"].strip().upper().replace(" ", "")
                    if clean_vno not in existing_nos:
                        db.execute_commit(
                            """
                            INSERT INTO transport_vehicle_entries (
                                period_id, branch, vehicle_no, make, model,
                                fuel_expenses, fc_cost, statutory_cost, repair_maintenance,
                                parking_fastag, employee_cost, other_cost, total_expenses,
                                diesel_litres, km_run, mileage, display_order, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                            """,
                            (pid, branch_name, v["vehicle_no"], v["make"], v["model"], v["display_order"])
                        )

            # Update vehicles_count in transport_census_entries
            b_count = str(len(vehicles_list))
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
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (period_id, branch) DO UPDATE SET vehicles_count = %s;
                    """,
                    (oct_id, branch_name, b_count, b_count)
                )

        total_v = sum(len(lst) for lst in FLEET_ROSTERS.values())
        print(f"[TransportVehiclesSync] Verified and seeded all {total_v} fleet vehicles: KPM ({len(KPM_FLEET_VEHICLES)}), University ({len(UNIVERSITY_FLEET_VEHICLES)}), RPS ({len(RPS_FLEET_VEHICLES)}), Common ({len(COMMON_FLEET_VEHICLES)}).")
    except Exception as e:
        print(f"[TransportVehiclesSync Warning] {e}")

if __name__ == "__main__":
    ensure_and_seed_transport_vehicles()
