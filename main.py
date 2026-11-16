from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import re
import json
import bcrypt
import database as db
import system_manager
import formula_engine as fe

app = FastAPI(
    title="Rathinam Report & Analytics API",
    description="Backend API for Food, Hostel & Transport Operations Management System",
    version="1.4.0"
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Subpath rewrite middleware: seamlessly supports deployment under rguedu.in/Report/api
@app.middleware("http")
async def rewrite_report_subpath(request: Request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/Report/api"):
        request.scope["path"] = path.replace("/Report/api", "/api", 1)
    elif path.startswith("/report/api"):
        request.scope["path"] = path.replace("/report/api", "/api", 1)
    return await call_next(request)

def ensure_schema_compatibility():
    """
    Safely and idempotently ensures all required columns exist in the database,
    even if full migrations previously stopped or encountered non-critical errors.
    """
    stmts = [
        "ALTER TABLE monthly_expense_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'Common';",
        "CREATE INDEX IF NOT EXISTS idx_monthly_expense_entries_branch ON monthly_expense_entries(branch);",
        "ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'Common';",
        "CREATE INDEX IF NOT EXISTS idx_transport_census_entries_branch ON transport_census_entries(branch);",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS category_type VARCHAR(20) NOT NULL DEFAULT 'DIRECT';",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_expression TEXT DEFAULT NULL;",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_definition JSONB DEFAULT NULL;",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS formula_version INT NOT NULL DEFAULT 1;",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';",
        "ALTER TABLE billing_periods ADD COLUMN IF NOT EXISTS module VARCHAR(50) NOT NULL DEFAULT 'food';",
        "ALTER TABLE hostel_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;",
        """
        CREATE TABLE IF NOT EXISTS hostel_master_parameters (
            id SERIAL PRIMARY KEY,
            param_key VARCHAR(100) UNIQUE NOT NULL,
            param_name VARCHAR(255) NOT NULL,
            section VARCHAR(100) NOT NULL,
            section_order INT NOT NULL DEFAULT 1,
            input_type VARCHAR(50) NOT NULL DEFAULT 'boys_girls_total',
            unit VARCHAR(50) DEFAULT '',
            formula TEXT DEFAULT NULL,
            display_order INT NOT NULL DEFAULT 1,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]
    for stmt in stmts:
        try:
            db.execute_commit(stmt)
        except Exception as e:
            print(f"[SchemaCompat] Notice: {e}")

@app.on_event("startup")
def startup_event():
    try:
        ensure_schema_compatibility()
    except Exception as e:
        print(f"Startup schema compatibility warning: {e}")
    try:
        db.auto_migrate()
    except Exception as e:
        print(f"Startup schema migration warning: {e}")

@app.get("/api/system/schema-compat")
@app.post("/api/system/schema-compat")
def run_schema_compat():
    try:
        ensure_schema_compatibility()
        try:
            db.auto_migrate()
        except Exception:
            pass
        return {"status": "ok", "message": "Schema compatibility verified and updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# PYDANTIC MODELS
# -------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

class ExpenseEntryCreate(BaseModel):
    period_id: int
    cost_head_id: int
    vendor_id: Optional[int] = None
    amount: float
    remarks: Optional[str] = None

class BatchEntryItem(BaseModel):
    cost_head_id: int
    vendor_id: Optional[int] = None
    amount: float
    remarks: Optional[str] = None

class BatchSaveRequest(BaseModel):
    period_id: int
    entries: List[BatchEntryItem]
    active_students: Optional[int] = None
    active_staff: Optional[int] = None
    others_count: Optional[int] = None
    total_persons: Optional[int] = None
    production_meals: Optional[int] = None
    operating_days: Optional[int] = None
    hostel_census: Optional[Dict[str, Any]] = None
    transport_census: Optional[Dict[str, Any]] = None
    module: Optional[str] = "food"
    branch: Optional[str] = "Common"
    updated_cost_heads: Optional[List[Dict[str, Any]]] = None
    updated_categories: Optional[List[Dict[str, Any]]] = None

class SpreadsheetSaveRequest(BaseModel):
    module: str = "food"
    branch: Optional[str] = "Common"
    entries_by_period: Optional[Dict[str, List[Dict[str, Any]]]] = None
    updated_cost_heads: Optional[List[Dict[str, Any]]] = None
    updated_categories: Optional[List[Dict[str, Any]]] = None
    new_cost_heads: Optional[List[Dict[str, Any]]] = None
    census_by_period: Optional[Dict[str, Dict[str, Any]]] = None
    hostel_census_by_period: Optional[Dict[str, Dict[str, Any]]] = None
    transport_census_by_period: Optional[Dict[str, Dict[str, Any]]] = None

class ClonePeriodRequest(BaseModel):
    source_period_id: int
    target_period_id: int

class LockPeriodRequest(BaseModel):
    period_id: int
    is_closed: bool

class PeriodCreate(BaseModel):
    period_label: str
    period_code: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    operating_days: Optional[int] = None
    module: Optional[str] = "food"
    clone_from_period_id: Optional[int] = None

class PeriodUpdate(BaseModel):
    period_label: str
    period_code: Optional[str] = None
    is_closed: Optional[bool] = None

# Master Data Models
class CostHeadCreate(BaseModel):
    category_id: int
    name: str
    code: Optional[str] = None
    cost_behavior: Optional[str] = "variable"
    default_vendor_id: Optional[int] = None
    display_order: Optional[int] = None

class CostHeadUpdate(BaseModel):
    category_id: Optional[int] = None
    name: str
    code: Optional[str] = None
    cost_behavior: Optional[str] = "variable"
    default_vendor_id: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = True

class ReorderCostHeadsRequest(BaseModel):
    cost_head_ids: List[int]

class ReorderCategoriesRequest(BaseModel):
    category_ids: List[int]

class BatchDeleteRequest(BaseModel):
    ids: List[int]

class CategoryCreate(BaseModel):
    name: str
    code: Optional[str] = None
    display_order: Optional[int] = None
    module: Optional[str] = "food"
    category_type: Optional[str] = "DIRECT"  # 'DIRECT' | 'FORMULA'
    formula_expression: Optional[str] = None
    formula_definition: Optional[Dict[str, Any]] = None
    formula_version: Optional[int] = 1

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = True
    module: Optional[str] = None
    category_type: Optional[str] = None
    formula_expression: Optional[str] = None
    formula_definition: Optional[Dict[str, Any]] = None
    formula_version: Optional[int] = None

class CategoryFormulaCreate(BaseModel):
    module: Optional[str] = "food"
    name: str
    expression: str
    description: Optional[str] = ""
    unit_type: Optional[str] = "currency"
    display_order: Optional[int] = 0

class CategoryFormulaUpdate(BaseModel):
    name: Optional[str] = None
    expression: Optional[str] = None
    description: Optional[str] = None
    unit_type: Optional[str] = None
    display_order: Optional[int] = None

class UserCreate(BaseModel):
    username: str
    full_name: str
    email: str
    password: str
    role: str
    department: Optional[str] = "Campus Operations"

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None

class PagePermissionItem(BaseModel):
    role: str
    page_id: str
    can_access: bool

class PagePermissionsBatch(BaseModel):
    permissions: List[PagePermissionItem]

class ClearDataRequest(BaseModel):
    confirmation_code: str

# -------------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# -------------------------------------------------------------
@app.post("/api/auth/login")
def login(req: LoginRequest):
    try:
        user = db.execute_query(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (req.username.strip(), req.username.strip()),
            fetch_all=False
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="User account is deactivated")
        
        valid = bcrypt.checkpw(req.password.encode('utf-8'), user["password_hash"].encode('utf-8'))
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        db.execute_commit("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user["id"],))

        return {
            "status": "success",
            "token": f"rathinam-token-{user['id']}-{user['username']}",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
                "department": user["department"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
def health_check():
    try:
        res = db.execute_query("SELECT 1 AS status", fetch_all=False)
        return {"status": "ok", "database": "connected", "postgres_check": res["status"] == 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# -------------------------------------------------------------
# BILLING PERIODS ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/periods")
def get_periods(module: Optional[str] = None):
    try:
        if module and module != "all":
            return db.execute_query(
                "SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module "
                "FROM billing_periods WHERE module = %s ORDER BY start_date",
                (module,)
            )
        return db.execute_query(
            "SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module "
            "FROM billing_periods ORDER BY start_date"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master/periods")
def get_master_periods(module: Optional[str] = None):
    return get_periods(module)

@app.post("/api/periods")
def create_period(req: PeriodCreate):
    try:
        import re
        import calendar

        label = req.period_label.strip()
        mod = (req.module or "food").strip().lower()

        months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'sept': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        derived_code = (req.period_code or "").strip()
        if not derived_code:
            match = re.search(r'([A-Za-z]+)[\'\s_-]*(\d{2,4})', label)
            if match:
                m_str = match.group(1).lower()[:3]
                m_num = months.get(m_str, '01')
                y_str = match.group(2)
                if len(y_str) == 2:
                    y_str = '20' + y_str
                derived_code = f"{y_str}-{m_num}"
            else:
                existing = db.execute_query("SELECT COUNT(*) as cnt FROM billing_periods WHERE module = %s", (mod,), fetch_all=False)
                cnt = (existing['cnt'] if existing else 0) + 1
                derived_code = f"2026-{cnt:02d}"

        # Calculate start_date, end_date, operating_days
        parts = derived_code.split('-')
        year = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 2026
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        _, last_day = calendar.monthrange(year, month)

        start_date = req.start_date or f"{year:04d}-{month:02d}-01"
        end_date = req.end_date or f"{year:04d}-{month:02d}-{last_day:02d}"
        operating_days = req.operating_days if req.operating_days is not None else last_day

        insert_sql = """
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, is_closed, module)
        VALUES (1, %s, %s, %s, %s, %s, false, %s)
        RETURNING id, period_code, period_label, module;
        """
        new_period = db.execute_query(
            insert_sql,
            (derived_code, label, start_date, end_date, operating_days, mod),
            fetch_all=False
        )

        if req.clone_from_period_id:
            clone_sql = """
            INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, vendor_id, amount, remarks, status, branch)
            SELECT %s, %s, cost_head_id, vendor_id, amount, 'Cloned from baseline', 'draft', COALESCE(branch, 'Common')
            FROM monthly_expense_entries
            WHERE period_id = %s
            ON CONFLICT (module, period_id, cost_head_id, branch) DO NOTHING;
            """
            db.execute_commit(clone_sql, (mod, new_period["id"], req.clone_from_period_id))

            if mod == "hostel":
                db.execute_commit("""
                INSERT INTO hostel_census_entries (
                    period_id, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
                    students_boys, students_girls, students_total, staff_boys, staff_girls, staff_total,
                    total_occupied, vacant_total, vacant_college, occupied_pct, vacant_pct, students_vacated,
                    tickets_received, tickets_closed, tickets_open, tat_hours, quality_issues_received,
                    quality_issues_closed, quality_issues_open, incidents_count, power_units, power_cost,
                    water_purchase_cost, normal_water_litres, normal_water_cost, drinking_water_litres,
                    drinking_water_cost, sq_feet, approved_budget, cumulative_budget_spent
                )
                SELECT %s, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
                    students_boys, students_girls, students_total, staff_boys, staff_girls, staff_total,
                    total_occupied, vacant_total, vacant_college, occupied_pct, vacant_pct, students_vacated,
                    tickets_received, tickets_closed, tickets_open, tat_hours, quality_issues_received,
                    quality_issues_closed, quality_issues_open, incidents_count, power_units, power_cost,
                    water_purchase_cost, normal_water_litres, normal_water_cost, drinking_water_litres,
                    drinking_water_cost, sq_feet, approved_budget, cumulative_budget_spent
                FROM hostel_census_entries WHERE period_id = %s
                ON CONFLICT (period_id) DO NOTHING;
                """, (new_period["id"], req.clone_from_period_id))
            elif mod == "transport":
                db.execute_commit("""
                INSERT INTO transport_census_entries (
                    period_id, branch, vehicles_count, passengers_count, students_count, staff_count,
                    approved_kms, actual_kms, additional_kms, diesel_litres, fuel_expenses,
                    service_tickets_raised, service_tickets_closed, service_tickets_open,
                    quality_issues_received, quality_issues_closed, quality_issues_open,
                    statutory_compliance, incidents_count, approved_budget, cumulative_budget_spent
                )
                SELECT %s, COALESCE(branch, 'Common'), vehicles_count, passengers_count, students_count, staff_count,
                    approved_kms, actual_kms, additional_kms, diesel_litres, fuel_expenses,
                    service_tickets_raised, service_tickets_closed, service_tickets_open,
                    quality_issues_received, quality_issues_closed, quality_issues_open,
                    statutory_compliance, incidents_count, approved_budget, cumulative_budget_spent
                FROM transport_census_entries WHERE period_id = %s
                ON CONFLICT (period_id, branch) DO NOTHING;
                """, (new_period["id"], req.clone_from_period_id))

        return {"status": "success", "period": new_period}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/periods/{period_id}")
def update_period(period_id: int, req: PeriodUpdate):
    """
    Update a billing period's label, code, or lock status.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                label = req.period_label.strip()
                if req.period_code:
                    code = req.period_code.strip()
                    if req.is_closed is not None:
                        cur.execute("UPDATE billing_periods SET period_label = %s, period_code = %s, is_closed = %s WHERE id = %s", (label, code, req.is_closed, period_id))
                    else:
                        cur.execute("UPDATE billing_periods SET period_label = %s, period_code = %s WHERE id = %s", (label, code, period_id))
                else:
                    if req.is_closed is not None:
                        cur.execute("UPDATE billing_periods SET period_label = %s, is_closed = %s WHERE id = %s", (label, req.is_closed, period_id))
                    else:
                        cur.execute("UPDATE billing_periods SET period_label = %s WHERE id = %s", (label, period_id))
                conn.commit()
                return {"status": "success", "message": f"Period #{period_id} updated successfully"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/periods/{period_id}")
def delete_period(period_id: int):
    """
    Delete a billing period and its dependent expense/census entries.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # First delete dependent entries
                cur.execute("DELETE FROM monthly_expense_entries WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM dining_census_entries WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM utility_meter_logs WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM billing_periods WHERE id = %s RETURNING period_label", (period_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Period not found")
                conn.commit()
                return {"status": "success", "message": f"Billing period '{row[0]}' and associated entries deleted successfully"}
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# CORE ANALYTICAL REPORTING & DYNAMIC MATRIX
# -------------------------------------------------------------
# EXECUTIVE OVERVIEW API (SCOPED BY MODULE)
# -------------------------------------------------------------
@app.get("/api/overview")
def get_overview(module: str = "food"):
    try:
        mod = module or "food"
        rows = db.execute_query("""
            SELECT 
                p.period_code,
                p.period_label,
                p.start_date,
                COALESCE(SUM(e.amount), 0) AS total
            FROM billing_periods p
            LEFT JOIN monthly_expense_entries e ON p.id = e.period_id AND e.module = %s
            WHERE p.module = %s
            GROUP BY p.period_code, p.period_label, p.start_date
            ORDER BY p.start_date
        """, (mod, mod))

        grand_total = sum(float(r["total"]) for r in rows)
        avg_monthly = grand_total / len(rows) if rows else 0

        trend = [{
            "period_code": r["period_code"],
            "period_label": r["period_label"],
            "total": float(r["total"])
        } for r in rows]

        return {
            "summary": {
                "grand_total": round(grand_total, 2),
                "monthly_avg": round(avg_monthly, 2)
            },
            "trend": trend
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/matrix")
def get_matrix(module: str = "food", branch: Optional[str] = None):
    """
    Dynamically generates the operational matrix for periods, categories, and active cost heads.
    Supports filtering by module ('food', 'hostel', 'transport', 'all') and branch for transport.
    """
    try:
        if module and module != "all":
            periods = db.execute_query(
                "SELECT id, period_code, period_label, start_date, operating_days, is_closed, module FROM billing_periods WHERE module = %s ORDER BY start_date",
                (module,)
            )
        else:
            periods = db.execute_query(
                "SELECT id, period_code, period_label, start_date, operating_days, is_closed, module FROM billing_periods ORDER BY start_date"
            )
        num_periods = len(periods) or 1

        if module and module != "all":
            categories = db.execute_query(
                "SELECT id, code, name, display_order, module, category_type, formula_expression, formula_definition FROM expense_categories WHERE is_active = true AND module = %s ORDER BY display_order",
                (module,)
            )
            cost_heads = db.execute_query("""
                SELECT ch.id, ch.category_id, ch.name, ch.code, ch.cost_behavior, ch.display_order, ch.default_vendor_id, v.name AS vendor_name
                FROM cost_heads ch
                JOIN expense_categories ec ON ch.category_id = ec.id
                LEFT JOIN vendors v ON ch.default_vendor_id = v.id
                WHERE ch.is_active = true AND ec.module = %s
                ORDER BY ch.display_order
            """, (module,))
        else:
            categories = db.execute_query(
                "SELECT id, code, name, display_order, module, category_type, formula_expression, formula_definition FROM expense_categories WHERE is_active = true ORDER BY display_order"
            )
            cost_heads = db.execute_query("""
                SELECT ch.id, ch.category_id, ch.name, ch.code, ch.cost_behavior, ch.display_order, ch.default_vendor_id, v.name AS vendor_name
                FROM cost_heads ch
                LEFT JOIN vendors v ON ch.default_vendor_id = v.id
                WHERE ch.is_active = true
                ORDER BY ch.display_order
            """)

        TRANSPORT_BRANCHES = ["RPS", "KPM", "Common", "University"]

        entries = []
        try:
            if module and module != "all":
                entries = db.execute_query(
                    "SELECT cost_head_id, period_id, amount, remarks, branch FROM monthly_expense_entries WHERE module = %s",
                    (module,)
                )
            else:
                entries = db.execute_query("SELECT cost_head_id, period_id, amount, remarks, branch FROM monthly_expense_entries")
        except Exception as q_err:
            if "branch" in str(q_err).lower():
                try:
                    ensure_schema_compatibility()
                except Exception:
                    pass
                try:
                    if module and module != "all":
                        entries = db.execute_query(
                            "SELECT cost_head_id, period_id, amount, remarks, branch FROM monthly_expense_entries WHERE module = %s",
                            (module,)
                        )
                    else:
                        entries = db.execute_query("SELECT cost_head_id, period_id, amount, remarks, branch FROM monthly_expense_entries")
                except Exception:
                    if module and module != "all":
                        entries = db.execute_query(
                            "SELECT cost_head_id, period_id, amount, remarks, 'Common' AS branch FROM monthly_expense_entries WHERE module = %s",
                            (module,)
                        )
                    else:
                        entries = db.execute_query("SELECT cost_head_id, period_id, amount, remarks, 'Common' AS branch FROM monthly_expense_entries")
            else:
                raise q_err

        entry_map = {}
        entry_map_by_branch = {b: {} for b in TRANSPORT_BRANCHES}
        matrix_by_branch = {}

        if module == "transport":
            for e in entries:
                ch_id = e["cost_head_id"]
                p_id = e["period_id"]
                amt = float(e["amount"]) if e["amount"] is not None else 0.0
                b = e.get("branch") or "Common"
                entry_map_by_branch.setdefault(b, {})[(ch_id, p_id)] = {
                    "amount": amt,
                    "remarks": e.get("remarks") or ""
                }

            if branch and branch != "all" and branch in entry_map_by_branch:
                entry_map = entry_map_by_branch[branch]
            else:
                # Consolidated: sum of all branches
                for b in TRANSPORT_BRANCHES:
                    for (ch_id, p_id), it_data in entry_map_by_branch.get(b, {}).items():
                        if (ch_id, p_id) not in entry_map:
                            entry_map[(ch_id, p_id)] = {"amount": 0.0, "remarks": ""}
                        entry_map[(ch_id, p_id)]["amount"] += it_data["amount"]

            for b in TRANSPORT_BRANCHES:
                b_map = entry_map_by_branch.get(b, {})
                matrix_by_branch[b] = {
                    "amounts": {
                        f"{ch['id']}_{p['id']}": b_map.get((ch["id"], p["id"]), {}).get("amount", 0.0)
                        for ch in cost_heads for p in periods
                    }
                }
        else:
            for e in entries:
                entry_map[(e["cost_head_id"], e["period_id"])] = {
                    "amount": float(e["amount"]),
                    "remarks": e.get("remarks") or ""
                }

        grand_total_by_period = {p["id"]: 0.0 for p in periods}
        overall_grand_total = 0.0

        categories_data = []

        for cat in categories:
            cat_id = cat["id"]
            cat_items = [ch for ch in cost_heads if ch["category_id"] == cat_id]
            if not cat_items:
                continue

            # Sort items by display_order
            cat_items.sort(key=lambda x: x["display_order"])

            cat_subtotal_by_period = {p["id"]: 0.0 for p in periods}
            cat_total = 0.0

            formatted_items = []
            for ch in cat_items:
                ch_id = ch["id"]
                amounts_dict = {}
                remarks_dict = {}
                row_total = 0.0

                for p in periods:
                    p_id = p["id"]
                    item_data = entry_map.get((ch_id, p_id))
                    val = item_data["amount"] if item_data else None
                    rem = item_data["remarks"] if item_data else ""
                    amounts_dict[str(p_id)] = val
                    remarks_dict[str(p_id)] = rem
                    if val is not None:
                        row_total += val
                        cat_subtotal_by_period[p_id] += val
                        grand_total_by_period[p_id] += val

                row_avg = round(row_total / num_periods, 2)
                cat_total += row_total
                overall_grand_total += row_total

                formatted_items.append({
                    "cost_head_id": ch_id,
                    "category_id": cat_id,
                    "description": ch["name"],
                    "code": ch["code"],
                    "cost_behavior": ch["cost_behavior"],
                    "default_vendor_name": ch["vendor_name"],
                    "display_order": ch["display_order"],
                    "amounts": amounts_dict,
                    "remarks": remarks_dict,
                    "total": row_total,
                    "avg": row_avg
                })

            cat_avg = round(cat_total / num_periods, 2)

            f_def = cat.get("formula_definition")
            if isinstance(f_def, str):
                try:
                    f_def = json.loads(f_def)
                except Exception:
                    f_def = None

            categories_data.append({
                "category_id": cat_id,
                "category_name": cat["name"],
                "category_code": cat["code"],
                "display_order": cat["display_order"],
                "category_type": cat.get("category_type") or "DIRECT",
                "formula_expression": cat.get("formula_expression"),
                "formula_definition": f_def,
                "items": formatted_items,
                "subtotal": {
                    "amounts": {str(k): round(v, 2) for k, v in cat_subtotal_by_period.items()},
                    "total": round(cat_total, 2),
                    "avg": cat_avg
                }
            })

        # Dynamically evaluate FORMULA categories across all periods using safe formula engine
        period_cat_values = {p["id"]: {} for p in periods}
        for cdata in categories_data:
            cid = cdata["category_id"]
            cname = cdata["category_name"].strip().lower()
            for p in periods:
                pid = p["id"]
                val = cdata["subtotal"]["amounts"].get(str(pid), 0.0)
                period_cat_values[pid][cid] = val
                period_cat_values[pid][cname] = val

        formula_cats = [c for c in categories_data if c.get("category_type") == "FORMULA"]
        # Multi-pass evaluation to safely resolve chained formula dependencies (e.g. C = A + B, D = C * 0.18)
        max_passes = max(1, len(formula_cats))
        for _ in range(max_passes):
            for fcat in formula_cats:
                fdef = fcat.get("formula_definition")
                fc_id = fcat["category_id"]
                fc_name = fcat["category_name"].strip().lower()
                for p in periods:
                    pid = p["id"]
                    val = fe.evaluate_formula(fdef, period_cat_values[pid])
                    val = round(val, 2)
                    fcat["subtotal"]["amounts"][str(pid)] = val
                    period_cat_values[pid][fc_id] = val
                    period_cat_values[pid][fc_name] = val
                    if fcat["items"]:
                        fcat["items"][0]["amounts"][str(pid)] = val

        for fcat in formula_cats:
            fc_total = 0.0
            for p in periods:
                pid = p["id"]
                val = fcat["subtotal"]["amounts"].get(str(pid), 0.0)
                fc_total += val
                grand_total_by_period[pid] += val
                overall_grand_total += val
            fcat["subtotal"]["total"] = round(fc_total, 2)
            fcat["subtotal"]["avg"] = round(fc_total / num_periods, 2)
            if fcat["items"]:
                fcat["items"][0]["total"] = round(fc_total, 2)
                fcat["items"][0]["avg"] = round(fc_total / num_periods, 2)

        grand_total_data = {
            "amounts": {str(k): round(v, 2) for k, v in grand_total_by_period.items()},
            "total": round(overall_grand_total, 2),
            "avg": round(overall_grand_total / num_periods, 2)
        }

        # Query Dining Census / Headcounts (Students count, Staff count, Others, Total Persons, Production count)
        census_rows = []
        try:
            census_rows = db.execute_query("""
                SELECT period_id, active_students, active_staff, others_count, total_persons, production_meals
                FROM dining_census_entries
            """)
        except Exception as e:
            try:
                db.auto_migrate()
                census_rows = db.execute_query("""
                    SELECT period_id, active_students, active_staff, others_count, total_persons, production_meals
                    FROM dining_census_entries
                """)
            except Exception as inner_e:
                print(f"[Census Query Notice] {inner_e}")
                census_rows = []

        census_by_period = {r["period_id"]: r for r in census_rows}

        census_data = {
            "students": {str(p["id"]): (census_by_period.get(p["id"], {}).get("active_students") or 0) for p in periods},
            "staff": {str(p["id"]): (census_by_period.get(p["id"], {}).get("active_staff") or 0) for p in periods},
            "others": {str(p["id"]): (census_by_period.get(p["id"], {}).get("others_count") or 0) for p in periods},
            "total_persons": {str(p["id"]): (
                census_by_period.get(p["id"], {}).get("total_persons") or (
                    (census_by_period.get(p["id"], {}).get("active_students") or 0) +
                    (census_by_period.get(p["id"], {}).get("active_staff") or 0) +
                    (census_by_period.get(p["id"], {}).get("others_count") or 0)
                )
            ) for p in periods},
            "production": {str(p["id"]): (census_by_period.get(p["id"], {}).get("production_meals") or 0) for p in periods}
        }

        # Query Hostel Census / Operational Metrics (when module == 'hostel')
        hostel_census_data = {}
        try:
            h_rows = db.execute_query("SELECT * FROM hostel_census_entries")
            for hr in h_rows:
                h_dict = {
                    k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                    for k, v in hr.items()
                }
                c_metrics = hr.get("custom_metrics") or {}
                if isinstance(c_metrics, str):
                    try:
                        c_metrics = json.loads(c_metrics)
                    except Exception:
                        c_metrics = {}
                if isinstance(c_metrics, dict):
                    for ck, cv in c_metrics.items():
                        if ck not in h_dict:
                            h_dict[ck] = cv
                hostel_census_data[str(hr["period_id"])] = h_dict
        except Exception as he:
            print(f"[Hostel Census Query Notice] {he}")

        # Query Transport Census / Fleet Metrics
        transport_census_data = {}
        transport_census_by_branch = {b: {} for b in TRANSPORT_BRANCHES}
        try:
            t_rows = db.execute_query("SELECT * FROM transport_census_entries")
            for tr in t_rows:
                b = tr.get("branch") or "Common"
                p_str = str(tr["period_id"])
                conv = {
                    k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                    for k, v in tr.items()
                }
                transport_census_by_branch.setdefault(b, {})[p_str] = conv

            if module == "transport" and branch and branch != "all" and branch in transport_census_by_branch:
                transport_census_data = transport_census_by_branch[branch]
            else:
                for p in periods:
                    p_str = str(p["id"])
                    c_veh_list = []
                    tot_passengers = 0
                    tot_students = 0
                    tot_staff = 0
                    tot_approved_kms = 0.0
                    tot_actual_kms = 0.0
                    tot_additional_kms = 0.0
                    tot_diesel_litres = 0.0
                    tot_fuel_expenses = 0.0
                    tot_fee_demand = 0.0
                    tot_fee_collected = 0.0
                    tot_fee_unpaid = 0.0
                    tot_approved_budget = 0.0
                    tot_cumulative_budget_spent = 0.0
                    tot_tickets_raised = 0
                    tot_tickets_closed = 0
                    tot_tickets_open = 0
                    tot_incidents = 0
                    has_data = False

                    for b in TRANSPORT_BRANCHES:
                        b_census = transport_census_by_branch.get(b, {}).get(p_str)
                        if b_census:
                            has_data = True
                            if b_census.get("vehicles_count"):
                                c_veh_list.append(f"{b}: {b_census['vehicles_count']}")
                            tot_passengers += int(b_census.get("passengers_count") or 0)
                            tot_students += int(b_census.get("students_count") or 0)
                            tot_staff += int(b_census.get("staff_count") or 0)
                            tot_approved_kms += float(b_census.get("approved_kms") or 0.0)
                            tot_actual_kms += float(b_census.get("actual_kms") or 0.0)
                            tot_additional_kms += float(b_census.get("additional_kms") or 0.0)
                            tot_diesel_litres += float(b_census.get("diesel_litres") or 0.0)
                            tot_fuel_expenses += float(b_census.get("fuel_expenses") or 0.0)
                            tot_fee_demand += float(b_census.get("fee_demand") or 0.0)
                            tot_fee_collected += float(b_census.get("fee_collected") or 0.0)
                            tot_fee_unpaid += float(b_census.get("fee_unpaid") or 0.0)
                            tot_approved_budget += float(b_census.get("approved_budget") or 0.0)
                            tot_cumulative_budget_spent += float(b_census.get("cumulative_budget_spent") or 0.0)
                            tot_tickets_raised += int(b_census.get("service_tickets_raised") or 0)
                            tot_tickets_closed += int(b_census.get("service_tickets_closed") or 0)
                            tot_tickets_open += int(b_census.get("service_tickets_open") or 0)
                            tot_incidents += int(b_census.get("incidents_count") or 0)

                    if has_data:
                        transport_census_data[p_str] = {
                            "vehicles_count": " / ".join(c_veh_list) if c_veh_list else "64 fleet",
                            "passengers_count": tot_passengers,
                            "students_count": tot_students,
                            "staff_count": tot_staff,
                            "approved_kms": round(tot_approved_kms, 2),
                            "actual_kms": round(tot_actual_kms, 2),
                            "additional_kms": round(tot_additional_kms, 2),
                            "diesel_litres": round(tot_diesel_litres, 2),
                            "fuel_expenses": round(tot_fuel_expenses, 2),
                            "fee_demand": round(tot_fee_demand, 2),
                            "fee_collected": round(tot_fee_collected, 2),
                            "fee_unpaid": round(tot_fee_unpaid, 2),
                            "approved_budget": round(tot_approved_budget, 2),
                            "cumulative_budget_spent": round(tot_cumulative_budget_spent, 2),
                            "balance": round(tot_approved_budget - tot_cumulative_budget_spent, 2),
                            "service_tickets_raised": tot_tickets_raised,
                            "service_tickets_closed": tot_tickets_closed,
                            "service_tickets_open": tot_tickets_open,
                            "incidents_count": tot_incidents,
                            "statutory_compliance": 1
                        }
                    elif p_str in transport_census_by_branch.get("Common", {}):
                        transport_census_data[p_str] = transport_census_by_branch["Common"][p_str]
        except Exception as te:
            print(f"[Transport Census Query Notice] {te}")

        return {
            "periods": periods,
            "categories": categories_data,
            "grand_total": grand_total_data,
            "census": census_data,
            "hostel_census": hostel_census_data,
            "transport_census": transport_census_data,
            "transport_census_by_branch": transport_census_by_branch if module == "transport" else None,
            "matrix_by_branch": matrix_by_branch if module == "transport" else None,
            "branches": ["all", "RPS", "KPM", "Common", "University"] if module == "transport" else None,
            "active_branch": branch or "all"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mom-variance")
def get_mom_variance():
    try:
        rows = db.execute_query("SELECT * FROM vw_food_mom_variance ORDER BY category_name, line_item")
        res = []
        for r in rows:
            res.append({
                "period_label": r["period_label"],
                "category_name": r["category_name"],
                "line_item": r["line_item"],
                "current_amount": float(r["current_amount"]) if r["current_amount"] is not None else 0,
                "prev_month_amount": float(r["prev_month_amount"]) if r["prev_month_amount"] is not None else None,
                "mom_diff_inr": float(r["mom_diff_inr"]) if r["mom_diff_inr"] is not None else None,
                "mom_growth_pct": float(r["mom_growth_pct"]) if r["mom_growth_pct"] is not None else None
            })
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master-data")
def get_master_data(module: Optional[str] = "food"):
    try:
        if module and module != "all":
            periods = db.execute_query(
                "SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module "
                "FROM billing_periods WHERE module = %s ORDER BY start_date",
                (module,)
            )
            categories = db.execute_query(
                "SELECT id, code, name, display_order, is_active, module FROM expense_categories WHERE is_active = true AND module = %s ORDER BY display_order",
                (module,)
            )
        else:
            periods = db.execute_query("SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module FROM billing_periods ORDER BY start_date")
            categories = db.execute_query("SELECT id, code, name, display_order, is_active, module FROM expense_categories WHERE is_active = true ORDER BY display_order")
        cost_heads = db.execute_query("""
            SELECT ch.id, ch.category_id, c.name AS category_name, ch.code, ch.name, ch.cost_behavior, ch.display_order, ch.default_vendor_id, ch.is_active, v.name AS default_vendor_name
            FROM cost_heads ch
            JOIN expense_categories c ON ch.category_id = c.id
            LEFT JOIN vendors v ON ch.default_vendor_id = v.id
            WHERE ch.is_active = true
            ORDER BY c.display_order, ch.display_order
        """)
        vendors = db.execute_query("SELECT id, vendor_code, name, vendor_type FROM vendors WHERE is_active = true ORDER BY id")
        
        return {
            "periods": periods,
            "categories": categories,
            "cost_heads": cost_heads,
            "vendors": vendors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# MASTER DATA MANAGEMENT CRUD & REORDER (DRAG & DROP)
# -------------------------------------------------------------
@app.get("/api/master/cost-heads")
def get_all_cost_heads(module: Optional[str] = None, include_inactive: bool = False):
    try:
        conditions = []
        params = []
        if not include_inactive:
            conditions.append("ch.is_active = true")
        if module and module != "all":
            conditions.append("c.module = %s")
            params.append(module)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
        SELECT 
            ch.id,
            ch.category_id,
            c.name AS category_name,
            c.code AS category_code,
            c.module,
            ch.name AS name,
            ch.code AS code,
            ch.cost_behavior,
            ch.display_order,
            ch.default_vendor_id,
            v.name AS vendor_name,
            ch.is_active,
            (SELECT COUNT(*) FROM monthly_expense_entries WHERE cost_head_id = ch.id) AS entry_count
        FROM cost_heads ch
        JOIN expense_categories c ON ch.category_id = c.id
        LEFT JOIN vendors v ON ch.default_vendor_id = v.id
        {where_clause}
        ORDER BY c.display_order, ch.display_order;
        """
        return db.execute_query(query, tuple(params) if params else None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/cost-heads")
def create_cost_head(req: CostHeadCreate):
    try:
        code = req.code
        if not code or not code.strip():
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', req.name).strip('_').upper()
            code = f"CH_{clean[:20]}"
        
        behavior = req.cost_behavior or "variable"

        display_order = req.display_order
        if display_order is None:
            max_row = db.execute_query(
                "SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM cost_heads WHERE category_id = %s",
                (req.category_id,),
                fetch_all=False
            )
            display_order = max_row["next_order"] if max_row else 10

        insert_sql = """
        INSERT INTO cost_heads (category_id, name, code, cost_behavior, default_vendor_id, display_order, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, true)
        RETURNING id, name, code, display_order;
        """
        new_row = db.execute_query(
            insert_sql,
            (req.category_id, req.name.strip(), code, behavior, req.default_vendor_id, display_order),
            fetch_all=False
        )
        return {"status": "success", "message": f"Cost head '{req.name}' created successfully", "cost_head": new_row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/master/cost-heads/{cost_head_id}")
def update_cost_head(cost_head_id: int, req: CostHeadUpdate):
    try:
        existing = db.execute_query("SELECT id, category_id, code, cost_behavior, default_vendor_id FROM cost_heads WHERE id = %s", (cost_head_id,), fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Cost head not found")

        cat_id = req.category_id if req.category_id is not None else existing["category_id"]
        code = req.code or existing["code"]
        behavior = req.cost_behavior or existing["cost_behavior"] or "variable"
        vendor_id = req.default_vendor_id if req.default_vendor_id is not None else existing["default_vendor_id"]
        is_active = req.is_active if req.is_active is not None else True

        update_sql = """
        UPDATE cost_heads
        SET 
            category_id = %s,
            name = %s,
            code = %s,
            cost_behavior = %s,
            default_vendor_id = %s,
            display_order = COALESCE(%s, display_order),
            is_active = %s
        WHERE id = %s;
        """
        db.execute_commit(
            update_sql,
            (cat_id, req.name.strip(), code, behavior, vendor_id, req.display_order, is_active, cost_head_id)
        )
        return {"status": "success", "message": "Cost head updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/reorder-cost-heads")
def reorder_cost_heads(req: ReorderCostHeadsRequest):
    """
    Updates the display order of cost heads following a drag-and-drop event.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for idx, ch_id in enumerate(req.cost_head_ids, start=1):
                    cur.execute("UPDATE cost_heads SET display_order = %s WHERE id = %s", (idx, ch_id))
                conn.commit()
                return {"status": "success", "message": "Cost heads reordered successfully in database"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/master/cost-heads/{cost_head_id}")
def delete_cost_head(cost_head_id: int):
    try:
        entry_count = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM monthly_expense_entries WHERE cost_head_id = %s",
            (cost_head_id,),
            fetch_all=False
        )["cnt"]

        if entry_count > 0:
            db.execute_commit("UPDATE cost_heads SET is_active = false WHERE id = %s", (cost_head_id,))
            return {
                "status": "deactivated",
                "message": f"Cost head has {entry_count} historical financial entries; soft-deactivated to preserve ledger audit trail."
            }
        else:
            db.execute_commit("DELETE FROM cost_heads WHERE id = %s", (cost_head_id,))
            return {"status": "deleted", "message": "Cost head deleted permanently"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/cost-heads/batch-delete")
def batch_delete_cost_heads(req: BatchDeleteRequest):
    try:
        if not req.ids:
            return {"status": "success", "deleted": 0, "deactivated": 0, "message": "No items chosen"}
        
        deleted = 0
        deactivated = 0
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for ch_id in req.ids:
                    cur.execute("SELECT COUNT(*) FROM monthly_expense_entries WHERE cost_head_id = %s", (ch_id,))
                    cnt = cur.fetchone()[0]
                    if cnt > 0:
                        cur.execute("UPDATE cost_heads SET is_active = false WHERE id = %s", (ch_id,))
                        deactivated += 1
                    else:
                        cur.execute("DELETE FROM cost_heads WHERE id = %s", (ch_id,))
                        deleted += 1
                conn.commit()
            return {
                "status": "success",
                "deleted": deleted,
                "deactivated": deactivated,
                "message": f"Successfully deleted {deleted + deactivated} selected line item(s)."
            }
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master/categories")
def get_categories(module: Optional[str] = None):
    try:
        select_cols = """
            c.id, c.code, c.name, c.display_order, c.is_active, c.module,
            c.category_type, c.formula_expression, c.formula_definition, c.formula_version, c.updated_at,
            COUNT(ch.id) AS cost_head_count
        """
        group_cols = """
            c.id, c.code, c.name, c.display_order, c.is_active, c.module,
            c.category_type, c.formula_expression, c.formula_definition, c.formula_version, c.updated_at
        """
        if module and module != "all":
            cats = db.execute_query(f"""
                SELECT {select_cols}
                FROM expense_categories c
                LEFT JOIN cost_heads ch ON c.id = ch.category_id AND ch.is_active = true
                WHERE c.is_active = true AND c.module = %s
                GROUP BY {group_cols}
                ORDER BY c.display_order;
            """, (module,))
        else:
            cats = db.execute_query(f"""
                SELECT {select_cols}
                FROM expense_categories c
                LEFT JOIN cost_heads ch ON c.id = ch.category_id AND ch.is_active = true
                WHERE c.is_active = true
                GROUP BY {group_cols}
                ORDER BY c.display_order;
            """)
        for cat in cats:
            fdef = cat.get("formula_definition")
            if isinstance(fdef, str):
                try:
                    cat["formula_definition"] = json.loads(fdef)
                except Exception:
                    cat["formula_definition"] = None
        return cats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/categories")
def create_category(req: CategoryCreate):
    try:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Category name cannot be empty")

        code = req.code
        if not code or not code.strip():
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').upper()
            if not clean:
                clean = "EXPENSE"
            code = f"CAT_{clean[:20]}"
        else:
            code = code.strip().upper()

        # Ensure unique code to prevent duplicate key constraint violations
        existing = db.execute_query("SELECT id FROM expense_categories WHERE code = %s", (code,), fetch_all=False)
        counter = 1
        base_code = code
        while existing:
            code = f"{base_code[:16]}_{counter}"
            existing = db.execute_query("SELECT id FROM expense_categories WHERE code = %s", (code,), fetch_all=False)
            counter += 1

        display_order = req.display_order
        if display_order is None:
            max_row = db.execute_query("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM expense_categories", fetch_all=False)
            display_order = max_row["next_order"] if max_row else 10

        mod = req.module or "food"
        cat_type = (req.category_type or "DIRECT").upper()
        if cat_type not in ("DIRECT", "FORMULA"):
            cat_type = "DIRECT"

        formula_expr = req.formula_expression.strip() if req.formula_expression else None
        formula_def = req.formula_definition

        if cat_type == "FORMULA":
            if not formula_expr:
                raise HTTPException(status_code=400, detail="Formula expression is required for formula-based category")
            
            all_cats = db.execute_query("SELECT id, name, code, category_type, formula_definition FROM expense_categories WHERE is_active = true")
            try:
                norm_expr, id_expr, cat_ids, cat_names = fe.normalize_expression(formula_expr, all_cats)
                has_cycle, cycle_err = fe.detect_circular_dependencies(all_cats, None, cat_ids)
                if has_cycle:
                    raise HTTPException(status_code=400, detail=cycle_err or "Circular dependency detected")
                
                # Test parse to tokens and rpn to ensure valid syntax
                tokens = fe.tokenize(id_expr)
                fe.to_rpn(tokens)
                
                formula_def = {
                    "raw_expression": formula_expr,
                    "normalized_expression": norm_expr,
                    "id_expression": id_expr,
                    "category_ids": cat_ids,
                    "category_names": cat_names
                }
                formula_expr = norm_expr
            except fe.FormulaError as fe_err:
                raise HTTPException(status_code=400, detail=str(fe_err))

        f_def_json = json.dumps(formula_def) if formula_def else None

        insert_sql = """
        INSERT INTO expense_categories (name, code, display_order, is_active, module, category_type, formula_expression, formula_definition, formula_version) 
        VALUES (%s, %s, %s, true, %s, %s, %s, %s, %s) 
        RETURNING id, name, code, display_order, module, category_type, formula_expression, formula_definition, formula_version;
        """
        cat = db.execute_query(insert_sql, (name, code, display_order, mod, cat_type, formula_expr, f_def_json, req.formula_version or 1), fetch_all=False)

        # Automatically create a default line item so it appears in spreadsheets and matrix
        db.execute_commit("""
            INSERT INTO cost_heads (category_id, name, code, cost_behavior, display_order, is_active)
            VALUES (%s, %s, %s, 'fixed', 1, true)
            ON CONFLICT DO NOTHING
        """, (cat["id"], name, f"{code}_HEAD"))

        return {
            "status": "success",
            "message": f"Category '{name}' created successfully",
            "category": cat
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/master/categories/{category_id}")
def update_category(category_id: int, req: CategoryUpdate):
    try:
        existing = db.execute_query(
            "SELECT id, name, code, display_order, is_active, module, category_type, formula_expression, formula_definition FROM expense_categories WHERE id = %s",
            (category_id,),
            fetch_all=False
        )
        if not existing:
            raise HTTPException(status_code=404, detail=f"Category ID {category_id} not found")

        name = req.name.strip() if req.name and req.name.strip() else existing["name"]
        display_order = req.display_order if req.display_order is not None else existing["display_order"]
        is_active = req.is_active if req.is_active is not None else existing["is_active"]
        module = req.module.strip() if (req.module and req.module.strip()) else existing["module"]
        cat_type = req.category_type.upper() if req.category_type else (existing.get("category_type") or "DIRECT")

        code = existing["code"]
        if req.code and req.code.strip():
            new_code = req.code.strip().upper()
            if new_code != existing["code"]:
                dup = db.execute_query(
                    "SELECT id FROM expense_categories WHERE code = %s AND id != %s",
                    (new_code, category_id),
                    fetch_all=False
                )
                if dup:
                    raise HTTPException(status_code=400, detail=f"Category code '{new_code}' is already in use by another category")
                code = new_code

        formula_expr = req.formula_expression if req.formula_expression is not None else existing.get("formula_expression")
        formula_def = req.formula_definition if req.formula_definition is not None else existing.get("formula_definition")

        if cat_type == "FORMULA":
            if not formula_expr or not formula_expr.strip():
                raise HTTPException(status_code=400, detail="Formula expression is required for formula-based category")
            
            all_cats = db.execute_query("SELECT id, name, code, category_type, formula_definition FROM expense_categories WHERE is_active = true AND id != %s", (category_id,))
            try:
                norm_expr, id_expr, cat_ids, cat_names = fe.normalize_expression(formula_expr, all_cats)
                has_cycle, cycle_err = fe.detect_circular_dependencies(all_cats, category_id, cat_ids)
                if has_cycle:
                    raise HTTPException(status_code=400, detail=cycle_err or "Circular dependency detected")
                
                # Test parse to tokens and rpn
                tokens = fe.tokenize(id_expr)
                fe.to_rpn(tokens)
                
                formula_def = {
                    "raw_expression": formula_expr,
                    "normalized_expression": norm_expr,
                    "id_expression": id_expr,
                    "category_ids": cat_ids,
                    "category_names": cat_names
                }
                formula_expr = norm_expr
            except fe.FormulaError as fe_err:
                raise HTTPException(status_code=400, detail=str(fe_err))

        f_def_json = json.dumps(formula_def) if (formula_def and isinstance(formula_def, dict)) else (formula_def if isinstance(formula_def, str) else None)

        update_sql = """
        UPDATE expense_categories 
        SET name = %s, code = %s, display_order = %s, is_active = %s, module = %s,
            category_type = %s, formula_expression = %s, formula_definition = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING id, name, code, display_order, is_active, module, category_type, formula_expression, formula_definition, updated_at;
        """
        updated = db.execute_query(update_sql, (name, code, display_order, is_active, module, cat_type, formula_expr, f_def_json, category_id), fetch_all=False)
        return {
            "status": "success",
            "message": f"Category '{name}' updated successfully",
            "category": updated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/master/categories/{category_id}")
def delete_category(category_id: int):
    """
    Delete or deactivate an expense category. Checks for historical entries and formula references first.
    """
    try:
        # Check if another formula-based category references this category_id
        cat_row = db.execute_query("SELECT name FROM expense_categories WHERE id = %s", (category_id,), fetch_all=False)
        if cat_row:
            cat_name = cat_row["name"]
            other_formula_cats = db.execute_query("""
                SELECT id, name, formula_expression, formula_definition 
                FROM expense_categories 
                WHERE is_active = true AND id != %s AND category_type = 'FORMULA'
            """, (category_id,))
            ref_names = []
            for ofc in other_formula_cats:
                fdef = ofc.get("formula_definition")
                if isinstance(fdef, str):
                    try:
                        fdef = json.loads(fdef)
                    except Exception:
                        fdef = None
                if fdef and isinstance(fdef, dict):
                    cids = fdef.get("category_ids") or []
                    if category_id in cids:
                        ref_names.append(ofc["name"])
                elif ofc.get("formula_expression") and cat_name.lower() in ofc["formula_expression"].lower():
                    ref_names.append(ofc["name"])
            
            if ref_names:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot delete category '{cat_name}' because it is referenced in the formula of: {', '.join(set(ref_names))}. Please update or remove those formulas first."
                )

        cost_heads = db.execute_query("SELECT id FROM cost_heads WHERE category_id = %s", (category_id,))
        if cost_heads:
            ch_ids = [ch["id"] for ch in cost_heads]
            placeholders = ','.join(['%s'] * len(ch_ids))
            entry_cnt = db.execute_query(
                f"SELECT COUNT(*) AS cnt FROM monthly_expense_entries WHERE cost_head_id IN ({placeholders})",
                tuple(ch_ids),
                fetch_all=False
            )["cnt"]
            if entry_cnt > 0:
                # Soft deactivate category and associated cost heads to preserve historical audit trail
                db.execute_commit("UPDATE expense_categories SET is_active = false WHERE id = %s", (category_id,))
                db.execute_commit(f"UPDATE cost_heads SET is_active = false WHERE category_id = %s", (category_id,))
                return {
                    "status": "deactivated",
                    "message": f"Category has {entry_cnt} associated expense ledger entries; deactivated to preserve historical audit trail."
                }
            else:
                db.execute_commit(f"DELETE FROM cost_heads WHERE category_id = %s", (category_id,))
                db.execute_commit("DELETE FROM expense_categories WHERE id = %s", (category_id,))
                return {"status": "deleted", "message": "Category and unused cost heads permanently deleted."}
        else:
            db.execute_commit("DELETE FROM expense_categories WHERE id = %s", (category_id,))
            return {"status": "deleted", "message": "Category permanently deleted."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/categories/batch-delete")
def batch_delete_categories(req: BatchDeleteRequest):
    try:
        if not req.ids:
            return {"status": "success", "deleted": 0, "deactivated": 0, "message": "No categories chosen"}
        
        # Check if any chosen category is referenced by another formula category not in req.ids
        other_formula_cats = db.execute_query("""
            SELECT id, name, formula_expression, formula_definition 
            FROM expense_categories 
            WHERE is_active = true AND category_type = 'FORMULA'
        """)
        for cat_id in req.ids:
            cat_row = db.execute_query("SELECT name FROM expense_categories WHERE id = %s", (cat_id,), fetch_all=False)
            if not cat_row:
                continue
            cat_name = cat_row["name"]
            for ofc in other_formula_cats:
                if ofc["id"] in req.ids:
                    continue  # Both are being deleted
                fdef = ofc.get("formula_definition")
                if isinstance(fdef, str):
                    try:
                        fdef = json.loads(fdef)
                    except Exception:
                        fdef = None
                if fdef and isinstance(fdef, dict):
                    cids = fdef.get("category_ids") or []
                    if cat_id in cids:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot delete category '{cat_name}' because it is referenced in the formula of: {ofc['name']}."
                        )
                elif ofc.get("formula_expression") and cat_name.lower() in ofc["formula_expression"].lower():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot delete category '{cat_name}' because it is referenced in the formula of: {ofc['name']}."
                    )

        deleted = 0
        deactivated = 0
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for cat_id in req.ids:
                    cur.execute("SELECT id FROM cost_heads WHERE category_id = %s", (cat_id,))
                    ch_rows = cur.fetchall()
                    ch_ids = [r[0] for r in ch_rows]
                    has_entries = False
                    if ch_ids:
                        placeholders = ','.join(['%s'] * len(ch_ids))
                        cur.execute(f"SELECT COUNT(*) FROM monthly_expense_entries WHERE cost_head_id IN ({placeholders})", tuple(ch_ids))
                        if cur.fetchone()[0] > 0:
                            has_entries = True
                    
                    if has_entries:
                        cur.execute("UPDATE expense_categories SET is_active = false WHERE id = %s", (cat_id,))
                        cur.execute("UPDATE cost_heads SET is_active = false WHERE category_id = %s", (cat_id,))
                        deactivated += 1
                    else:
                        cur.execute("DELETE FROM cost_heads WHERE category_id = %s", (cat_id,))
                        cur.execute("DELETE FROM expense_categories WHERE id = %s", (cat_id,))
                        deleted += 1
                conn.commit()
            return {
                "status": "success",
                "deleted": deleted,
                "deactivated": deactivated,
                "message": f"Successfully processed {deleted + deactivated} selected category(ies)."
            }
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/categories/reorder")
@app.post("/api/master/reorder-categories")
def reorder_categories(req: ReorderCategoriesRequest):
    """
    Updates the display order of categories following a drag-and-drop or move step event.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for idx, cat_id in enumerate(req.category_ids, start=1):
                    cur.execute("UPDATE expense_categories SET display_order = %s WHERE id = %s", (idx, cat_id))
                conn.commit()
                return {"status": "success", "message": "Categories reordered successfully in database"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# CATEGORY FORMULAS & FUNCTIONS CRUD
# -------------------------------------------------------------
@app.get("/api/master/category-formulas")
def get_category_formulas(module: Optional[str] = None):
    try:
        query = "SELECT * FROM category_formulas"
        params = []
        if module:
            query += " WHERE LOWER(module) = %s"
            params.append(module.lower())
        query += " ORDER BY display_order ASC, id ASC;"
        res = db.execute_query(query, params)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/category-formulas")
def create_category_formula(req: CategoryFormulaCreate):
    try:
        mod = (req.module or "food").lower()
        query = """
            INSERT INTO category_formulas (module, name, expression, description, unit_type, display_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, module, name, expression, description, unit_type, display_order, created_at, updated_at;
        """
        row = db.execute_query(query, (
            mod,
            req.name.strip(),
            req.expression.strip(),
            req.description or "",
            req.unit_type or "currency",
            req.display_order or 0
        ), fetch_all=False)
        return row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/master/category-formulas/{formula_id}")
def update_category_formula(formula_id: int, req: CategoryFormulaUpdate):
    try:
        updates = []
        params = []
        if req.name is not None:
            updates.append("name = %s")
            params.append(req.name.strip())
        if req.expression is not None:
            updates.append("expression = %s")
            params.append(req.expression.strip())
        if req.description is not None:
            updates.append("description = %s")
            params.append(req.description)
        if req.unit_type is not None:
            updates.append("unit_type = %s")
            params.append(req.unit_type)
        if req.display_order is not None:
            updates.append("display_order = %s")
            params.append(req.display_order)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        updates.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE category_formulas SET {', '.join(updates)} WHERE id = %s RETURNING id, module, name, expression, description, unit_type, display_order, created_at, updated_at;"
        params.append(formula_id)
        row = db.execute_query(query, params, fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="Formula not found")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/master/category-formulas/{formula_id}")
def delete_category_formula(formula_id: int):
    try:
        query = "DELETE FROM category_formulas WHERE id = %s RETURNING id;"
        row = db.execute_query(query, (formula_id,), fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="Formula not found")
        return {"status": "success", "message": "Formula deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# HOSTEL MASTER PARAMETERS CRUD ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/hostel/parameters")
def get_hostel_parameters():
    """
    Returns the list of active hostel master parameters grouped into sections.
    """
    try:
        rows = db.execute_query(
            """
            SELECT id, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM hostel_master_parameters
            WHERE is_active = TRUE
            ORDER BY section_order ASC, display_order ASC, id ASC;
            """
        )
        return rows or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hostel/parameters")
def create_hostel_parameter(req: Dict[str, Any]):
    """
    Creates a new hostel parameter row in Master Data.
    """
    try:
        param_name = (req.get("param_name") or "").strip()
        if not param_name:
            raise HTTPException(status_code=400, detail="Parameter name is required")

        section = (req.get("section") or "Custom Parameters").strip()
        section_order = int(req.get("section_order") or 7)
        input_type = (req.get("input_type") or "cost").strip()
        unit = (req.get("unit") or "").strip()
        formula = req.get("formula") or None
        display_order = int(req.get("display_order") or 50)

        # Generate a safe unique param_key
        base_key = re.sub(r'[^a-z0-9_]', '', param_name.lower().replace(' ', '_'))
        if not base_key:
            base_key = f"param_{int(datetime.now().timestamp())}"
        param_key = base_key

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Check collision
                cur.execute("SELECT id FROM hostel_master_parameters WHERE param_key = %s;", (param_key,))
                if cur.fetchone():
                    param_key = f"{base_key}_{int(datetime.now().timestamp())}"

                cur.execute(
                    """
                    INSERT INTO hostel_master_parameters (
                        param_key, param_name, section, section_order,
                        input_type, unit, formula, display_order, is_system, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE)
                    RETURNING id, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                    """,
                    (param_key, param_name, section, section_order, input_type, unit, formula, display_order)
                )
                new_row = cur.fetchone()
                conn.commit()
                col_names = [d[0] for d in cur.description]
                res_dict = dict(zip(col_names, new_row))
                return {
                    "status": "success",
                    "message": f"Created parameter '{param_name}' successfully",
                    "parameter": res_dict
                }
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/hostel/parameters/{param_id}")
def update_hostel_parameter(param_id: int, req: Dict[str, Any]):
    """
    Updates an existing hostel parameter (name, section, formula, input_type, display_order).
    """
    try:
        fields = []
        vals = []
        if "param_name" in req:
            fields.append("param_name = %s")
            vals.append(str(req["param_name"]).strip())
        if "section" in req:
            fields.append("section = %s")
            vals.append(str(req["section"]).strip())
        if "section_order" in req:
            fields.append("section_order = %s")
            vals.append(int(req["section_order"]))
        if "input_type" in req:
            fields.append("input_type = %s")
            vals.append(str(req["input_type"]).strip())
        if "unit" in req:
            fields.append("unit = %s")
            vals.append(str(req["unit"]).strip())
        if "formula" in req:
            fields.append("formula = %s")
            vals.append(req["formula"])
        if "display_order" in req:
            fields.append("display_order = %s")
            vals.append(int(req["display_order"]))
        if "is_active" in req:
            fields.append("is_active = %s")
            vals.append(bool(req["is_active"]))

        if not fields:
            return {"status": "success", "message": "No changes requested"}

        vals.append(param_id)
        query = f"UPDATE hostel_master_parameters SET {', '.join(fields)} WHERE id = %s RETURNING id, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;"
        row = db.execute_query(query, tuple(vals), fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="Hostel parameter not found")
        return {
            "status": "success",
            "message": "Hostel parameter updated successfully",
            "parameter": row
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/hostel/parameters/{param_id}")
def delete_hostel_parameter(param_id: int):
    """
    Soft-deletes or removes a hostel parameter.
    """
    try:
        param = db.execute_query("SELECT id, is_system FROM hostel_master_parameters WHERE id = %s;", (param_id,), fetch_all=False)
        if not param:
            raise HTTPException(status_code=404, detail="Parameter not found")

        db.execute_commit("UPDATE hostel_master_parameters SET is_active = FALSE WHERE id = %s;", (param_id,))
        return {"status": "success", "message": "Parameter removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# HOSTEL CENSUS CALCULATION & PERSISTENCE HELPER
# -------------------------------------------------------------
def _clean_num(val, default=0.0):
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return val
    try:
        s = str(val).replace(",", "").replace("%", "").strip()
        return float(s) if "." in s else int(s)
    except Exception:
        return default

def compute_and_upsert_hostel_census(cur, period_id: int, hc: Dict[str, Any]):
    cur.execute("SELECT * FROM hostel_census_entries WHERE period_id = %s;", (period_id,))
    existing_row = cur.fetchone()
    existing = {}
    if existing_row:
        if isinstance(existing_row, dict):
            existing = existing_row
        elif hasattr(cur, 'description') and cur.description:
            col_names = [desc[0] for desc in cur.description]
            existing = dict(zip(col_names, existing_row))

    def get_f(key, fallback):
        if key in hc and hc[key] is not None and hc[key] != "":
            return hc[key]
        if key in existing and existing[key] is not None:
            return existing[key]
        return fallback

    bc_b = int(_clean_num(get_f("bed_capacity_boys", 2223)))
    bc_g = int(_clean_num(get_f("bed_capacity_girls", 896)))
    bc_tot = bc_b + bc_g

    st_b = int(_clean_num(get_f("students_boys", 2075)))
    st_g = int(_clean_num(get_f("students_girls", 768)))
    st_tot = st_b + st_g

    sf_b = int(_clean_num(get_f("staff_boys", 72)))
    sf_g = int(_clean_num(get_f("staff_girls", 59)))
    sf_tot = sf_b + sf_g

    occ_b = st_b + sf_b
    occ_g = st_g + sf_g
    occ_tot = occ_b + occ_g

    vac_b = bc_b - occ_b
    vac_g = bc_g - occ_g
    vac_tot = vac_b + vac_g

    vac_coll_b = int(_clean_num(get_f("vacant_college_boys", vac_b - 41)))
    vac_coll_g = int(_clean_num(get_f("vacant_college_girls", vac_g)))
    vac_coll_tot = vac_coll_b + vac_coll_g

    vac_sp_b = int(_clean_num(get_f("vacant_sports_boys", 0)))
    vac_sp_g = int(_clean_num(get_f("vacant_sports_girls", 0)))
    vac_sp_tot = vac_sp_b + vac_sp_g

    vac_sc_b = int(_clean_num(get_f("vacant_school_boys", 0)))
    vac_sc_g = int(_clean_num(get_f("vacant_school_girls", 0)))
    vac_sc_tot = vac_sc_b + vac_sc_g

    occ_pct_b = round((occ_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    occ_pct_g = round((occ_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    occ_pct = round((occ_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    vac_pct_b = round((vac_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    vac_pct_g = round((vac_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    vac_pct = round((vac_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    st_vacated = int(_clean_num(get_f("students_vacated", 0)))

    t_rec = int(_clean_num(get_f("tickets_received", 0)))
    t_cls = int(_clean_num(get_f("tickets_closed", 0)))
    t_opn = max(0, t_rec - t_cls)

    tot_hrs = float(_clean_num(get_f("total_hours_close", 0.0)))
    tat_hrs = float(_clean_num(get_f("tat_hours", 62.29)))

    q_rec = int(_clean_num(get_f("quality_issues_received", 0)))
    q_cls = int(_clean_num(get_f("quality_issues_closed", 0)))
    q_opn = max(0, q_rec - q_cls)

    incidents = int(_clean_num(get_f("incidents_count", 0)))

    p_units = int(_clean_num(get_f("power_units", 0)))
    p_cost = float(_clean_num(get_f("power_cost", 0.0)))
    w_pur = float(_clean_num(get_f("water_purchase_cost", 0.0)))
    maint_exp = float(_clean_num(get_f("maintenance_expenses", 119394.0)))
    exp_occ = float(_clean_num(get_f("expenses_occurred", 9349172.0)))

    app_bud = float(_clean_num(get_f("approved_budget", 131788118.0)))
    cum_bud = float(_clean_num(get_f("cumulative_budget_spent", 0.0)))
    bal = app_bud - cum_bud

    nw_ltr = int(_clean_num(get_f("normal_water_litres", 0)))
    nw_cost = float(_clean_num(get_f("normal_water_cost", 0.0)))
    dw_ltr = int(_clean_num(get_f("drinking_water_litres", 0)))
    dw_cost = float(_clean_num(get_f("drinking_water_cost", 0.0)))

    sq_ft = float(_clean_num(get_f("sq_feet", 231701.0)))
    per_st_mo = round(exp_occ / st_tot, 2) if st_tot > 0 else 0.0
    per_st_day = round(per_st_mo / 30.0, 2)
    sq_ft_occ = round(sq_ft / occ_tot, 2) if occ_tot > 0 else (round(sq_ft / st_tot, 2) if st_tot > 0 else 0.0)

    nw_st_ltr = round(nw_ltr / st_tot, 2) if st_tot > 0 else float(_clean_num(get_f("normal_water_student_ltrs", 0.0)))
    nw_st_cost = round(nw_cost / st_tot, 2) if st_tot > 0 else float(_clean_num(get_f("normal_water_student_cost", 88.0)))

    p_sqft = round(p_cost / sq_ft, 2) if sq_ft > 0 else 0.0
    p_occ_u = round(p_units / occ_tot, 2) if occ_tot > 0 else 0.0
    p_occ_c = round(p_cost / occ_tot, 2) if occ_tot > 0 else 0.0

    nw_day_ltr = round(nw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    nw_day_c = round(nw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    dw_day_ltr = round(dw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    dw_day_c = round(dw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    remarks = str(hc.get("remarks") or "")

    custom_metrics = hc.get("custom_metrics")
    if not isinstance(custom_metrics, dict):
        custom_metrics = existing.get("custom_metrics") or {}
        if isinstance(custom_metrics, str):
            try:
                custom_metrics = json.loads(custom_metrics)
            except Exception:
                custom_metrics = {}
    if not isinstance(custom_metrics, dict):
        custom_metrics = {}

    for k, v in hc.items():
        if k not in (
            "id", "period_id", "created_at", "bed_capacity_boys", "bed_capacity_girls", "bed_capacity_total",
            "students_boys", "students_girls", "students_total", "staff_boys", "staff_girls", "staff_total",
            "total_occupied_boys", "total_occupied_girls", "total_occupied", "vacant_boys", "vacant_girls",
            "vacant_total", "vacant_college_boys", "vacant_college_girls", "vacant_college", "vacant_sports_boys",
            "vacant_sports_girls", "vacant_sports_total", "vacant_school_boys", "vacant_school_girls",
            "vacant_school_total", "occupied_pct_boys", "occupied_pct_girls", "occupied_pct", "vacant_pct_boys",
            "vacant_pct_girls", "vacant_pct", "students_vacated", "tickets_received", "tickets_closed",
            "tickets_open", "total_hours_close", "tat_hours", "quality_issues_received", "quality_issues_closed",
            "quality_issues_open", "incidents_count", "power_units", "power_cost", "water_purchase_cost",
            "maintenance_expenses", "expenses_occurred", "approved_budget", "cumulative_budget_spent", "balance",
            "normal_water_litres", "normal_water_cost", "drinking_water_litres", "drinking_water_cost", "sq_feet",
            "per_student_cost_month", "per_student_cost_day", "sq_feet_per_occupant", "normal_water_student_ltrs",
            "normal_water_student_cost", "power_cost_sqft", "units_per_occupant", "power_cost_occupant",
            "normal_water_ltr_day", "normal_water_cost_day", "drinking_water_ltr_day", "drinking_water_cost_day",
            "remarks", "custom_metrics"
        ) and not k.startswith("temp_"):
            custom_metrics[k] = v
    custom_metrics_json = json.dumps(custom_metrics)

    hc_sql = """
    INSERT INTO hostel_census_entries (
        period_id, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
        students_boys, students_girls, students_total,
        staff_boys, staff_girls, staff_total,
        total_occupied_boys, total_occupied_girls, total_occupied,
        vacant_boys, vacant_girls, vacant_total,
        vacant_college_boys, vacant_college_girls, vacant_college,
        vacant_sports_boys, vacant_sports_girls, vacant_sports_total,
        vacant_school_boys, vacant_school_girls, vacant_school_total,
        occupied_pct_boys, occupied_pct_girls, occupied_pct,
        vacant_pct_boys, vacant_pct_girls, vacant_pct,
        students_vacated,
        tickets_received, tickets_closed, tickets_open, total_hours_close, tat_hours,
        quality_issues_received, quality_issues_closed, quality_issues_open, incidents_count,
        power_units, power_cost, water_purchase_cost,
        maintenance_expenses, expenses_occurred,
        approved_budget, cumulative_budget_spent, balance,
        normal_water_litres, normal_water_cost,
        drinking_water_litres, drinking_water_cost,
        sq_feet, per_student_cost_month, per_student_cost_day,
        sq_feet_per_occupant, normal_water_student_ltrs, normal_water_student_cost,
        power_cost_sqft, units_per_occupant, power_cost_occupant,
        normal_water_ltr_day, normal_water_cost_day,
        drinking_water_ltr_day, drinking_water_cost_day,
        remarks, custom_metrics
    ) VALUES (
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s,
        %s, %s
    )
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
        total_occupied_boys = EXCLUDED.total_occupied_boys,
        total_occupied_girls = EXCLUDED.total_occupied_girls,
        total_occupied = EXCLUDED.total_occupied,
        vacant_boys = EXCLUDED.vacant_boys,
        vacant_girls = EXCLUDED.vacant_girls,
        vacant_total = EXCLUDED.vacant_total,
        vacant_college_boys = EXCLUDED.vacant_college_boys,
        vacant_college_girls = EXCLUDED.vacant_college_girls,
        vacant_college = EXCLUDED.vacant_college,
        vacant_sports_boys = EXCLUDED.vacant_sports_boys,
        vacant_sports_girls = EXCLUDED.vacant_sports_girls,
        vacant_sports_total = EXCLUDED.vacant_sports_total,
        vacant_school_boys = EXCLUDED.vacant_school_boys,
        vacant_school_girls = EXCLUDED.vacant_school_girls,
        vacant_school_total = EXCLUDED.vacant_school_total,
        occupied_pct_boys = EXCLUDED.occupied_pct_boys,
        occupied_pct_girls = EXCLUDED.occupied_pct_girls,
        occupied_pct = EXCLUDED.occupied_pct,
        vacant_pct_boys = EXCLUDED.vacant_pct_boys,
        vacant_pct_girls = EXCLUDED.vacant_pct_girls,
        vacant_pct = EXCLUDED.vacant_pct,
        students_vacated = EXCLUDED.students_vacated,
        tickets_received = EXCLUDED.tickets_received,
        tickets_closed = EXCLUDED.tickets_closed,
        tickets_open = EXCLUDED.tickets_open,
        total_hours_close = EXCLUDED.total_hours_close,
        tat_hours = EXCLUDED.tat_hours,
        quality_issues_received = EXCLUDED.quality_issues_received,
        quality_issues_closed = EXCLUDED.quality_issues_closed,
        quality_issues_open = EXCLUDED.quality_issues_open,
        incidents_count = EXCLUDED.incidents_count,
        power_units = EXCLUDED.power_units,
        power_cost = EXCLUDED.power_cost,
        water_purchase_cost = EXCLUDED.water_purchase_cost,
        maintenance_expenses = EXCLUDED.maintenance_expenses,
        expenses_occurred = EXCLUDED.expenses_occurred,
        approved_budget = EXCLUDED.approved_budget,
        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
        balance = EXCLUDED.balance,
        normal_water_litres = EXCLUDED.normal_water_litres,
        normal_water_cost = EXCLUDED.normal_water_cost,
        drinking_water_litres = EXCLUDED.drinking_water_litres,
        drinking_water_cost = EXCLUDED.drinking_water_cost,
        sq_feet = EXCLUDED.sq_feet,
        per_student_cost_month = EXCLUDED.per_student_cost_month,
        per_student_cost_day = EXCLUDED.per_student_cost_day,
        sq_feet_per_occupant = EXCLUDED.sq_feet_per_occupant,
        normal_water_student_ltrs = EXCLUDED.normal_water_student_ltrs,
        normal_water_student_cost = EXCLUDED.normal_water_student_cost,
        power_cost_sqft = EXCLUDED.power_cost_sqft,
        units_per_occupant = EXCLUDED.units_per_occupant,
        power_cost_occupant = EXCLUDED.power_cost_occupant,
        normal_water_ltr_day = EXCLUDED.normal_water_ltr_day,
        normal_water_cost_day = EXCLUDED.normal_water_cost_day,
        drinking_water_ltr_day = EXCLUDED.drinking_water_ltr_day,
        drinking_water_cost_day = EXCLUDED.drinking_water_cost_day,
        remarks = EXCLUDED.remarks,
        custom_metrics = EXCLUDED.custom_metrics;
    """
    cur.execute(hc_sql, (
        period_id, bc_b, bc_g, bc_tot,
        st_b, st_g, st_tot,
        sf_b, sf_g, sf_tot,
        occ_b, occ_g, occ_tot,
        vac_b, vac_g, vac_tot,
        vac_coll_b, vac_coll_g, vac_coll_tot,
        vac_sp_b, vac_sp_g, vac_sp_tot,
        vac_sc_b, vac_sc_g, vac_sc_tot,
        occ_pct_b, occ_pct_g, occ_pct,
        vac_pct_b, vac_pct_g, vac_pct,
        st_vacated,
        t_rec, t_cls, t_opn, tot_hrs, tat_hrs,
        q_rec, q_cls, q_opn, incidents,
        p_units, p_cost, w_pur,
        maint_exp, exp_occ,
        app_bud, cum_bud, bal,
        nw_ltr, nw_cost,
        dw_ltr, dw_cost,
        sq_ft, per_st_mo, per_st_day,
        sq_ft_occ, nw_st_ltr, nw_st_cost,
        p_sqft, p_occ_u, p_occ_c,
        nw_day_ltr, nw_day_c,
        dw_day_ltr, dw_day_c,
        remarks, custom_metrics_json
    ))

def compute_and_upsert_transport_census(cur, period_id: int, tc: Dict[str, Any], branch: str = "Common"):
    b_val = branch or "Common"
    cur.execute("SELECT * FROM transport_census_entries WHERE period_id = %s AND branch = %s;", (period_id, b_val))
    existing_row = cur.fetchone()
    existing = {}
    if existing_row:
        if isinstance(existing_row, dict):
            existing = existing_row
        elif hasattr(cur, 'description') and cur.description:
            col_names = [desc[0] for desc in cur.description]
            existing = dict(zip(col_names, existing_row))

    def get_f(key, fallback):
        if key in tc and tc[key] is not None and tc[key] != "":
            return tc[key]
        if key in existing and existing[key] is not None:
            return existing[key]
        return fallback

    vehicles_count = str(get_f("vehicles_count", "18+1"))
    passengers_count = int(_clean_num(get_f("passengers_count", 447)))
    students_count = int(_clean_num(get_f("students_count", 412)))
    staff_count = int(_clean_num(get_f("staff_count", 35)))

    approved_kms = float(_clean_num(get_f("approved_kms", 26691.0)))
    actual_kms = float(_clean_num(get_f("actual_kms", 25777.0)))
    additional_kms = float(_clean_num(get_f("additional_kms", 2481.0)))
    excess_kms_rps = float(_clean_num(get_f("excess_kms_rps", 0.0)))
    excess_km_billed_rps = float(_clean_num(get_f("excess_km_billed_rps", 0.0)))

    fuel_expenses = float(_clean_num(get_f("fuel_expenses", 487375.0)))
    diesel_litres = float(_clean_num(get_f("diesel_litres", 5184.84)))
    fc_cost = float(_clean_num(get_f("fc_cost", 0.0)))
    statutory_cost = float(_clean_num(get_f("statutory_cost", 0.0)))
    repair_maintenance_cost = float(_clean_num(get_f("repair_maintenance_cost", 0.0)))
    employee_cost = float(_clean_num(get_f("employee_cost", 0.0)))
    other_cost = float(_clean_num(get_f("other_cost", 0.0)))

    # Row 15: Total Expenses = SUM(fuel + fc + statutory + repair + employee + other)
    total_expenses = fuel_expenses + fc_cost + statutory_cost + repair_maintenance_cost + employee_cost + other_cost

    fee_demand = float(_clean_num(get_f("fee_demand", 0.0)))
    fee_discount = float(_clean_num(get_f("fee_discount", 0.0)))
    fee_collected = float(_clean_num(get_f("fee_collected", 0.0)))
    fee_unpaid = max(0.0, fee_demand - fee_discount - fee_collected)

    rps_monthly_billing = float(_clean_num(get_f("rps_monthly_billing", 0.0)))
    staff_travel_deduction = float(_clean_num(get_f("staff_travel_deduction", 0.0)))
    additional_kms_billed_rps = float(_clean_num(get_f("additional_kms_billed_rps", 0.0)))
    additional_kms_others_billing = float(_clean_num(get_f("additional_kms_others_billing", 0.0)))
    cab_billing = float(_clean_num(get_f("cab_billing", 0.0)))

    cumulative_income = (fee_collected + rps_monthly_billing + staff_travel_deduction + 
                         additional_kms_billed_rps + additional_kms_others_billing + cab_billing)

    approved_budget = float(_clean_num(get_f("approved_budget", 13730137.73)))
    cumulative_budget_spent = float(_clean_num(get_f("cumulative_budget_spent", 0.0)))
    if cumulative_budget_spent == 0.0 and total_expenses > 0.0:
        cumulative_budget_spent = total_expenses
    balance = approved_budget - cumulative_budget_spent

    service_tickets_raised = int(_clean_num(get_f("service_tickets_raised", 38)))
    service_tickets_closed = int(_clean_num(get_f("service_tickets_closed", 38)))
    service_tickets_open = max(0, service_tickets_raised - service_tickets_closed)

    quality_issues_received = int(_clean_num(get_f("quality_issues_received", 0)))
    quality_issues_closed = int(_clean_num(get_f("quality_issues_closed", 0)))
    quality_issues_open = max(0, quality_issues_received - quality_issues_closed)

    statutory_compliance = int(_clean_num(get_f("statutory_compliance", 1)))
    incidents_count = int(_clean_num(get_f("incidents_count", 1)))

    per_student_cost_expenses = round(total_expenses / passengers_count, 2) if passengers_count > 0 else 0.0
    per_student_fee_year = round(fee_demand / students_count, 2) if students_count > 0 else 0.0
    demand_per_km_day = round(fee_demand / (actual_kms * 30), 2) if actual_kms > 0 else 0.0
    km_per_veh_day = round(actual_kms / (19.0 * 30.0), 2)
    fuel_cost_per_km = round(fuel_expenses / actual_kms, 2) if actual_kms > 0 else 0.0
    diesel_per_100km = round((diesel_litres / actual_kms) * 100.0, 2) if actual_kms > 0 else 0.0

    remarks = str(tc.get("remarks") if "remarks" in tc else existing.get("remarks", ""))

    tc_sql = """
    INSERT INTO transport_census_entries (
        period_id, branch, vehicles_count, passengers_count, students_count, staff_count,
        approved_kms, actual_kms, additional_kms, excess_kms_rps, excess_km_billed_rps,
        fuel_expenses, diesel_litres, fc_cost, statutory_cost,
        repair_maintenance_cost, employee_cost, other_cost, total_expenses,
        fee_demand, fee_discount, fee_collected, fee_unpaid,
        rps_monthly_billing, staff_travel_deduction, additional_kms_billed_rps, additional_kms_others_billing, cab_billing, cumulative_income,
        approved_budget, cumulative_budget_spent, balance,
        service_tickets_raised, service_tickets_closed, service_tickets_open,
        quality_issues_received, quality_issues_closed, quality_issues_open,
        statutory_compliance, incidents_count,
        per_student_cost_expenses, per_student_fee_year, demand_per_km_day, km_per_veh_day,
        fuel_cost_per_km, diesel_per_100km, remarks
    ) VALUES (
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s, %s, %s,
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
        excess_kms_rps = EXCLUDED.excess_kms_rps,
        excess_km_billed_rps = EXCLUDED.excess_km_billed_rps,
        fuel_expenses = EXCLUDED.fuel_expenses,
        diesel_litres = EXCLUDED.diesel_litres,
        fc_cost = EXCLUDED.fc_cost,
        statutory_cost = EXCLUDED.statutory_cost,
        repair_maintenance_cost = EXCLUDED.repair_maintenance_cost,
        employee_cost = EXCLUDED.employee_cost,
        other_cost = EXCLUDED.other_cost,
        total_expenses = EXCLUDED.total_expenses,
        fee_demand = EXCLUDED.fee_demand,
        fee_discount = EXCLUDED.fee_discount,
        fee_collected = EXCLUDED.fee_collected,
        fee_unpaid = EXCLUDED.fee_unpaid,
        rps_monthly_billing = EXCLUDED.rps_monthly_billing,
        staff_travel_deduction = EXCLUDED.staff_travel_deduction,
        additional_kms_billed_rps = EXCLUDED.additional_kms_billed_rps,
        additional_kms_others_billing = EXCLUDED.additional_kms_others_billing,
        cab_billing = EXCLUDED.cab_billing,
        cumulative_income = EXCLUDED.cumulative_income,
        approved_budget = EXCLUDED.approved_budget,
        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
        balance = EXCLUDED.balance,
        service_tickets_raised = EXCLUDED.service_tickets_raised,
        service_tickets_closed = EXCLUDED.service_tickets_closed,
        service_tickets_open = EXCLUDED.service_tickets_open,
        quality_issues_received = EXCLUDED.quality_issues_received,
        quality_issues_closed = EXCLUDED.quality_issues_closed,
        quality_issues_open = EXCLUDED.quality_issues_open,
        statutory_compliance = EXCLUDED.statutory_compliance,
        incidents_count = EXCLUDED.incidents_count,
        per_student_cost_expenses = EXCLUDED.per_student_cost_expenses,
        per_student_fee_year = EXCLUDED.per_student_fee_year,
        demand_per_km_day = EXCLUDED.demand_per_km_day,
        km_per_veh_day = EXCLUDED.km_per_veh_day,
        fuel_cost_per_km = EXCLUDED.fuel_cost_per_km,
        diesel_per_100km = EXCLUDED.diesel_per_100km,
        remarks = EXCLUDED.remarks;
    """
    cur.execute(tc_sql, (
        period_id, b_val, vehicles_count, passengers_count, students_count, staff_count,
        approved_kms, actual_kms, additional_kms, excess_kms_rps, excess_km_billed_rps,
        fuel_expenses, diesel_litres, fc_cost, statutory_cost,
        repair_maintenance_cost, employee_cost, other_cost, total_expenses,
        fee_demand, fee_discount, fee_collected, fee_unpaid,
        rps_monthly_billing, staff_travel_deduction, additional_kms_billed_rps, additional_kms_others_billing, cab_billing, cumulative_income,
        approved_budget, cumulative_budget_spent, balance,
        service_tickets_raised, service_tickets_closed, service_tickets_open,
        quality_issues_received, quality_issues_closed, quality_issues_open,
        statutory_compliance, incidents_count,
        per_student_cost_expenses, per_student_fee_year, demand_per_km_day, km_per_veh_day,
        fuel_cost_per_km, diesel_per_100km, remarks
    ))

# -------------------------------------------------------------
# WORKSTATION BATCH SAVE & ACTIONS
# -------------------------------------------------------------
@app.post("/api/workstation/batch-save")
@app.post("/api/batch-entry")
def batch_save_workstation_data(req: BatchSaveRequest):
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                if req.operating_days is not None:
                    cur.execute("UPDATE billing_periods SET operating_days = %s WHERE id = %s", (req.operating_days, req.period_id))
                
                mod = req.module or "food"
                branch = req.branch or "Common"
                for item in req.entries:
                    upsert_sql = """
                    INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, vendor_id, amount, remarks, branch, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (module, period_id, cost_head_id, branch)
                    DO UPDATE SET
                        amount = EXCLUDED.amount,
                        vendor_id = EXCLUDED.vendor_id,
                        remarks = EXCLUDED.remarks,
                        updated_at = CURRENT_TIMESTAMP;
                    """
                    cur.execute(upsert_sql, (mod, req.period_id, item.cost_head_id, item.vendor_id, item.amount, item.remarks, branch))

                # Update dining census ONLY for food module
                if mod == "food" and any(v is not None for v in [req.active_students, req.active_staff, req.others_count, req.total_persons, req.production_meals]):
                    students = req.active_students if req.active_students is not None else 0
                    staff = req.active_staff if req.active_staff is not None else 0
                    others = req.others_count if req.others_count is not None else 0
                    total_p = req.total_persons if req.total_persons is not None else (students + staff + others)
                    prod = req.production_meals if req.production_meals is not None else 0

                    census_sql = """
                    INSERT INTO dining_census_entries (period_id, active_students, active_staff, others_count, total_persons, production_meals)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (period_id)
                    DO UPDATE SET
                        active_students = EXCLUDED.active_students,
                        active_staff = EXCLUDED.active_staff,
                        others_count = EXCLUDED.others_count,
                        total_persons = EXCLUDED.total_persons,
                        production_meals = EXCLUDED.production_meals;
                    """
                    cur.execute(census_sql, (req.period_id, students, staff, others, total_p, prod))

                # Update Hostel Census & Operational Metrics
                if req.hostel_census:
                    compute_and_upsert_hostel_census(cur, req.period_id, req.hostel_census)

                # Update Transport Census & Fleet Metrics
                if req.transport_census:
                    compute_and_upsert_transport_census(cur, req.period_id, req.transport_census, branch=branch)

                # Update any edited Cost Head descriptions / names
                if req.updated_cost_heads:
                    for ch in req.updated_cost_heads:
                        if ch.get("id") and ch.get("name"):
                            cur.execute("UPDATE cost_heads SET name = %s WHERE id = %s", (ch["name"].strip(), ch["id"]))

                # Update any edited Category names
                if req.updated_categories:
                    for cat in req.updated_categories:
                        if cat.get("id") and cat.get("name"):
                            cur.execute("UPDATE expense_categories SET name = %s WHERE id = %s", (cat["name"].strip(), cat["id"]))

                conn.commit()
                return {"status": "success", "message": f"Successfully committed batch for period ID {req.period_id}"}
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workstation/spreadsheet-save")
def spreadsheet_save_all(req: SpreadsheetSaveRequest):
    """
    Saves multi-month spreadsheet data, inline line item text edits, category renames,
    added rows and period entries in a single atomic transaction.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                mod = req.module or "food"
                branch = req.branch or "Common"

                # 1. Update edited Cost Head names/descriptions
                if req.updated_cost_heads:
                    for ch in req.updated_cost_heads:
                        if ch.get("id") and ch.get("name"):
                            cur.execute("UPDATE cost_heads SET name = %s WHERE id = %s", (ch["name"].strip(), ch["id"]))

                # 2. Update edited Category names
                if req.updated_categories:
                    for cat in req.updated_categories:
                        if cat.get("id") and cat.get("name"):
                            cur.execute("UPDATE expense_categories SET name = %s WHERE id = %s", (cat["name"].strip(), cat["id"]))

                # 3. Insert newly added cost heads
                created_cost_heads = {}
                if req.new_cost_heads:
                    for nch in req.new_cost_heads:
                        cat_id = nch.get("category_id")
                        name = (nch.get("name") or "").strip()
                        temp_id = str(nch.get("temp_id") or "")
                        if cat_id and name:
                            clean_code = "CH_" + re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').upper()[:16]
                            cur.execute("""
                                INSERT INTO cost_heads (category_id, name, code, is_active, display_order)
                                VALUES (%s, %s, %s, true, 99)
                                RETURNING id;
                            """, (cat_id, name, clean_code))
                            new_row = cur.fetchone()
                            if new_row:
                                created_cost_heads[temp_id] = new_row[0]

                # 4. Save multi-period entries
                if req.entries_by_period:
                    for p_id_str, items in req.entries_by_period.items():
                        try:
                            p_id = int(p_id_str)
                            for it in items:
                                ch_id = it.get("cost_head_id")
                                if str(ch_id) in created_cost_heads:
                                    ch_id = created_cost_heads[str(ch_id)]
                                if ch_id is not None:
                                    amt = float(it.get("amount") or 0.0)
                                    remarks = str(it.get("remarks") or "")
                                    item_branch = it.get("branch") or branch
                                    cur.execute("""
                                        INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, amount, remarks, branch, updated_at)
                                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                        ON CONFLICT (module, period_id, cost_head_id, branch)
                                        DO UPDATE SET
                                            amount = EXCLUDED.amount,
                                            remarks = EXCLUDED.remarks,
                                            updated_at = CURRENT_TIMESTAMP;
                                    """, (mod, p_id, ch_id, amt, remarks, item_branch))
                        except (ValueError, TypeError):
                            continue

                # 5. Save multi-period census (for food)
                if req.census_by_period:
                    for p_id_str, cdata in req.census_by_period.items():
                        try:
                            p_id = int(p_id_str)
                            s = int(cdata.get("students") or 0)
                            st = int(cdata.get("staff") or 0)
                            o = int(cdata.get("others") or 0)
                            tot = s + st + o
                            prod = int(cdata.get("production") or 0)
                            cur.execute("""
                                INSERT INTO dining_census_entries (period_id, active_students, active_staff, others_count, total_persons, production_meals)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (period_id)
                                DO UPDATE SET
                                    active_students = EXCLUDED.active_students,
                                    active_staff = EXCLUDED.active_staff,
                                    others_count = EXCLUDED.others_count,
                                    total_persons = EXCLUDED.total_persons,
                                    production_meals = EXCLUDED.production_meals;
                            """, (p_id, s, st, o, tot, prod))
                        except (ValueError, TypeError):
                            continue

                # 6. Save multi-period hostel census (for hostel module)
                if req.hostel_census_by_period:
                    for p_id_str, hc_data in req.hostel_census_by_period.items():
                        try:
                            p_id = int(p_id_str)
                            if hc_data:
                                compute_and_upsert_hostel_census(cur, p_id, hc_data)
                        except Exception as h_err:
                            print(f"[Hostel Census Save Notice] period {p_id_str}: {h_err}")

                # 7. Save multi-period transport census (for transport module)
                if req.transport_census_by_period:
                    for p_id_str, tc_data in req.transport_census_by_period.items():
                        try:
                            p_id = int(p_id_str)
                            if tc_data:
                                tc_branch = tc_data.get("branch") or branch
                                compute_and_upsert_transport_census(cur, p_id, tc_data, branch=tc_branch)
                        except Exception as t_err:
                            print(f"[Transport Census Save Notice] period {p_id_str}: {t_err}")

                conn.commit()
                return {
                    "status": "success",
                    "message": "All spreadsheet rows, text edits, formulas and monthly entries saved to database successfully!",
                    "created_cost_heads": created_cost_heads
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hostel-census/{period_id}")
def save_hostel_census_direct(period_id: int, req: Dict[str, Any]):
    """
    Direct endpoint to calculate and save hostel census & operational metrics for a specific period.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                compute_and_upsert_hostel_census(cur, period_id, req)
                conn.commit()
                row = db.execute_query(
                    "SELECT * FROM hostel_census_entries WHERE period_id = %s;",
                    (period_id,),
                    fetch_all=False
                )
                clean_row = {}
                if row:
                    clean_row = {
                        k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                        for k, v in row.items()
                    }
                return {
                    "status": "success",
                    "message": f"Hostel census parameters & formulas saved successfully for period {period_id}",
                    "period_id": period_id,
                    "data": clean_row
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/hostel-census-bulk")
def save_hostel_census_bulk(req: Dict[str, Any]):
    """
    Bulk endpoint to save multiple periods in the multi-month hostel ledger in one transaction.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                months_data = req.get("months") or req
                updated_periods = []
                for p_id_str, data in months_data.items():
                    try:
                        p_id = int(p_id_str)
                        if isinstance(data, dict):
                            compute_and_upsert_hostel_census(cur, p_id, data)
                            updated_periods.append(p_id)
                    except (ValueError, TypeError):
                        continue
                conn.commit()
                return {
                    "status": "success",
                    "message": f"Saved {len(updated_periods)} hostel operational month(s) successfully",
                    "updated_periods": updated_periods
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/transport/branches")
def get_transport_branches():
    """
    Returns available operating transport branches / fleets.
    """
    return {
        "branches": [
            {"id": "all", "code": "all", "label": "All Branches (Consolidated)", "description": "Consolidated fleet metrics across all institutions", "icon": "🏢"},
            {"id": "RPS", "code": "RPS", "label": "RPS Branch", "description": "Rathinam Public School Fleet", "icon": "🏫"},
            {"id": "KPM", "code": "KPM", "label": "KPM Branch", "description": "KPM Matriculation Fleet", "icon": "🏫"},
            {"id": "Common", "code": "Common", "label": "Common Pool", "description": "Central Campus Shared Fleet", "icon": "🚌"},
            {"id": "University", "code": "University", "label": "University Fleet", "description": "Rathinam University Main Fleet", "icon": "🎓"},
        ]
    }

@app.post("/api/transport-census/{period_id}")
def save_transport_census_direct(period_id: int, req: Dict[str, Any]):
    """
    Direct endpoint to calculate and save transport census & fleet operational metrics for a specific period.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                branch = req.get("branch") or "Common"
                compute_and_upsert_transport_census(cur, period_id, req, branch=branch)
                conn.commit()
                row = db.execute_query(
                    "SELECT * FROM transport_census_entries WHERE period_id = %s AND branch = %s;",
                    (period_id, branch),
                    fetch_all=False
                )
                clean_row = {}
                if row:
                    clean_row = {
                        k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                        for k, v in row.items()
                    }
                return {
                    "status": "success",
                    "message": f"Transport fleet parameters & formulas saved successfully for period {period_id} ({branch})",
                    "period_id": period_id,
                    "branch": branch,
                    "data": clean_row
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transport-census-bulk")
def save_transport_census_bulk(req: Dict[str, Any]):
    """
    Bulk endpoint to save multiple periods in the transport fleet ledger in one transaction.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                branch = req.get("branch") or "Common"
                months_data = req.get("months") or req
                updated_periods = []
                for p_id_str, data in months_data.items():
                    if p_id_str == "branch":
                        continue
                    try:
                        p_id = int(p_id_str)
                        if isinstance(data, dict):
                            m_branch = data.get("branch") or branch
                            compute_and_upsert_transport_census(cur, p_id, data, branch=m_branch)
                            updated_periods.append(p_id)
                    except (ValueError, TypeError):
                        continue
                conn.commit()
                return {
                    "status": "success",
                    "message": f"Saved {len(updated_periods)} transport fleet month(s) successfully for branch {branch}",
                    "branch": branch,
                    "updated_periods": updated_periods
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workstation/clone")
def clone_period_data(req: ClonePeriodRequest):
    try:
        clone_sql = """
        INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, vendor_id, amount, remarks, status, branch)
        SELECT COALESCE(module, 'food'), %s, cost_head_id, vendor_id, amount, 'Cloned from baseline', 'draft', COALESCE(branch, 'Common')
        FROM monthly_expense_entries
        WHERE period_id = %s
        ON CONFLICT (module, period_id, cost_head_id, branch)
        DO UPDATE SET
            amount = EXCLUDED.amount,
            vendor_id = EXCLUDED.vendor_id,
            remarks = 'Re-cloned from baseline',
            updated_at = CURRENT_TIMESTAMP;
        """
        db.execute_commit(clone_sql, (req.target_period_id, req.source_period_id))

        try:
            clone_census_sql = """
            INSERT INTO dining_census_entries (period_id, active_students, active_staff, others_count, total_persons, production_meals)
            SELECT %s, active_students, active_staff, others_count, total_persons, production_meals
            FROM dining_census_entries
            WHERE period_id = %s
            ON CONFLICT (period_id)
            DO UPDATE SET
                active_students = EXCLUDED.active_students,
                active_staff = EXCLUDED.active_staff,
                others_count = EXCLUDED.others_count,
                total_persons = EXCLUDED.total_persons,
                production_meals = EXCLUDED.production_meals;
            """
            db.execute_commit(clone_census_sql, (req.target_period_id, req.source_period_id))
        except Exception as ce:
            print(f"[Clone Census Notice] {ce}")

        try:
            clone_hostel_sql = """
            INSERT INTO hostel_census_entries (
                period_id, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
                students_boys, students_girls, students_total,
                staff_boys, staff_girls, staff_total,
                total_occupied, vacant_total, vacant_college,
                occupied_pct, vacant_pct, students_vacated,
                tickets_received, tickets_closed, tickets_open,
                tat_hours, quality_issues_received, quality_issues_closed, quality_issues_open, incidents_count,
                power_units, power_cost, water_purchase_cost,
                normal_water_litres, normal_water_cost,
                drinking_water_litres, drinking_water_cost,
                sq_feet, approved_budget, cumulative_budget_spent, remarks
            )
            SELECT
                %s, bed_capacity_boys, bed_capacity_girls, bed_capacity_total,
                students_boys, students_girls, students_total,
                staff_boys, staff_girls, staff_total,
                total_occupied, vacant_total, vacant_college,
                occupied_pct, vacant_pct, students_vacated,
                tickets_received, tickets_closed, tickets_open,
                tat_hours, quality_issues_received, quality_issues_closed, quality_issues_open, incidents_count,
                power_units, power_cost, water_purchase_cost,
                normal_water_litres, normal_water_cost,
                drinking_water_litres, drinking_water_cost,
                sq_feet, approved_budget, cumulative_budget_spent, remarks
            FROM hostel_census_entries
            WHERE period_id = %s
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
                cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
                remarks = EXCLUDED.remarks;
            """
            db.execute_commit(clone_hostel_sql, (req.target_period_id, req.source_period_id))
        except Exception as he:
            print(f"[Clone Hostel Census Notice] {he}")

        try:
            clone_transport_sql = """
            INSERT INTO transport_census_entries (
                period_id, vehicles_count, passengers_count, students_count, staff_count,
                approved_kms, actual_kms, additional_kms, excess_kms_rps,
                fuel_expenses, diesel_litres, fc_cost, statutory_cost,
                repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                fee_demand, fee_collected, fee_unpaid,
                service_tickets_raised, service_tickets_closed, service_tickets_open,
                quality_issues_received, quality_issues_closed, quality_issues_open,
                statutory_compliance, incidents_count,
                approved_budget, cumulative_budget_spent, remarks
            )
            SELECT
                %s, vehicles_count, passengers_count, students_count, staff_count,
                approved_kms, actual_kms, additional_kms, excess_kms_rps,
                fuel_expenses, diesel_litres, fc_cost, statutory_cost,
                repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                fee_demand, fee_collected, fee_unpaid,
                service_tickets_raised, service_tickets_closed, service_tickets_open,
                quality_issues_received, quality_issues_closed, quality_issues_open,
                statutory_compliance, incidents_count,
                approved_budget, cumulative_budget_spent, remarks
            FROM transport_census_entries
            WHERE period_id = %s
            ON CONFLICT (period_id) DO UPDATE SET
                vehicles_count = EXCLUDED.vehicles_count,
                passengers_count = EXCLUDED.passengers_count,
                students_count = EXCLUDED.students_count,
                staff_count = EXCLUDED.staff_count,
                approved_kms = EXCLUDED.approved_kms,
                actual_kms = EXCLUDED.actual_kms,
                additional_kms = EXCLUDED.additional_kms,
                excess_kms_rps = EXCLUDED.excess_kms_rps,
                fuel_expenses = EXCLUDED.fuel_expenses,
                diesel_litres = EXCLUDED.diesel_litres,
                fc_cost = EXCLUDED.fc_cost,
                statutory_cost = EXCLUDED.statutory_cost,
                repair_maintenance_cost = EXCLUDED.repair_maintenance_cost,
                employee_cost = EXCLUDED.employee_cost,
                other_cost = EXCLUDED.other_cost,
                total_expenses = EXCLUDED.total_expenses,
                fee_demand = EXCLUDED.fee_demand,
                fee_collected = EXCLUDED.fee_collected,
                fee_unpaid = EXCLUDED.fee_unpaid,
                service_tickets_raised = EXCLUDED.service_tickets_raised,
                service_tickets_closed = EXCLUDED.service_tickets_closed,
                service_tickets_open = EXCLUDED.service_tickets_open,
                quality_issues_received = EXCLUDED.quality_issues_received,
                quality_issues_closed = EXCLUDED.quality_issues_closed,
                quality_issues_open = EXCLUDED.quality_issues_open,
                statutory_compliance = EXCLUDED.statutory_compliance,
                incidents_count = EXCLUDED.incidents_count,
                approved_budget = EXCLUDED.approved_budget,
                cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
                remarks = EXCLUDED.remarks;
            """
            db.execute_commit(clone_transport_sql, (req.target_period_id, req.source_period_id))
        except Exception as te:
            print(f"[Clone Transport Census Notice] {te}")

        return {"status": "success", "message": f"Cloned entries from period {req.source_period_id} to {req.target_period_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workstation/lock")
def lock_period(req: LockPeriodRequest):
    try:
        db.execute_commit("UPDATE billing_periods SET is_closed = %s WHERE id = %s", (req.is_closed, req.period_id))
        return {"status": "success", "is_closed": req.is_closed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audit-flags")
def get_audit_flags():
    return [
        {
            "id": 1,
            "severity": "high",
            "title": "Missing October Water Consumption Entry",
            "category": "FC Maintenance / Utilities",
            "description": "Row 11 (Water Consumption) is unrecorded for Oct'26. September water was ₹2,15,954.70. Omission skews operating expenses downward by ~₹1.80 Lakhs.",
            "recommendation": "Retrieve utility meter invoice from Water Purchase Tracker and update October entry."
        },
        {
            "id": 2,
            "severity": "high",
            "title": "Siri Event Staffing Surge (+139.95%)",
            "category": "Food Labour",
            "description": "Cost expanded from ₹2,29,268 in June to ₹5,50,121.60 in October. Vendor is being used for regular counter shifts rather than ad-hoc event staffing.",
            "recommendation": "Cap contingent vendor headcount and transition core serving staff to in-house contracts to save 25%-35%."
        },
        {
            "id": 3,
            "severity": "medium",
            "title": "Food Vehicle Transport Spike (+138.77%)",
            "category": "FC Maintenance / Logistics",
            "description": "Food logistics vehicle expense doubled from ₹33,940.45 in September to ₹81,039.58 in October.",
            "recommendation": "Audit logbook and garage repair receipts to verify whether this was an unbudgeted overhaul."
        },
        {
            "id": 4,
            "severity": "medium",
            "title": "September Raw Material Peak (+42.33%)",
            "category": "Food Material",
            "description": "Material issued surged from ₹69.50 Lakhs in August to ₹98.92 Lakhs in September following full campus reopening.",
            "recommendation": "Institute recipe yield tracking and daily store-issue audits linked to scanned student tokens."
        }
    ]

# -------------------------------------------------------------
# USER MANAGEMENT (USER CONTROL)
# -------------------------------------------------------------
@app.get("/api/users")
def get_all_users():
    try:
        users = db.execute_query(
            "SELECT id, username, email, full_name, role, department, is_active, created_at, last_login FROM users ORDER BY id ASC"
        )
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users")
def create_new_user(req: UserCreate):
    try:
        # Check if username or email exists
        existing = db.execute_query(
            "SELECT id FROM users WHERE username = %s OR email = %s",
            (req.username.strip(), req.email.strip()),
            fetch_all=False
        )
        if existing:
            raise HTTPException(status_code=400, detail="Username or email already exists")

        pw_hash = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        insert_sql = """
        INSERT INTO users (username, email, password_hash, full_name, role, department, is_active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
        RETURNING id, username, email, full_name, role, department, is_active, created_at;
        """
        user = db.execute_query(
            insert_sql,
            (req.username.strip(), req.email.strip(), pw_hash, req.full_name.strip(), req.role.strip(), req.department.strip()),
            fetch_all=False
        )
        return {"status": "success", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/users/{user_id}")
def update_user(user_id: int, req: UserUpdate):
    try:
        user = db.execute_query("SELECT id FROM users WHERE id = %s", (user_id,), fetch_all=False)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates = []
        params = []
        if req.full_name is not None:
            updates.append("full_name = %s")
            params.append(req.full_name.strip())
        if req.email is not None:
            updates.append("email = %s")
            params.append(req.email.strip())
        if req.role is not None:
            updates.append("role = %s")
            params.append(req.role.strip())
        if req.department is not None:
            updates.append("department = %s")
            params.append(req.department.strip())
        if req.is_active is not None:
            updates.append("is_active = %s")
            params.append(req.is_active)
        if req.password is not None and req.password.strip():
            pw_hash = bcrypt.hashpw(req.password.strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            updates.append("password_hash = %s")
            params.append(pw_hash)

        if not updates:
            return {"status": "success", "message": "No changes requested"}

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s;"
        db.execute_commit(sql, tuple(params))
        return {"status": "success", "message": f"User {user_id} updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int):
    try:
        if user_id == 1:
            raise HTTPException(status_code=400, detail="Cannot delete default system administrator account (ID 1)")

        user = db.execute_query("SELECT id, username, role FROM users WHERE id = %s", (user_id,), fetch_all=False)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user["role"] == "admin":
            admin_count = db.execute_query("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'", fetch_all=False)
            if admin_count and admin_count["c"] <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the sole remaining administrator")

        db.execute_commit("DELETE FROM users WHERE id = %s", (user_id,))
        return {"status": "success", "message": f"User {user['username']} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# PAGE ACCESS CONTROL (PERMISSIONS)
# -------------------------------------------------------------
@app.get("/api/permissions/page-access")
def get_page_access_permissions():
    try:
        perms = db.execute_query("SELECT role, page_id, can_access FROM role_page_permissions ORDER BY role, page_id")
        return perms
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/permissions/page-access")
def save_page_access_permissions(req: PagePermissionsBatch):
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for p in req.permissions:
                    # Enforce admin always has access to all pages
                    can_acc = True if p.role == 'admin' else p.can_access
                    cur.execute("""
                    INSERT INTO role_page_permissions (role, page_id, can_access)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (role, page_id)
                    DO UPDATE SET can_access = EXCLUDED.can_access;
                    """, (p.role, p.page_id, can_acc))
                conn.commit()
                return {"status": "success", "message": "Page access permissions updated successfully"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# SQL DATABASE DUMP, RELOAD & DUMMY DATA MANAGEMENT
# -------------------------------------------------------------
@app.get("/api/system/backup")
def download_database_backup():
    try:
        sql_dump = system_manager.generate_sql_dump()
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rathinam_erp_backup_{date_str}.sql"
        return Response(
            content=sql_dump,
            media_type="application/sql",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate database dump: {str(e)}")

@app.post("/api/system/restore")
async def restore_database_backup(file: UploadFile = File(...)):
    try:
        if not file.filename.endswith(".sql"):
            raise HTTPException(status_code=400, detail="Only .sql files are accepted for database restore")

        content_bytes = await file.read()
        sql_text = content_bytes.decode("utf-8", errors="replace")

        res = system_manager.restore_sql_dump(sql_text)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(e)}")

@app.post("/api/system/clear-dummy-data")
def clear_database_dummy_data(req: ClearDataRequest):
    try:
        if req.confirmation_code != "DELETE-DUMMY-DATA":
            raise HTTPException(status_code=400, detail="Invalid confirmation code. You must type DELETE-DUMMY-DATA exactly.")

        res = system_manager.clear_dummy_data()
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear dummy data: {str(e)}")

@app.post("/api/system/seed-default")
def reseed_database_demo_data():
    try:
        res = system_manager.reseed_demo_data()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to re-seed data: {str(e)}")
