import sys
from datetime import datetime
import database as db

def generate_sql_dump() -> str:
    """Generates a complete PostgreSQL database backup dump as SQL statements."""
    dump_lines = [
        "-- ============================================================================",
        "-- Rathinam Group of Institutions • Report Database Backup Dump",
        f"-- Export Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "-- Database: PostgreSQL 18 (food_operations)",
        "-- Target Modules: Food & Dining, Hostel Facilities, Transport Fleet",
        "-- ============================================================================\n",
        "BEGIN;\n",
        "SET statement_timeout = 0;",
        "SET client_encoding = 'UTF8';",
        "SET standard_conforming_strings = on;\n"
    ]

    tables = [
        'fiscal_years',
        'billing_periods',
        'expense_categories',
        'cost_heads',
        'vendors',
        'users',
        'role_page_permissions',
        'monthly_expense_entries',
        'dining_census_entries',
        'utility_meter_logs'
    ]

    for table in tables:
        dump_lines.append(f"-- -------------------------------------------------------------")
        dump_lines.append(f"-- Table Data: {table}")
        dump_lines.append(f"-- -------------------------------------------------------------")

        try:
            rows = db.execute_query(f"SELECT * FROM {table} ORDER BY 1 ASC")
            if not rows:
                dump_lines.append(f"-- (No rows in {table})\n")
                continue

            cols = list(rows[0].keys())
            cols_str = ", ".join([f'"{c}"' for c in cols])

            for r in rows:
                vals = []
                for c in cols:
                    val = r[c]
                    if val is None:
                        vals.append("NULL")
                    elif isinstance(val, bool):
                        vals.append("TRUE" if val else "FALSE")
                    elif isinstance(val, (int, float)):
                        vals.append(str(val))
                    elif isinstance(val, datetime):
                        vals.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                    else:
                        cleaned = str(val).replace("'", "''")
                        vals.append(f"'{cleaned}'")
                vals_str = ", ".join(vals)
                dump_lines.append(f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;")
            dump_lines.append("")
        except Exception as e:
            dump_lines.append(f"-- Error dumping {table}: {str(e)}\n")

    # Sequence updates
    dump_lines.append("-- -------------------------------------------------------------")
    dump_lines.append("-- Sequence Resets")
    dump_lines.append("-- -------------------------------------------------------------")
    serial_tables = ['fiscal_years', 'billing_periods', 'expense_categories', 'cost_heads', 'vendors', 'users', 'monthly_expense_entries']
    for st in serial_tables:
        dump_lines.append(f"SELECT setval(pg_get_serial_sequence('{st}', 'id'), COALESCE((SELECT MAX(id) FROM {st}), 1));")

    dump_lines.append("\nCOMMIT;\n-- End of Backup Dump\n")
    return "\n".join(dump_lines)


def restore_sql_dump(sql_text: str) -> dict:
    """Restores database by executing the provided SQL dump text."""
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql_text)
            conn.commit()
            return {"status": "success", "message": "SQL dump executed and committed successfully."}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        db.release_db_connection(conn)


def clear_dummy_data() -> dict:
    """
    Safely removes transactional records (monthly expenses, census, logs)
    while preserving categories, cost heads, billing cycles, users and configuration.
    """
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM monthly_expense_entries;")
            count_entries = cur.fetchone()[0]

            cur.execute("DELETE FROM monthly_expense_entries;")
            cur.execute("DELETE FROM dining_census_entries;")
            cur.execute("DELETE FROM utility_meter_logs;")
            conn.commit()

            return {
                "status": "success",
                "cleared_entries": count_entries,
                "message": f"Successfully cleared {count_entries} dummy expense entries. Master data and cycles preserved."
            }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        db.release_db_connection(conn)


def reseed_demo_data() -> dict:
    """Re-seeds canonical historical expenses (Jun'26 to Oct'26) across Food, Hostel, Transport."""
    import random
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Food Excel actuals
            food_actuals = [
                # Material issued
                ("FOOD_MATERIAL", "Material issued", [5839162.00, 7361269.00, 6949789.00, 9891873.00, 9140730.00]),
                # Fuel
                ("FOOD_MATERIAL", "Fuel Expenses (Gas)", [823395.00, 958560.00, 717708.00, 1042274.00, 982945.00]),
                # Salary
                ("FOOD_LABOUR", "Salary", [1694705.00, 1628691.00, 1862412.00, 1834324.00, 1988139.00]),
                # Catering Vendor
                ("FOOD_LABOUR", "Catering Vendor", [268700.00, 410500.00, 299600.00, 515200.00, 498600.00]),
                # Adithya Housekeeping
                ("FOOD_LABOUR", "Adithya Housekeeping", [469920.00, 525580.00, 507320.00, 464530.00, 459360.00]),
                # Siri event
                ("FOOD_LABOUR", "Siri event", [229268.00, 382684.00, 297851.00, 495760.00, 558121.60]),
                # Food Court Maintenance
                ("FC_MAINTENANCE", "Food Court Maintenance", [293075.80, 131972.00, 275221.00, 327232.00, 378443.00]),
                # Water consumption
                ("FC_MAINTENANCE", "Water consumption", [89756.25, 159129.48, 149484.33, 215954.70, 0.00]),
                # Food Vehicle
                ("FC_MAINTENANCE", "Food Vehicle", [43392.11, 30441.70, 24023.88, 33940.45, 81039.58]),
                # Event Purchase
                ("EVENTS_ADDITIONAL", "Event Purchase", [254495.00, 217870.00, 114490.00, 76775.00, 210525.00]),
                # Food Festival
                ("FOOD_FESTIVAL", "Food Festival", [0.00, 0.00, 551639.00, 0.00, 0.00])
            ]

            period_ids = [1, 2, 3, 4, 5] # Jun, Jul, Aug, Sept, Oct

            # Upsert Food line items
            for cat_code, ch_name, amounts in food_actuals:
                cur.execute("SELECT id FROM cost_heads WHERE name = %s LIMIT 1;", (ch_name,))
                ch_row = cur.fetchone()
                if ch_row:
                    ch_id = ch_row[0]
                    for idx, p_id in enumerate(period_ids):
                        amt = amounts[idx]
                        cur.execute("""
                        INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount, status, updated_at)
                        VALUES (%s, %s, %s, 'audited', CURRENT_TIMESTAMP)
                        ON CONFLICT (period_id, cost_head_id)
                        DO UPDATE SET amount = EXCLUDED.amount, status = 'audited', updated_at = CURRENT_TIMESTAMP;
                        """, (p_id, ch_id, amt))

            # Upsert Hostel & Transport actuals
            cur.execute("SELECT id, name, category_id FROM cost_heads WHERE category_id IN (SELECT id FROM expense_categories WHERE module IN ('hostel', 'transport'));")
            ht_cost_heads = cur.fetchall()

            for ch_id, ch_name, cat_id in ht_cost_heads:
                for p_id in period_ids:
                    # Deterministic seeded values
                    base_val = (hash(f"{ch_name}_{p_id}") % 120000) + 40000
                    cur.execute("""
                    INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount, status, updated_at)
                    VALUES (%s, %s, %s, 'audited', CURRENT_TIMESTAMP)
                    ON CONFLICT (period_id, cost_head_id)
                    DO UPDATE SET amount = EXCLUDED.amount, status = 'audited', updated_at = CURRENT_TIMESTAMP;
                    """, (p_id, ch_id, base_val))

            conn.commit()
            return {"status": "success", "message": "Canonical historical demo actuals successfully re-seeded across all modules."}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        db.release_db_connection(conn)
