import sys
import json
import ast
import re
from decimal import Decimal
from datetime import datetime, date
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
        'utility_meter_logs',
        'food_budget_tracking',
        'hostel_master_parameters',
        'hostel_census_entries',
        'hostel_budget_tracking',
        'transport_master_parameters',
        'transport_census_entries',
        'transport_vehicle_entries',
        'transport_budget_tracking',
        'transport_budget_common',
        'transport_budget_kpm',
        'transport_budget_rps',
        'transport_budget_university',
        'cctv_master_parameters',
        'cctv_monthly_entries',
        'monthly_attachments'
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

            gen_rows = db.execute_query(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s AND is_generated = 'ALWAYS';",
                (table,)
            )
            gen_cols = {g["column_name"] for g in gen_rows}
            cols = [c for c in rows[0].keys() if c not in gen_cols]
            cols_str = ", ".join([f'"{c}"' for c in cols])

            for r in rows:
                vals = []
                for c in cols:
                    val = r[c]
                    if val is None:
                        vals.append("NULL")
                    elif isinstance(val, bool):
                        vals.append("TRUE" if val else "FALSE")
                    elif isinstance(val, (int, float, Decimal)):
                        vals.append(str(val))
                    elif isinstance(val, (dict, list)):
                        cleaned = json.dumps(val, default=str).replace("'", "''")
                        vals.append(f"'{cleaned}'")
                    elif isinstance(val, (datetime, date)):
                        vals.append(f"'{val.isoformat()}'")
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
    serial_tables = [
        'fiscal_years', 'billing_periods', 'expense_categories', 'cost_heads',
        'vendors', 'users', 'monthly_expense_entries', 'food_budget_tracking',
        'hostel_master_parameters', 'hostel_census_entries', 'hostel_budget_tracking',
        'transport_master_parameters', 'transport_census_entries', 'transport_vehicle_entries',
        'transport_budget_tracking', 'transport_budget_common', 'transport_budget_kpm',
        'transport_budget_rps', 'transport_budget_university', 'cctv_master_parameters',
        'cctv_monthly_entries', 'monthly_attachments'
    ]
    for st in serial_tables:
        dump_lines.append(f"SELECT setval(pg_get_serial_sequence('{st}', 'id'), COALESCE((SELECT MAX(id) FROM {st}), 1));")

    dump_lines.append("\nCOMMIT;\n-- End of Backup Dump\n")
    return "\n".join(dump_lines)


def _sanitize_legacy_python_json_in_sql(sql_text: str) -> str:
    """
    Converts legacy backup SQL literals that serialized Python dicts/lists via str(val)
    (e.g. '{''key'': ''value''}') into valid JSON strings ('{"key": "value"}').
    """
    def _fix_literal(match):
        raw_inner = match.group(1)
        unescaped = raw_inner.replace("''", "'")
        stripped = unescaped.lstrip()
        if not stripped.startswith(("{", "[")):
            return match.group(0)
        # If it already parses as valid JSON, leave it alone
        try:
            json.loads(unescaped)
            return match.group(0)
        except Exception:
            pass
        # Try parsing as Python dict/list literal
        try:
            parsed = ast.literal_eval(unescaped)
            if isinstance(parsed, (dict, list)):
                valid_json = json.dumps(parsed, default=str).replace("'", "''")
                return f"'{valid_json}'"
        except Exception:
            pass
        return match.group(0)

    # Match any SQL single-quoted string literal (handling '' escapes properly)
    pattern = re.compile(r"'((?:[^']|'')*)'")
    return pattern.sub(_fix_literal, sql_text)


def _split_sql_values(vals_str: str) -> list:
    """Splits a SQL VALUES(...) argument list respecting single-quoted strings and '' escapes."""
    items = []
    buf = []
    in_quote = False
    i = 0
    n = len(vals_str)
    while i < n:
        ch = vals_str[i]
        if in_quote:
            if ch == "'" and i + 1 < n and vals_str[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            elif ch == "'":
                in_quote = False
            buf.append(ch)
        else:
            if ch == "'":
                in_quote = True
                buf.append(ch)
            elif ch == ",":
                items.append("".join(buf).strip())
                buf = []
                i += 1
                continue
            else:
                buf.append(ch)
        i += 1
    if buf or vals_str.endswith(","):
        items.append("".join(buf).strip())
    return items


def _unquote_sql(val: str):
    if val.upper() == "NULL":
        return None
    if val.startswith("'") and val.endswith("'") and len(val) >= 2:
        return val[1:-1].replace("''", "'")
    return val


def _remap_and_execute_sql_dump(sql_text: str, cur) -> None:
    """
    Executes a SQL dump while safely remapping parent IDs (expense_categories, billing_periods,
    cost_heads) when the target database already has matching natural keys under different IDs,
    preventing foreign-key violations such as monthly_expense_entries_period_id_fkey.
    """
    insert_re = re.compile(
        r"^INSERT\s+INTO\s+\"?([a-zA-Z0-9_]+)\"?\s*\(([^)]+)\)\s*VALUES\s*\((.*)\)\s*(ON\s+CONFLICT.*)?;?\s*$",
        re.IGNORECASE
    )

    cat_id_map = {}
    period_id_map = {}
    cost_head_id_map = {}
    generated_cols_cache = {}

    def _get_generated_cols(tbl: str) -> set:
        if tbl not in generated_cols_cache:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s AND is_generated = 'ALWAYS';",
                (tbl,)
            )
            generated_cols_cache[tbl] = {r[0] for r in cur.fetchall()}
        return generated_cols_cache[tbl]

    for raw_line in sql_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        upper = line.upper()
        if upper in ("BEGIN;", "COMMIT;"):
            continue

        m = insert_re.match(line)
        if not m:
            cur.execute(line)
            continue

        table = m.group(1).lower()
        cols = [c.strip().strip('"') for c in m.group(2).split(",")]
        vals = _split_sql_values(m.group(3))
        if len(cols) != len(vals):
            cur.execute(line)
            continue

        col_idx = {c: idx for idx, c in enumerate(cols)}

        # Remap foreign keys in child tables before executing
        if "category_id" in col_idx:
            c_raw = _unquote_sql(vals[col_idx["category_id"]])
            if c_raw is not None and str(c_raw).isdigit() and int(c_raw) in cat_id_map:
                vals[col_idx["category_id"]] = str(cat_id_map[int(c_raw)])

        if "period_id" in col_idx:
            p_raw = _unquote_sql(vals[col_idx["period_id"]])
            if p_raw is not None and str(p_raw).isdigit():
                p_int = int(p_raw)
                if p_int in period_id_map:
                    vals[col_idx["period_id"]] = str(period_id_map[p_int])
                else:
                    # Verify period_id exists in billing_periods; skip orphaned rows safely
                    cur.execute("SELECT 1 FROM billing_periods WHERE id = %s LIMIT 1;", (p_int,))
                    if not cur.fetchone():
                        continue

        if "cost_head_id" in col_idx:
            ch_raw = _unquote_sql(vals[col_idx["cost_head_id"]])
            if ch_raw is not None and str(ch_raw).isdigit():
                ch_int = int(ch_raw)
                if ch_int in cost_head_id_map:
                    vals[col_idx["cost_head_id"]] = str(cost_head_id_map[ch_int])
                else:
                    cur.execute("SELECT 1 FROM cost_heads WHERE id = %s LIMIT 1;", (ch_int,))
                    if not cur.fetchone():
                        continue

        # Record parent ID mappings when natural keys already exist under a different ID
        if table == "expense_categories" and "id" in col_idx and "code" in col_idx:
            dump_id = _unquote_sql(vals[col_idx["id"]])
            code = _unquote_sql(vals[col_idx["code"]])
            if dump_id is not None and str(dump_id).isdigit() and code:
                cur.execute("SELECT id FROM expense_categories WHERE code = %s LIMIT 1;", (code,))
                row = cur.fetchone()
                if row:
                    cat_id_map[int(dump_id)] = row[0]
                    continue

        if table == "billing_periods" and "id" in col_idx and "period_code" in col_idx:
            dump_id = _unquote_sql(vals[col_idx["id"]])
            p_code = _unquote_sql(vals[col_idx["period_code"]])
            mod = _unquote_sql(vals[col_idx["module"]]) if "module" in col_idx else "food"
            if dump_id is not None and str(dump_id).isdigit() and p_code:
                cur.execute(
                    "SELECT id FROM billing_periods WHERE period_code = %s AND COALESCE(module, 'food') = %s LIMIT 1;",
                    (p_code, mod or "food")
                )
                row = cur.fetchone()
                if row:
                    period_id_map[int(dump_id)] = row[0]
                    continue

        if table == "cost_heads" and "id" in col_idx and "name" in col_idx:
            dump_id = _unquote_sql(vals[col_idx["id"]])
            ch_name = _unquote_sql(vals[col_idx["name"]])
            cat_id = _unquote_sql(vals[col_idx["category_id"]]) if "category_id" in col_idx else None
            if dump_id is not None and str(dump_id).isdigit() and ch_name:
                if cat_id is not None and str(cat_id).isdigit():
                    cur.execute(
                        "SELECT id FROM cost_heads WHERE name = %s AND category_id = %s LIMIT 1;",
                        (ch_name, int(cat_id))
                    )
                else:
                    cur.execute("SELECT id FROM cost_heads WHERE name = %s LIMIT 1;", (ch_name,))
                row = cur.fetchone()
                if row:
                    cost_head_id_map[int(dump_id)] = row[0]
                    continue

        # Strip PostgreSQL GENERATED ALWAYS columns (e.g. unscanned_meals) so INSERT does not fail
        gen_cols = _get_generated_cols(table)
        if gen_cols:
            filtered = [(c, v) for c, v in zip(cols, vals) if c not in gen_cols]
            cols = [c for c, _ in filtered]
            vals = [v for _, v in filtered]

        # Replace existing transactional/budget rows by natural key so restore updates local data
        if table == "monthly_expense_entries" and "period_id" in col_idx and "cost_head_id" in col_idx:
            cur.execute(
                "DELETE FROM monthly_expense_entries WHERE period_id = %s AND cost_head_id = %s;",
                (int(_unquote_sql(vals[col_idx["period_id"]])), int(_unquote_sql(vals[col_idx["cost_head_id"]])))
            )
        elif table == "transport_vehicle_entries" and "period_id" in col_idx and "branch" in col_idx and "vehicle_no" in col_idx:
            cur.execute(
                "DELETE FROM transport_vehicle_entries WHERE period_id = %s AND LOWER(branch) = LOWER(%s) AND vehicle_no = %s;",
                (int(_unquote_sql(vals[col_idx["period_id"]])), _unquote_sql(vals[col_idx["branch"]]), _unquote_sql(vals[col_idx["vehicle_no"]]))
            )
        elif table == "transport_census_entries" and "period_id" in col_idx and "branch" in col_idx:
            cur.execute(
                "DELETE FROM transport_census_entries WHERE period_id = %s AND LOWER(branch) = LOWER(%s);",
                (int(_unquote_sql(vals[col_idx["period_id"]])), _unquote_sql(vals[col_idx["branch"]]))
            )
        elif table == "hostel_census_entries" and "period_id" in col_idx:
            cur.execute(
                "DELETE FROM hostel_census_entries WHERE period_id = %s;",
                (int(_unquote_sql(vals[col_idx["period_id"]])),)
            )
        elif table in ("food_budget_tracking", "hostel_budget_tracking") and "budget_head" in col_idx:
            cur.execute(
                f"DELETE FROM {table} WHERE budget_head = %s;",
                (_unquote_sql(vals[col_idx["budget_head"]]),)
            )
        elif table == "cctv_monthly_entries" and "period_id" in col_idx:
            cur.execute(
                "DELETE FROM cctv_monthly_entries WHERE period_id = %s;",
                (int(_unquote_sql(vals[col_idx["period_id"]])),)
            )

        cols_sql = ", ".join([f'"{c}"' for c in cols])
        vals_sql = ", ".join(vals)
        conflict_clause = m.group(4) or "ON CONFLICT DO NOTHING"
        cur.execute(f"INSERT INTO {table} ({cols_sql}) VALUES ({vals_sql}) {conflict_clause};")


def restore_sql_dump(sql_text: str) -> dict:
    """Restores database by executing the provided SQL dump text."""
    sanitized_sql = _sanitize_legacy_python_json_in_sql(sql_text)
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            _remap_and_execute_sql_dump(sanitized_sql, cur)
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

            # Resolve real billing period IDs per module
            cur.execute("SELECT id FROM billing_periods WHERE module = 'food' ORDER BY start_date ASC, id ASC;")
            food_period_ids = [r[0] for r in cur.fetchall()]

            def upsert_entry(p_id, ch_id, amt, mod):
                cur.execute(
                    "SELECT id FROM monthly_expense_entries WHERE period_id = %s AND cost_head_id = %s LIMIT 1;",
                    (p_id, ch_id)
                )
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        "UPDATE monthly_expense_entries SET amount = %s, module = %s, status = 'audited', updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                        (amt, mod, existing[0])
                    )
                else:
                    cur.execute(
                        "INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount, module, status, updated_at) VALUES (%s, %s, %s, %s, 'audited', CURRENT_TIMESTAMP);",
                        (p_id, ch_id, amt, mod)
                    )

            # Upsert Food line items
            for cat_code, ch_name, amounts in food_actuals:
                cur.execute("SELECT id FROM cost_heads WHERE name = %s LIMIT 1;", (ch_name,))
                ch_row = cur.fetchone()
                if ch_row:
                    ch_id = ch_row[0]
                    for idx, p_id in enumerate(food_period_ids):
                        if idx < len(amounts):
                            upsert_entry(p_id, ch_id, amounts[idx], 'food')

            # Upsert Hostel & Transport actuals using their real module period IDs
            for mod in ('hostel', 'transport'):
                cur.execute("SELECT id FROM billing_periods WHERE module = %s ORDER BY start_date ASC, id ASC;", (mod,))
                mod_pids = [r[0] for r in cur.fetchall()]
                cur.execute(
                    "SELECT id, name FROM cost_heads WHERE category_id IN (SELECT id FROM expense_categories WHERE module = %s);",
                    (mod,)
                )
                mod_cost_heads = cur.fetchall()
                for ch_id, ch_name in mod_cost_heads:
                    for p_id in mod_pids:
                        base_val = (abs(hash(f"{ch_name}_{p_id}")) % 120000) + 40000
                        upsert_entry(p_id, ch_id, base_val, mod)

            conn.commit()
            return {"status": "success", "message": "Canonical historical demo actuals successfully re-seeded across all modules."}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        db.release_db_connection(conn)
