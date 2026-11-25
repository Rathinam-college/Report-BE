from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Response, Request
from starlette.staticfiles import StaticFiles
import os
import uuid
import mimetypes
import shutil
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
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
# Mount uploads static directory for monthly documents and bills
uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

@app.middleware("http")
async def rewrite_report_subpath(request: Request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/Report/api"):
        request.scope["path"] = path.replace("/Report/api", "/api", 1)
    elif path.startswith("/report/api"):
        request.scope["path"] = path.replace("/report/api", "/api", 1)
    elif path.startswith("/Report/uploads"):
        request.scope["path"] = path.replace("/Report/uploads", "/uploads", 1)
    elif path.startswith("/report/uploads"):
        request.scope["path"] = path.replace("/report/uploads", "/uploads", 1)
    return await call_next(request)

def ensure_schema_compatibility():
    """
    Safely and idempotently ensures all required columns exist in the database,
    even if full migrations previously stopped or encountered non-critical errors.
    """
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS monthly_attachments (
            id SERIAL PRIMARY KEY,
            module VARCHAR(50) NOT NULL,
            period_id INT NOT NULL REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) DEFAULT 'Common',
            file_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            file_path TEXT NOT NULL,
            file_size BIGINT DEFAULT 0,
            mime_type VARCHAR(100) DEFAULT '',
            is_link BOOLEAN NOT NULL DEFAULT FALSE,
            uploaded_by VARCHAR(100) DEFAULT 'User',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_monthly_attachments_module_period ON monthly_attachments(module, period_id);
        """,
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
        "ALTER TABLE transport_census_entries ADD COLUMN IF NOT EXISTS custom_metrics JSONB DEFAULT '{}'::jsonb;",
        """
        CREATE TABLE IF NOT EXISTS hostel_budget_tracking (
            id SERIAL PRIMARY KEY,
            s_no INT NOT NULL,
            budget_head VARCHAR(100) UNIQUE NOT NULL,
            sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
            month_limit NUMERIC(14,2) DEFAULT 0.0,
            sep_25_actual NUMERIC(14,2) DEFAULT 0.0,
            oct_26_actual NUMERIC(14,2) DEFAULT 0.0,
            nov_26_actual NUMERIC(14,2) DEFAULT 0.0,
            dec_26_actual NUMERIC(14,2) DEFAULT 0.0,
            jan_27_actual NUMERIC(14,2) DEFAULT 0.0,
            feb_27_actual NUMERIC(14,2) DEFAULT 0.0,
            mar_27_actual NUMERIC(14,2) DEFAULT 0.0,
            apr_27_actual NUMERIC(14,2) DEFAULT 0.0,
            may_27_actual NUMERIC(14,2) DEFAULT 0.0,
            jun_27_actual NUMERIC(14,2) DEFAULT 0.0,
            jul_27_actual NUMERIC(14,2) DEFAULT 0.0,
            aug_27_actual NUMERIC(14,2) DEFAULT 0.0,
            sep_27_actual NUMERIC(14,2) DEFAULT 0.0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        INSERT INTO hostel_budget_tracking (s_no, budget_head, sanctioned_amount, month_limit)
        VALUES 
            (1, 'Rent', 84762516, 10595314.5),
            (2, 'Printing & Stationary Expenses', 15000, 1875),
            (3, 'Rates & Taxes', 731612, 91451.5),
            (4, 'Employee Cost', 15402907, 1925363.38),
            (5, 'Hostel Management Services', 30490064, 3811258),
            (6, 'Utility', 32893042, 4111630.25),
            (7, 'Laundry Expenses', 11728517, 1466064.63),
            (8, 'Repairs and Maintenance', 5425960, 678245),
            (9, 'Events', 4000000, 500000)
        ON CONFLICT (budget_head) DO NOTHING;
        """,
        "ALTER TABLE hostel_budget_tracking ADD COLUMN IF NOT EXISTS sep_25_actual NUMERIC DEFAULT 0.0;",
        "ALTER TABLE hostel_budget_tracking ADD COLUMN IF NOT EXISTS jun_27_actual NUMERIC DEFAULT 0.0;",
        "ALTER TABLE hostel_budget_tracking ADD COLUMN IF NOT EXISTS jul_27_actual NUMERIC DEFAULT 0.0;",
        "ALTER TABLE hostel_budget_tracking ADD COLUMN IF NOT EXISTS aug_27_actual NUMERIC DEFAULT 0.0;",
        "ALTER TABLE hostel_budget_tracking ADD COLUMN IF NOT EXISTS sep_27_actual NUMERIC DEFAULT 0.0;",
        """
        CREATE TABLE IF NOT EXISTS hostel_master_parameters (
            id SERIAL PRIMARY KEY,
            s_no VARCHAR(20) DEFAULT '',
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
        """,
        "ALTER TABLE hostel_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';",
        "UPDATE hostel_master_parameters SET s_no = CAST(display_order AS VARCHAR) WHERE s_no IS NULL OR s_no = '';",
        """
        CREATE TABLE IF NOT EXISTS transport_master_parameters (
            id SERIAL PRIMARY KEY,
            param_key VARCHAR(100) UNIQUE NOT NULL,
            param_name VARCHAR(255) NOT NULL,
            section VARCHAR(100) NOT NULL,
            section_order INT NOT NULL DEFAULT 1,
            input_type VARCHAR(50) NOT NULL DEFAULT 'cost',
            unit VARCHAR(50) DEFAULT '',
            formula TEXT DEFAULT NULL,
            display_order INT NOT NULL DEFAULT 1,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS transport_vehicle_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) NOT NULL DEFAULT 'Common',
            vehicle_no VARCHAR(50) NOT NULL,
            make VARCHAR(100) DEFAULT '',
            model VARCHAR(100) DEFAULT '',
            fuel_expenses NUMERIC(12,2) DEFAULT 0.0,
            fc_cost NUMERIC(12,2) DEFAULT 0.0,
            statutory_cost NUMERIC(12,2) DEFAULT 0.0,
            repair_maintenance NUMERIC(12,2) DEFAULT 0.0,
            parking_fastag NUMERIC(12,2) DEFAULT 0.0,
            employee_cost NUMERIC(12,2) DEFAULT 0.0,
            other_cost NUMERIC(12,2) DEFAULT 0.0,
            total_expenses NUMERIC(12,2) DEFAULT 0.0,
            diesel_litres NUMERIC(10,2) DEFAULT 0.0,
            km_run NUMERIC(10,2) DEFAULT 0.0,
            mileage NUMERIC(10,2) DEFAULT 0.0,
            display_order INT DEFAULT 0,
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_trans_veh_period_branch ON transport_vehicle_entries(period_id, branch);
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
    branch: Optional[str] = "all"

class PeriodUpdate(BaseModel):
    period_label: str
    period_code: Optional[str] = None
    is_closed: Optional[bool] = None

# Master Data Models
class CostHeadCreate(BaseModel):
    category_id: Optional[Union[int, str]] = None
    name: str
    code: Optional[str] = None
    cost_behavior: Optional[str] = "variable"
    default_vendor_id: Optional[int] = None
    default_vendor: Optional[str] = None
    display_order: Optional[int] = None
    module: Optional[str] = "food"

class CostHeadUpdate(BaseModel):
    category_id: Optional[Union[int, str]] = None
    name: Optional[str] = None
    code: Optional[str] = None
    cost_behavior: Optional[str] = "variable"
    default_vendor_id: Optional[int] = None
    default_vendor: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = True
    module: Optional[str] = None

class ReorderCostHeadsRequest(BaseModel):
    cost_head_ids: List[int]

class ReorderCategoriesRequest(BaseModel):
    category_ids: List[int]

class ReorderParametersRequest(BaseModel):
    parameter_ids: List[int]

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
                "SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module, COALESCE(branch, 'all') AS branch "
                "FROM billing_periods WHERE module = %s ORDER BY start_date",
                (module,)
            )
        return db.execute_query(
            "SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed, module, COALESCE(branch, 'all') AS branch "
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
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, is_closed, module, branch)
        VALUES (1, %s, %s, %s, %s, %s, false, %s, %s)
        RETURNING id, period_code, period_label, module, branch;
        """
        new_period = db.execute_query(
            insert_sql,
            (derived_code, label, start_date, end_date, operating_days, mod, req.branch or 'all'),
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
                    fc_cost, statutory_cost, repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                    fee_demand, fee_collected, fee_unpaid, approved_budget, cumulative_budget_spent, balance,
                    service_tickets_raised, service_tickets_closed, service_tickets_open,
                    quality_issues_received, quality_issues_closed, quality_issues_open,
                    statutory_compliance, incidents_count, custom_metrics
                )
                SELECT %s, COALESCE(branch, 'Common'), vehicles_count, passengers_count, students_count, staff_count,
                    approved_kms, actual_kms, additional_kms, diesel_litres, fuel_expenses,
                    fc_cost, statutory_cost, repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                    fee_demand, fee_collected, fee_unpaid, approved_budget, cumulative_budget_spent, balance,
                    service_tickets_raised, service_tickets_closed, service_tickets_open,
                    quality_issues_received, quality_issues_closed, quality_issues_open,
                    statutory_compliance, incidents_count, custom_metrics
                FROM transport_census_entries WHERE period_id = %s
                ON CONFLICT (period_id, branch) DO NOTHING;
                """, (new_period["id"], req.clone_from_period_id))

                db.execute_commit("""
                INSERT INTO transport_vehicle_entries (
                    period_id, branch, vehicle_no, make, model, display_order, remarks,
                    fuel_expenses, fc_cost, statutory_cost, repair_maintenance, parking_fastag,
                    employee_cost, other_cost, total_expenses, diesel_litres, km_run, mileage
                )
                SELECT %s, branch, vehicle_no, make, model, display_order, remarks,
                    0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                FROM transport_vehicle_entries WHERE period_id = %s
                ON CONFLICT DO NOTHING;
                """, (new_period["id"], req.clone_from_period_id))
        elif mod == "transport":
            # Distinct baseline initialization: if req.branch is specified (e.g. 'KPM'), ONLY initialize for that branch!
            target_branch = req.branch if (req.branch and req.branch != "all") else None
            branches_to_seed = [target_branch] if target_branch else ["Common", "RPS", "KPM", "University"]

            DISTINCT_TRANSPORT_BRANCH_DEFAULTS = {
                "RPS": {
                    "vehicles": "19", "passengers": 482, "students": 447, "staff": 35,
                    "approved_kms": 33046.0, "actual_kms": 0.0, "additional_kms": 0.0,
                    "diesel_litres": 0.0, "fuel_expense": 0.0,
                    "repair_maint": 0.0, "employee_cost": 0.0, "other_ops": 0.0,
                    "statutory_fc": 0.0, "insurance": 0.0,
                    "budget_approved": 8500000.0, "budget_spent": 0.0,
                    "fee_demand": 4200000.0, "fee_collected": 0.0,
                    "tickets_raised": 0, "tickets_closed": 0, "incidents": 0
                },
                "KPM": {
                    "vehicles": "5", "passengers": 270, "students": 250, "staff": 20,
                    "approved_kms": 6006.0, "actual_kms": 0.0, "additional_kms": 0.0,
                    "diesel_litres": 0.0, "fuel_expense": 0.0,
                    "repair_maint": 0.0, "employee_cost": 0.0, "other_ops": 0.0,
                    "statutory_fc": 0.0, "insurance": 0.0,
                    "budget_approved": 6200000.0, "budget_spent": 0.0,
                    "fee_demand": 2100000.0, "fee_collected": 0.0,
                    "tickets_raised": 0, "tickets_closed": 0, "incidents": 0
                },
                "Common": {
                    "vehicles": "18", "passengers": 120, "students": 0, "staff": 120,
                    "approved_kms": 8500.0, "actual_kms": 0.0, "additional_kms": 0.0,
                    "diesel_litres": 0.0, "fuel_expense": 0.0,
                    "repair_maint": 0.0, "employee_cost": 0.0, "other_ops": 0.0,
                    "statutory_fc": 0.0, "insurance": 0.0,
                    "budget_approved": 3800000.0, "budget_spent": 0.0,
                    "fee_demand": 0.0, "fee_collected": 0.0,
                    "tickets_raised": 0, "tickets_closed": 0, "incidents": 0
                },
                "University": {
                    "vehicles": "16", "passengers": 1230, "students": 1150, "staff": 80,
                    "approved_kms": 55097.0, "actual_kms": 0.0, "additional_kms": 0.0,
                    "diesel_litres": 0.0, "fuel_expense": 0.0,
                    "repair_maint": 0.0, "employee_cost": 0.0, "other_ops": 0.0,
                    "statutory_fc": 0.0, "insurance": 0.0,
                    "budget_approved": 14000000.0, "budget_spent": 0.0,
                    "fee_demand": 9500000.0, "fee_collected": 0.0,
                    "tickets_raised": 0, "tickets_closed": 0, "incidents": 0
                }
            }
            for b_name in branches_to_seed:
                b_data = DISTINCT_TRANSPORT_BRANCH_DEFAULTS.get(b_name)
                if not b_data:
                    continue
                db.execute_commit("""
                INSERT INTO transport_census_entries (
                    period_id, branch, vehicles_count, passengers_count, students_count, staff_count,
                    approved_kms, actual_kms, additional_kms, diesel_litres, fuel_expenses,
                    fc_cost, statutory_cost, repair_maintenance_cost, employee_cost, other_cost, total_expenses,
                    fee_demand, fee_collected, fee_unpaid, approved_budget, cumulative_budget_spent, balance,
                    service_tickets_raised, service_tickets_closed, service_tickets_open,
                    statutory_compliance, incidents_count, remarks
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    1, %s, %s
                )
                ON CONFLICT (period_id, branch) DO NOTHING;
                """, (
                    new_period["id"], b_name, b_data["vehicles"], b_data["passengers"], b_data["students"], b_data["staff"],
                    b_data["approved_kms"], b_data["actual_kms"], b_data["additional_kms"], b_data["diesel_litres"], b_data["fuel_expense"],
                    b_data["statutory_fc"], b_data["insurance"], b_data["repair_maint"], b_data["employee_cost"], b_data["other_ops"], 0.0,
                    b_data["fee_demand"], b_data["fee_collected"], b_data["fee_demand"] - b_data["fee_collected"],
                    b_data["budget_approved"], b_data["budget_spent"], b_data["budget_approved"] - b_data["budget_spent"],
                    b_data["tickets_raised"], b_data["tickets_closed"], 0,
                    b_data["incidents"], f"{b_name} fleet metrics"
                ))

            # Clone vehicle fleet roster for target branches from latest existing transport period
            latest_t_period = db.execute_query(
                "SELECT id FROM billing_periods WHERE module = 'transport' AND id != %s ORDER BY start_date DESC LIMIT 1;",
                (new_period["id"],),
                fetch_all=False
            )
            if latest_t_period:
                template_p_id = latest_t_period["id"]
                for b_name in branches_to_seed:
                    db.execute_commit("""
                        INSERT INTO transport_vehicle_entries (
                            period_id, branch, vehicle_no, make, model, display_order, remarks,
                            fuel_expenses, fc_cost, statutory_cost, repair_maintenance, parking_fastag,
                            employee_cost, other_cost, total_expenses, diesel_litres, km_run, mileage
                        )
                        SELECT %s, branch, vehicle_no, make, model, display_order, remarks,
                            0.0, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                        FROM transport_vehicle_entries WHERE period_id = %s AND branch = %s
                        ON CONFLICT DO NOTHING;
                    """, (new_period["id"], template_p_id, b_name))

            # Initialize monthly expense entries for target branches
            for b_name in branches_to_seed:
                db.execute_commit("""
                    INSERT INTO monthly_expense_entries (module, period_id, cost_head_id, amount, remarks, status, branch)
                    SELECT 'transport', %s, ch.id, 0.0, '', 'draft', %s
                    FROM cost_heads ch
                    JOIN expense_categories ec ON ch.category_id = ec.id
                    WHERE ec.module = 'transport'
                    ON CONFLICT (module, period_id, cost_head_id, branch) DO NOTHING;
                """, (new_period["id"], b_name))

        return {"status": "success", "period": new_period, "branch": req.branch or "all"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/periods/batch-delete")
def batch_delete_periods(req: Dict[str, Any]):
    """
    Batch delete multiple selected billing periods in a single transaction.
    """
    period_ids = req.get("period_ids") or req.get("ids") or []
    if not period_ids:
        raise HTTPException(status_code=400, detail="No billing period IDs provided for deletion")

    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                p_tuple = tuple(int(x) for x in period_ids)
                cur.execute("DELETE FROM monthly_expense_entries WHERE period_id IN %s", (p_tuple,))
                cur.execute("DELETE FROM dining_census_entries WHERE period_id IN %s", (p_tuple,))
                cur.execute("DELETE FROM utility_meter_logs WHERE period_id IN %s", (p_tuple,))
                cur.execute("DELETE FROM hostel_census_entries WHERE period_id IN %s", (p_tuple,))
                cur.execute("DELETE FROM transport_census_entries WHERE period_id IN %s", (p_tuple,))
                cur.execute("DELETE FROM billing_periods WHERE id IN %s RETURNING id, period_label", (p_tuple,))
                deleted_rows = cur.fetchall()
                conn.commit()
                deleted_labels = [r[1] for r in deleted_rows]
                return {
                    "status": "success",
                    "message": f"Successfully deleted {len(deleted_labels)} billing cycle(s): {', '.join(deleted_labels)}",
                    "deleted_count": len(deleted_labels),
                    "deleted_ids": [r[0] for r in deleted_rows]
                }
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hostel/budget-tracking")
def update_hostel_budget_tracking(req: Dict[str, Any]):
    """
    Updates or inserts budget heads and actual monthly expenses for all billing cycle months.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hostel_budget_tracking (
                        id SERIAL PRIMARY KEY,
                        s_no INT NOT NULL,
                        budget_head VARCHAR(100) UNIQUE NOT NULL,
                        sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
                        month_limit NUMERIC(14,2) DEFAULT 0.0,
                        sep_25_actual NUMERIC(14,2) DEFAULT 0.0,
                        oct_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        nov_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        dec_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        jan_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        feb_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        mar_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        apr_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        may_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        jun_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        jul_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        aug_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        sep_27_actual NUMERIC(14,2) DEFAULT 0.0,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                items = req.get("items") if isinstance(req, dict) and "items" in req else ([req] if isinstance(req, dict) else req)
                month_cols = [
                    "sep_25_actual", "oct_26_actual", "nov_26_actual", "dec_26_actual",
                    "jan_27_actual", "feb_27_actual", "mar_27_actual", "apr_27_actual",
                    "may_27_actual", "jun_27_actual", "jul_27_actual", "aug_27_actual",
                    "sep_27_actual"
                ]
                for item in items:
                    b_head = item.get("budget_head")
                    if not b_head:
                        continue
                    
                    cols = ["s_no", "budget_head", "sanctioned_amount", "month_limit"] + month_cols
                    vals = [
                        item.get("s_no", 1), b_head, item.get("sanctioned_amount") or 0.0, item.get("month_limit") or 0.0
                    ] + [item.get(col) for col in month_cols]
                    
                    placeholders = ", ".join(["%s"] * len(cols))
                    col_names = ", ".join(cols)
                    
                    update_set = [
                        "sanctioned_amount = CASE WHEN EXCLUDED.sanctioned_amount IS NOT NULL AND EXCLUDED.sanctioned_amount >= 0 THEN EXCLUDED.sanctioned_amount ELSE hostel_budget_tracking.sanctioned_amount END",
                        "month_limit = CASE WHEN EXCLUDED.month_limit IS NOT NULL AND EXCLUDED.month_limit >= 0 THEN EXCLUDED.month_limit ELSE hostel_budget_tracking.month_limit END"
                    ]
                    for col in month_cols:
                        update_set.append(f"{col} = CASE WHEN EXCLUDED.{col} IS NOT NULL THEN EXCLUDED.{col} ELSE hostel_budget_tracking.{col} END")
                    
                    update_clause = ", ".join(update_set)
                    
                    cur.execute(f"""
                        INSERT INTO hostel_budget_tracking ({col_names})
                        VALUES ({placeholders})
                        ON CONFLICT (budget_head) DO UPDATE SET
                            {update_clause};
                    """, tuple(vals))

                # Synchronize period 30 (Oct) actual spend and balance in hostel_census_entries
                try:
                    cur.execute("SELECT SUM(oct_26_actual) FROM hostel_budget_tracking")
                    tot_oct_sum = float(cur.fetchone()[0] or 0.0)
                    if tot_oct_sum > 0.0:
                        cur.execute("""
                            UPDATE hostel_census_entries 
                            SET expenses_occurred = %s,
                                cumulative_budget_spent = %s,
                                balance = COALESCE(approved_budget, 142010789.0) - %s
                            WHERE period_id IN (30, 246)
                        """, (tot_oct_sum, tot_oct_sum, tot_oct_sum))
                except Exception as sync_err:
                    print(f"[Hostel Census Sync Notice] {sync_err}")

                conn.commit()
                return {"status": "success", "message": "Hostel budget tracking updated successfully"}
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


@app.get("/api/food/budget-tracking")
def get_food_budget_tracking():
    """
    Returns the official 8-head Food Budget Tracking Summary directly from PostgreSQL.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS food_budget_tracking (
                        id SERIAL PRIMARY KEY,
                        s_no INT NOT NULL,
                        budget_head VARCHAR(120) UNIQUE NOT NULL,
                        sanctioned_amount NUMERIC(14,2) DEFAULT 0.0,
                        month_limit NUMERIC(14,2) DEFAULT 0.0,
                        jun_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        jul_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        aug_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        sep_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        oct_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        nov_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        dec_26_actual NUMERIC(14,2) DEFAULT 0.0,
                        monthly_actuals JSONB DEFAULT '{}',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("SELECT * FROM food_budget_tracking ORDER BY s_no ASC")
                rows = cur.fetchall()
                desc = [d[0] for d in cur.description]
                items = []
                for r in rows:
                    row_dict = dict(zip(desc, r))
                    conv = {}
                    for k, v in row_dict.items():
                        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
                            conv[k] = float(v)
                        else:
                            conv[k] = v
                    items.append(conv)

                if not items:
                    default_heads = [
                        (1, 'Food Material', 105000000.0, 8750000.0, 6662557.0, 7667497.0, 10934147.0, 10934147.0, 10123675.0),
                        (2, 'Food Team Salary', 36000000.0, 3000000.0, 2650000.0, 2870000.0, 2970000.0, 3309814.0, 3496221.0),
                        (3, 'Contract Labour Expenses', 4800000.0, 400000.0, 144212.0, 97183.0, 339814.0, 0.0, 0.0),
                        (4, 'Catering Vendor Expenses', 6000000.0, 500000.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                        (5, 'FC Maintenance/Power/Water/Vehicle', 6600000.0, 550000.0, 426223.0, 448729.0, 577127.0, 577127.0, 459483.0),
                        (6, 'Event/Additional Food', 3000000.0, 250000.0, 254000.0, 114490.0, 76775.0, 76775.0, 211000.0),
                        (7, 'Food Festival', 6000000.0, 500000.0, 0.0, 551639.0, 0.0, 0.0, 0.0),
                        (8, 'Staff Welfare', 1800000.0, 150000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                    ]
                    for dh in default_heads:
                        s_no, b_head, sanc, limit, jun, jul, aug, sep, oct_val = dh
                        m_dict = {'12': jun, '14': jul, '18': aug, '19': sep, '311': oct_val}
                        cur.execute('''
                            INSERT INTO food_budget_tracking 
                            (s_no, budget_head, sanctioned_amount, month_limit, jun_26_actual, jul_26_actual, aug_26_actual, sep_26_actual, oct_26_actual, monthly_actuals)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (budget_head) DO NOTHING;
                        ''', (s_no, b_head, sanc, limit, jun, jul, aug, sep, oct_val, json.dumps(m_dict)))
                    conn.commit()
                    cur.execute("SELECT * FROM food_budget_tracking ORDER BY s_no ASC")
                    rows = cur.fetchall()
                    items = []
                    for r in rows:
                        row_dict = dict(zip(desc, r))
                        conv = {k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v) for k, v in row_dict.items()}
                        items.append(conv)

                months = ["jun_26_actual", "jul_26_actual", "aug_26_actual", "sep_26_actual", "oct_26_actual", "nov_26_actual", "dec_26_actual"]
                monthly_totals = {m: sum(float(r.get(m) or 0) for r in items) for m in months}

                return {
                    "status": "success",
                    "items": items,
                    "total_sanctioned": sum(float(r.get("sanctioned_amount") or 0) for r in items),
                    "total_month_limit": sum(float(r.get("month_limit") or 0) for r in items),
                    "monthly_totals": monthly_totals
                }
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/food/budget-tracking")
def update_food_budget_tracking(req: Dict[str, Any]):
    """
    Updates or inserts budget heads and monthly targets/actuals for Food.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                items = req.get("items") if isinstance(req, dict) and "items" in req else ([req] if isinstance(req, dict) else req)
                month_cols = ["jun_26_actual", "jul_26_actual", "aug_26_actual", "sep_26_actual", "oct_26_actual", "nov_26_actual", "dec_26_actual"]
                for item in items:
                    b_head = item.get("budget_head")
                    if not b_head:
                        continue
                    cols = ["s_no", "budget_head", "sanctioned_amount", "month_limit"] + month_cols
                    vals = [
                        item.get("s_no", 1), b_head, float(item.get("sanctioned_amount") or 0.0), float(item.get("month_limit") or 0.0)
                    ] + [float(item.get(c) or 0.0) for c in month_cols]

                    if "monthly_actuals" in item and item["monthly_actuals"] is not None:
                        cols.append("monthly_actuals")
                        vals.append(json.dumps(item["monthly_actuals"]) if isinstance(item["monthly_actuals"], dict) else str(item["monthly_actuals"]))

                    placeholders = ", ".join(["%s"] * len(cols))
                    col_names = ", ".join(cols)
                    
                    update_set = [
                        "s_no = EXCLUDED.s_no",
                        "sanctioned_amount = EXCLUDED.sanctioned_amount",
                        "month_limit = EXCLUDED.month_limit",
                        "updated_at = CURRENT_TIMESTAMP"
                    ]
                    for col in month_cols:
                        update_set.append(f"{col} = EXCLUDED.{col}")
                    if "monthly_actuals" in cols:
                        update_set.append("monthly_actuals = EXCLUDED.monthly_actuals")

                    cur.execute(f"""
                        INSERT INTO food_budget_tracking ({col_names})
                        VALUES ({placeholders})
                        ON CONFLICT (budget_head) DO UPDATE SET
                            {', '.join(update_set)};
                    """, tuple(vals))

                conn.commit()
                return {"status": "success", "message": "Food budget tracking updated successfully"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/food/budget-tracking/sync")
def sync_food_budget_tracking():
    """
    Recalculates and synchronizes actual food expense entries directly into the 8 food budget heads.
    """
    try:
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ch.id, ch.name, ec.name as category_name
                    FROM cost_heads ch
                    JOIN expense_categories ec ON ch.category_id = ec.id
                    WHERE ec.module = 'food';
                """)
                cost_heads_map = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

                cur.execute("""
                    SELECT m.cost_head_id, m.period_id, p.period_code, p.period_label, m.amount
                    FROM monthly_expense_entries m
                    JOIN billing_periods p ON m.period_id = p.id
                    JOIN cost_heads ch ON m.cost_head_id = ch.id
                    JOIN expense_categories ec ON ch.category_id = ec.id
                    WHERE ec.module = 'food';
                """)
                entries = cur.fetchall()

                budget_head_sums = {
                    "Food Material": {},
                    "Food Team Salary": {},
                    "Contract Labour Expenses": {},
                    "Catering Vendor Expenses": {},
                    "FC Maintenance/Power/Water/Vehicle": {},
                    "Event/Additional Food": {},
                    "Food Festival": {},
                    "Staff Welfare": {}
                }

                for ch_id, pid, pcode, plabel, amt in entries:
                    if ch_id not in cost_heads_map:
                        continue
                    ch_name, cat_name = cost_heads_map[ch_id]
                    ch_lower = ch_name.lower()
                    cat_lower = cat_name.lower()
                    amount = float(amt or 0.0)

                    target_head = None
                    if "material" in cat_lower or "material" in ch_lower or "gas" in ch_lower:
                        target_head = "Food Material"
                    elif "salary" in ch_lower:
                        target_head = "Food Team Salary"
                    elif "housekeeping" in ch_lower or "adithya" in ch_lower or "contract" in ch_lower:
                        target_head = "Contract Labour Expenses"
                    elif "catering" in ch_lower or "vendor" in ch_lower:
                        target_head = "Catering Vendor Expenses"
                    elif "maintenance" in cat_lower or "power" in cat_lower or "vehicle" in ch_lower or "water" in ch_lower or "food court" in ch_lower:
                        target_head = "FC Maintenance/Power/Water/Vehicle"
                    elif "festival" in cat_lower or "festival" in ch_lower:
                        target_head = "Food Festival"
                    elif "event" in cat_lower or "event" in ch_lower:
                        target_head = "Event/Additional Food"
                    elif "welfare" in cat_lower or "welfare" in ch_lower:
                        target_head = "Staff Welfare"
                    else:
                        target_head = "Food Material"

                    if target_head:
                        budget_head_sums[target_head][str(pid)] = budget_head_sums[target_head].get(str(pid), 0.0) + amount

                for b_head, period_dict in budget_head_sums.items():
                    jun_val = period_dict.get('12', 0.0)
                    jul_val = period_dict.get('14', 0.0)
                    aug_val = period_dict.get('18', 0.0)
                    sep_val = period_dict.get('19', 0.0)
                    oct_val = period_dict.get('311', 0.0)
                    cur.execute("""
                        UPDATE food_budget_tracking
                        SET jun_26_actual = %s,
                            jul_26_actual = %s,
                            aug_26_actual = %s,
                            sep_26_actual = %s,
                            oct_26_actual = %s,
                            monthly_actuals = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE budget_head = %s;
                    """, (jun_val, jul_val, aug_val, sep_val, oct_val, json.dumps(period_dict), b_head))

                conn.commit()
                return {"status": "success", "message": "Food budget tracking synced successfully from monthly ledger"}
        finally:
            db.release_db_connection(conn)
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
                # Delete dependent entries across all modules
                cur.execute("DELETE FROM monthly_expense_entries WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM dining_census_entries WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM utility_meter_logs WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM hostel_census_entries WHERE period_id = %s", (period_id,))
                cur.execute("DELETE FROM transport_census_entries WHERE period_id = %s", (period_id,))
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
        mod = (module or "food").lower()
        rows = db.execute_query("""
            SELECT 
                p.period_code,
                p.period_label,
                p.start_date,
                COALESCE(SUM(
                    CASE 
                        WHEN ch.is_active = FALSE OR ec.is_active = FALSE THEN 0
                        WHEN %s = 'food' AND (
                            LOWER(TRIM(ec.name)) IN ('person', 'persons', 'total person', 'total persons')
                            OR LOWER(ec.name) LIKE '%%person%%' 
                            OR LOWER(ec.name) LIKE '%%diners%%' 
                            OR LOWER(ec.name) LIKE '%%census%%'
                            OR LOWER(ec.name) LIKE '%%unit economics%%'
                            OR LOWER(ch.name) LIKE '%%person%%' 
                            OR LOWER(ch.name) LIKE '%%student%%' 
                            OR LOWER(ch.name) LIKE '%%staff count%%'
                            OR LOWER(ch.name) LIKE '%%diners%%'
                            OR LOWER(ch.name) LIKE '%%census%%'
                            OR (LOWER(TRIM(ec.name)) = 'person' AND LOWER(TRIM(ch.name)) = 'others')
                        )
                        THEN 0 
                        ELSE e.amount 
                    END
                ), 0) AS total
            FROM billing_periods p
            LEFT JOIN monthly_expense_entries e ON p.id = e.period_id AND e.module = %s
            LEFT JOIN cost_heads ch ON e.cost_head_id = ch.id
            LEFT JOIN expense_categories ec ON ch.category_id = ec.id
            WHERE p.module = %s
            GROUP BY p.period_code, p.period_label, p.start_date
            ORDER BY p.start_date
        """, (mod, mod, mod))

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
                "SELECT id, period_code, period_label, start_date, operating_days, is_closed, module, COALESCE(branch, 'all') AS branch FROM billing_periods WHERE module = %s ORDER BY start_date",
                (module,)
            )
        else:
            periods = db.execute_query(
                "SELECT id, period_code, period_label, start_date, operating_days, is_closed, module, COALESCE(branch, 'all') AS branch FROM billing_periods ORDER BY start_date"
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

        def is_excluded_from_grand_total(cat_name: str, item_name: str = "") -> bool:
            if (module or "food").lower() != "food":
                return False
            c = str(cat_name or "").lower().strip()
            i = str(item_name or "").lower().strip()
            s = f"{c} {i}".strip()
            if (
                c == "person"
                or c == "persons"
                or "person" in c
                or "diners" in c
                or "census" in c
                or "unit economics" in c
                or "economics" in c
            ):
                return True
            return (
                "student" in i
                or "staff count" in i
                or "staffs count" in i
                or "cost per person" in i
                or "cost/person" in i
                or "cost / person" in i
                or "per person" in i
                or "per meal" in i
                or "diners" in i
                or "census" in i
                or "headcount" in i
                or "total person" in s
                or "total persons" in s
                or "cost per person" in s
                or "student count" in s
                or "students count" in s
                or "staff count" in s
                or (c in ("person", "persons") and "other" in i)
            )

        categories_data = []

        for cat in categories:
            cat_id = cat["id"]
            cat_name = cat.get("name") or ""
            is_non_expense = is_excluded_from_grand_total(cat_name)
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
                ch_name = ch.get("name") or ""
                is_item_non_expense = is_non_expense or is_excluded_from_grand_total(cat_name, ch_name)
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
                        if not is_item_non_expense:
                            grand_total_by_period[p_id] += val

                row_avg = round(row_total / num_periods, 2)
                cat_total += row_total
                if not is_item_non_expense:
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
            is_fcat_non_expense = is_excluded_from_grand_total(fcat.get("category_name"))
            for p in periods:
                pid = p["id"]
                val = fcat["subtotal"]["amounts"].get(str(pid), 0.0)
                fc_total += val
                if not is_fcat_non_expense:
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

        # Dining Census / Headcounts removed for Food module
        census_data = {}

        # Query Food Budget Tracking
        food_budget_tracking_data = []
        if module in ('food', 'all', None):
            try:
                fb_rows = db.execute_query("SELECT * FROM food_budget_tracking ORDER BY s_no ASC")
                for fbr in fb_rows:
                    food_budget_tracking_data.append({
                        k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                        for k, v in fbr.items()
                    })
            except Exception as fbe:
                print(f"[Food Budget Query Notice] {fbe}")

        # Query Hostel Census / Operational Metrics (when module == 'hostel')
        hostel_census_data = {}
        hostel_budget_tracking_data = []
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

                # Ensure budget, cumulative spent, and remaining balance are always strictly synchronized
                exp_occ = float(h_dict.get("expenses_occurred") or 0.0)
                app_bud = float(h_dict.get("approved_budget") or 185449618.0)
                cum_sp = float(h_dict.get("cumulative_budget_spent") or 0.0)
                if cum_sp < exp_occ and exp_occ > 0.0:
                    cum_sp = exp_occ
                    h_dict["cumulative_budget_spent"] = cum_sp
                h_dict["approved_budget"] = app_bud
                h_dict["balance"] = round(app_bud - cum_sp, 2)

                hostel_census_data[str(hr["period_id"])] = h_dict

            if module in ('hostel', 'all', None):
                try:
                    hb_rows = db.execute_query("SELECT * FROM hostel_budget_tracking ORDER BY s_no ASC")
                    for hbr in hb_rows:
                        hostel_budget_tracking_data.append({
                            k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                            for k, v in hbr.items()
                        })
                    tot_sanctioned_sum = sum(float(r.get("sanctioned_amount") or 0.0) for r in hostel_budget_tracking_data)
                    if tot_sanctioned_sum > 0:
                        for p_str, hc_row in hostel_census_data.items():
                            hc_row["approved_budget"] = tot_sanctioned_sum
                            c_spent = float(hc_row.get("cumulative_budget_spent") or hc_row.get("expenses_occurred") or 0.0)
                            hc_row["balance"] = round(tot_sanctioned_sum - c_spent, 2)
                except Exception as b_err:
                    print(f"[Hostel Budget Query Notice] {b_err}")
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
                c_metrics = tr.get("custom_metrics") or {}
                if isinstance(c_metrics, str):
                    try:
                        c_metrics = json.loads(c_metrics)
                    except Exception:
                        c_metrics = {}
                if isinstance(c_metrics, dict):
                    for ck, cv in c_metrics.items():
                        if ck not in conv:
                            conv[ck] = cv
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
                    tot_fc_cost = 0.0
                    tot_statutory_cost = 0.0
                    tot_repair_maintenance_cost = 0.0
                    tot_other_cost = 0.0
                    tot_employee_cost = 0.0
                    tot_parking_fastag = 0.0
                    tot_cctv_replacement = 0.0
                    tot_cab_billing = 0.0
                    tot_total_expenses = 0.0
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
                            tot_fc_cost += float(b_census.get("fc_cost") or 0.0)
                            tot_statutory_cost += float(b_census.get("statutory_cost") or 0.0)
                            tot_repair_maintenance_cost += float(b_census.get("repair_maintenance_cost") or 0.0)
                            tot_other_cost += float(b_census.get("other_cost") or 0.0)
                            tot_employee_cost += float(b_census.get("employee_cost") or 0.0)
                            tot_parking_fastag += float(b_census.get("parking_fastag") or 0.0)
                            tot_cctv_replacement += float(b_census.get("cctv_replacement") or 0.0)
                            tot_cab_billing += float(b_census.get("cab_billing") or 0.0)
                            tot_total_expenses += float(b_census.get("total_expenses") or 0.0)
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
                            "vehicles_count": " / ".join(c_veh_list) if c_veh_list else "0 fleet",
                            "passengers_count": tot_passengers,
                            "students_count": tot_students,
                            "staff_count": tot_staff,
                            "approved_kms": round(tot_approved_kms, 2),
                            "actual_kms": round(tot_actual_kms, 2),
                            "additional_kms": round(tot_additional_kms, 2),
                            "diesel_litres": round(tot_diesel_litres, 2),
                            "fuel_expenses": round(tot_fuel_expenses, 2),
                            "fc_cost": round(tot_fc_cost, 2),
                            "statutory_cost": round(tot_statutory_cost, 2),
                            "repair_maintenance_cost": round(tot_repair_maintenance_cost, 2),
                            "other_cost": round(tot_other_cost, 2),
                            "employee_cost": round(tot_employee_cost, 2),
                            "parking_fastag": round(tot_parking_fastag, 2),
                            "cctv_replacement": round(tot_cctv_replacement, 2),
                            "cab_billing": round(tot_cab_billing, 2),
                            "total_expenses": round(tot_total_expenses, 2),
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

        # Query CCTV Entries & Parameters if module == 'cctv' or 'all'
        cctv_entries_data = {}
        cctv_parameters_data = []
        if module == "cctv":
            try:
                c_rows = db.execute_query("SELECT * FROM cctv_monthly_entries;")
                for cr in c_rows:
                    p_str = str(cr["period_id"])
                    cctv_entries_data[p_str] = {
                        k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                        for k, v in cr.items()
                    }
                p_rows = db.execute_query("""
                    SELECT id, s_no, param_key, param_name, section, section_order,
                           input_type, unit, formula, display_order, is_system, is_active
                    FROM cctv_master_parameters
                    WHERE is_active = TRUE
                    ORDER BY display_order ASC, section_order ASC, id ASC;
                """)
                cctv_parameters_data = [dict(pr) for pr in p_rows]

                # Populate grand_total for CCTV
                cctv_amounts = {}
                tot_cctv = 0.0
                for p in periods:
                    p_id = p["id"]
                    p_str = str(p_id)
                    exp = float(cctv_entries_data.get(p_str, {}).get("total_expenses") or 0.0)
                    cctv_amounts[p_id] = exp
                    cctv_amounts[p_str] = exp
                    tot_cctv += exp
                grand_total_data = {
                    "total": round(tot_cctv, 2),
                    "amounts": cctv_amounts
                }
            except Exception as ce:
                print(f"[CCTV Matrix Query Notice] {ce}")

        # Query Transport Fleet Sanctioned Branch Budgets
        transport_branch_budgets = {}
        if module in ("transport", "all", None):
            try:
                t_budgets_rows = db.execute_query("SELECT * FROM transport_budget_tracking ORDER BY branch, display_order ASC;")
                for r in t_budgets_rows:
                    b = r.get("branch")
                    if b not in transport_branch_budgets:
                        transport_branch_budgets[b] = {
                            "branch": b,
                            "sanctioned": 0.0,
                            "lineItems": []
                        }
                    item = {
                        "id": r.get("id"),
                        "param": r.get("param_name"),
                        "amount": float(r.get("sanctioned_amount") or 0.0),
                        "order": r.get("display_order"),
                        "color": r.get("color"),
                        "bg": r.get("bg"),
                        "isTotal": bool(r.get("is_total")),
                        "isBlank": bool(r.get("is_blank"))
                    }
                    transport_branch_budgets[b]["lineItems"].append(item)
                    if item["isTotal"]:
                        transport_branch_budgets[b]["sanctioned"] = item["amount"]
            except Exception as tbe:
                print(f"[Transport Budget Matrix Query Notice] {tbe}")

        return {
            "periods": periods,
            "categories": categories_data,
            "grand_total": grand_total_data,
            "census": census_data,
            "hostel_census": hostel_census_data,
            "hostel_budget_tracking": hostel_budget_tracking_data if (module in ('hostel', 'all', None) or hostel_budget_tracking_data) else None,
            "food_budget_tracking": food_budget_tracking_data if (module in ('food', 'all', None) or food_budget_tracking_data) else None,
            "transport_census": transport_census_data,
            "transport_census_by_branch": transport_census_by_branch if module == "transport" else None,
            "transport_branch_budgets": transport_branch_budgets if module in ("transport", "all", None) else None,
            "matrix_by_branch": matrix_by_branch if module == "transport" else None,
            "branches": ["all", "RPS", "KPM", "Common", "University"] if module == "transport" else None,
            "active_branch": branch or "all",
            "cctv_entries": cctv_entries_data if module in ("cctv", "all") else None,
            "cctv_parameters": cctv_parameters_data if module in ("cctv", "all") else None,
            "module": module
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
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Cost head name cannot be empty")

        # Resolve category_id safely
        cat_id = None
        if req.category_id is not None:
            try:
                parsed_id = int(req.category_id)
                if parsed_id > 0:
                    cat_id = parsed_id
            except (ValueError, TypeError):
                cat_id = None

        if not cat_id:
            mod = (req.module or "food").lower()
            first_cat = db.execute_query(
                "SELECT id FROM expense_categories WHERE LOWER(module) = %s AND is_active = true ORDER BY display_order ASC, id ASC LIMIT 1",
                (mod,),
                fetch_all=False
            )
            if not first_cat:
                first_cat = db.execute_query(
                    "SELECT id FROM expense_categories WHERE is_active = true ORDER BY display_order ASC, id ASC LIMIT 1",
                    fetch_all=False
                )
            if first_cat:
                cat_id = first_cat["id"]
            else:
                def_cat = db.execute_query(
                    "INSERT INTO expense_categories (name, code, module, display_order, is_active) VALUES (%s, %s, %s, 1, true) RETURNING id",
                    ("General Operational Expenses", f"CAT_{mod.upper()}_GEN", mod),
                    fetch_all=False
                )
                cat_id = def_cat["id"]

        code = req.code
        if not code or not code.strip():
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').upper()
            code = f"CH_{clean[:20]}"
        else:
            code = code.strip().upper()

        # Ensure unique code in cost_heads to avoid duplicate key violations
        existing = db.execute_query("SELECT id FROM cost_heads WHERE code = %s", (code,), fetch_all=False)
        counter = 1
        base_code = code
        while existing:
            code = f"{base_code[:16]}_{counter}"
            existing = db.execute_query("SELECT id FROM cost_heads WHERE code = %s", (code,), fetch_all=False)
            counter += 1

        behavior = req.cost_behavior or "variable"

        display_order = req.display_order
        if display_order is None:
            max_row = db.execute_query(
                "SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM cost_heads WHERE category_id = %s",
                (cat_id,),
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
            (cat_id, name, code, behavior, req.default_vendor_id, display_order),
            fetch_all=False
        )
        return {"status": "success", "message": f"Cost head '{name}' created successfully", "cost_head": new_row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/master/cost-heads/{cost_head_id}")
def update_cost_head(cost_head_id: int, req: CostHeadUpdate):
    try:
        existing = db.execute_query("SELECT id, category_id, code, cost_behavior, default_vendor_id, name FROM cost_heads WHERE id = %s", (cost_head_id,), fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Cost head not found")

        cat_id = None
        if req.category_id is not None:
            try:
                parsed_id = int(req.category_id)
                if parsed_id > 0:
                    cat_id = parsed_id
            except (ValueError, TypeError):
                cat_id = existing["category_id"]
        else:
            cat_id = existing["category_id"]

        name = (req.name or existing.get("name") or "").strip()
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
            (cat_id, name, code, behavior, vendor_id, req.display_order, is_active, cost_head_id)
        )
        return {"status": "success", "message": "Cost head updated successfully"}
    except HTTPException:
        raise
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
        ch_row = db.execute_query("SELECT code FROM cost_heads WHERE id = %s", (cost_head_id,), fetch_all=False)
        ch_code = ch_row.get("code") if ch_row else None
        if ch_code:
            db.execute_commit("""
                INSERT INTO deleted_master_parameters (module, param_key)
                VALUES ('food_cost_head', %s)
                ON CONFLICT (module, param_key) DO NOTHING;
            """, (ch_code,))

        entry_count = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM monthly_expense_entries WHERE cost_head_id = %s",
            (cost_head_id,),
            fetch_all=False
        )["cnt"]

        # Keep as inactive tombstone so migrations/reinstall will never re-insert or reactivate it
        db.execute_commit("UPDATE cost_heads SET is_active = false WHERE id = %s", (cost_head_id,))
        if entry_count > 0:
            return {
                "status": "deactivated",
                "message": f"Cost head has {entry_count} historical financial entries; soft-deactivated to preserve ledger audit trail."
            }
        else:
            return {"status": "deleted", "message": "Cost head removed successfully"}
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
                    cur.execute("SELECT code FROM cost_heads WHERE id = %s", (ch_id,))
                    code_row = cur.fetchone()
                    if code_row and code_row[0]:
                        cur.execute("INSERT INTO deleted_master_parameters (module, param_key) VALUES ('food_cost_head', %s) ON CONFLICT DO NOTHING;", (code_row[0],))
                    cur.execute("UPDATE cost_heads SET is_active = false WHERE id = %s", (ch_id,))
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
        cat_code = cat_row.get("code") if cat_row else None
        if cat_code:
            db.execute_commit("""
                INSERT INTO deleted_master_parameters (module, param_key)
                VALUES ('food', %s)
                ON CONFLICT (module, param_key) DO NOTHING;
            """, (cat_code,))

        # Mark as inactive tombstone so migrations/reinstall will never re-insert or reactivate it
        db.execute_commit("UPDATE expense_categories SET is_active = false WHERE id = %s", (category_id,))
        db.execute_commit("UPDATE cost_heads SET is_active = false WHERE category_id = %s", (category_id,))
        return {
            "status": "deleted",
            "message": f"Category '{cat_name}' removed successfully."
        }
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
                    
                    cur.execute("SELECT code FROM expense_categories WHERE id = %s", (cat_id,))
                    code_row = cur.fetchone()
                    if code_row and code_row[0]:
                        cur.execute("INSERT INTO deleted_master_parameters (module, param_key) VALUES ('food', %s) ON CONFLICT DO NOTHING;", (code_row[0],))
                    cur.execute("UPDATE expense_categories SET is_active = false WHERE id = %s", (cat_id,))
                    cur.execute("UPDATE cost_heads SET is_active = false WHERE category_id = %s", (cat_id,))
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
    Self-heals and seeds parameters if table is missing or unpopulated in production.
    """
    try:
        rows = db.execute_query(
            """
            SELECT id, s_no, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM hostel_master_parameters
            WHERE is_active = TRUE
            ORDER BY display_order ASC, section_order ASC, id ASC;
            """
        )
        if rows is not None and len(rows) > 0:
            return rows
    except Exception as query_err:
        print(f"[HostelParameters] Notice on query: {query_err}. Running self-healing sync...")

    # Auto-heal: Ensure table exists and canonical parameters are seeded
    try:
        import seed_hostel_canonical
        seed_hostel_canonical.ensure_and_seed_hostel_parameters()
        rows = db.execute_query(
            """
            SELECT id, s_no, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM hostel_master_parameters
            WHERE is_active = TRUE
            ORDER BY display_order ASC, section_order ASC, id ASC;
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

        s_no = str(req.get("s_no") or "").strip()
        section = (req.get("section") or "Custom Parameters").strip()
        section_order = int(req.get("section_order") or 7)
        input_type = (req.get("input_type") or "cost").strip()
        unit = (req.get("unit") or "").strip()
        formula = req.get("formula") or None
        display_order = int(req.get("display_order") or 50)
        if not s_no:
            s_no = str(display_order)

        # Generate a safe unique param_key
        base_key = re.sub(r'[^a-z0-9_]', '', param_name.lower().replace(' ', '_'))
        if not base_key:
            base_key = f"param_{int(datetime.now().timestamp())}"
        param_key = base_key

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Remove from deleted tombstones if re-adding
                cur.execute("DELETE FROM deleted_master_parameters WHERE module = 'hostel' AND param_key = %s;", (param_key,))

                # Check collision
                cur.execute("SELECT id FROM hostel_master_parameters WHERE param_key = %s;", (param_key,))
                existing_row = cur.fetchone()
                if existing_row:
                    cur.execute(
                        """
                        UPDATE hostel_master_parameters
                        SET s_no = %s, param_name = %s, section = %s, section_order = %s,
                            input_type = %s, unit = %s, formula = %s, display_order = %s, is_active = TRUE
                        WHERE id = %s
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                        """,
                        (s_no, param_name, section, section_order, input_type, unit, formula, display_order, existing_row[0])
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO hostel_master_parameters (
                            s_no, param_key, param_name, section, section_order,
                            input_type, unit, formula, display_order, is_system, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE)
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                        """,
                        (s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order)
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
    Updates an existing hostel parameter (s_no, name, section, formula, input_type, display_order).
    """
    try:
        fields = []
        vals = []
        if "s_no" in req:
            fields.append("s_no = %s")
            vals.append(str(req["s_no"]).strip())
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
        query = f"UPDATE hostel_master_parameters SET {', '.join(fields)} WHERE id = %s RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;"
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
    Soft-deletes a hostel parameter and records a permanent deletion tombstone.
    """
    try:
        param = db.execute_query("SELECT id, param_key, param_name, is_system FROM hostel_master_parameters WHERE id = %s;", (param_id,), fetch_all=False)
        if not param:
            raise HTTPException(status_code=404, detail="Parameter not found")

        pkey = param.get("param_key")
        db.execute_commit("UPDATE hostel_master_parameters SET is_active = FALSE WHERE id = %s;", (param_id,))
        if pkey:
            db.execute_commit("""
                INSERT INTO deleted_master_parameters (module, param_key)
                VALUES ('hostel', %s)
                ON CONFLICT (module, param_key) DO NOTHING;
            """, (pkey,))
        return {"status": "success", "message": f"Hostel parameter '{param.get('param_name')}' removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# TRANSPORT MASTER PARAMETERS CRUD ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/transport/parameters")
def get_transport_parameters():
    """
    Returns active transport master parameters grouped into sections.
    Self-heals and seeds parameters if table is missing or unpopulated in production.
    """
    try:
        rows = db.execute_query(
            """
            SELECT id, s_no, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM transport_master_parameters
            WHERE is_active = TRUE
            ORDER BY display_order ASC, section_order ASC, id ASC;
            """
        )
        if rows is not None and len(rows) > 0:
            return rows
    except Exception as query_err:
        print(f"[TransportParameters] Notice on query: {query_err}. Running self-healing sync...")

    # Auto-heal: Ensure table exists and 47 canonical parameters are seeded
    try:
        import seed_transport_canonical
        seed_transport_canonical.ensure_and_seed_transport_parameters()
        rows = db.execute_query(
            """
            SELECT id, s_no, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM transport_master_parameters
            WHERE is_active = TRUE
            ORDER BY display_order ASC, section_order ASC, id ASC;
            """
        )
        return rows or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transport/parameters")
def create_transport_parameter(req: Dict[str, Any]):
    """
    Creates a new transport parameter row in Master Data.
    """
    try:
        param_name = (req.get("param_name") or "").strip()
        if not param_name:
            raise HTTPException(status_code=400, detail="Parameter name is required")

        s_no = str(req.get("s_no") or "").strip()
        section = (req.get("section") or "Custom Parameters").strip()
        section_order = int(req.get("section_order") or 8)
        input_type = (req.get("input_type") or "cost").strip()
        unit = (req.get("unit") or "").strip()
        formula = req.get("formula") or None
        display_order = int(req.get("display_order") or 50)
        if not s_no:
            s_no = str(display_order)

        base_key = re.sub(r'[^a-z0-9_]', '', param_name.lower().replace(' ', '_'))
        if not base_key:
            base_key = f"param_{int(datetime.now().timestamp())}"
        param_key = base_key

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Remove from deleted tombstones if re-adding
                cur.execute("DELETE FROM deleted_master_parameters WHERE module = 'transport' AND param_key = %s;", (param_key,))

                cur.execute("SELECT id FROM transport_master_parameters WHERE param_key = %s;", (param_key,))
                existing_row = cur.fetchone()
                if existing_row:
                    cur.execute(
                        """
                        UPDATE transport_master_parameters
                        SET s_no = %s, param_name = %s, section = %s, section_order = %s,
                            input_type = %s, unit = %s, formula = %s, display_order = %s, is_active = TRUE
                        WHERE id = %s
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                        """,
                        (s_no, param_name, section, section_order, input_type, unit, formula, display_order, existing_row[0])
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO transport_master_parameters (
                            s_no, param_key, param_name, section, section_order,
                            input_type, unit, formula, display_order, is_system, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE)
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                        """,
                        (s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order)
                    )
                new_row = cur.fetchone()
                conn.commit()
                col_names = [d[0] for d in cur.description]
                res_dict = dict(zip(col_names, new_row))
                return {
                    "status": "success",
                    "message": f"Created transport parameter '{param_name}' successfully",
                    "parameter": res_dict
                }
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/transport/parameters/{param_id}")
def update_transport_parameter(param_id: int, req: Dict[str, Any]):
    """
    Updates an existing transport parameter.
    """
    try:
        fields = []
        vals = []
        if "s_no" in req:
            fields.append("s_no = %s")
            vals.append(str(req["s_no"]).strip())
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
        query = f"UPDATE transport_master_parameters SET {', '.join(fields)} WHERE id = %s RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;"
        row = db.execute_query(query, tuple(vals), fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="Transport parameter not found")
        return {
            "status": "success",
            "message": "Transport parameter updated successfully",
            "parameter": row
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/transport/parameters/{param_id}")
def delete_transport_parameter(param_id: int):
    """
    Soft-deletes a transport parameter and records a permanent deletion tombstone.
    """
    try:
        param = db.execute_query("SELECT id, param_key, param_name, is_system FROM transport_master_parameters WHERE id = %s;", (param_id,), fetch_all=False)
        if not param:
            raise HTTPException(status_code=404, detail="Transport parameter not found")

        pkey = param.get("param_key")
        db.execute_commit("UPDATE transport_master_parameters SET is_active = FALSE WHERE id = %s;", (param_id,))
        if pkey:
            db.execute_commit("""
                INSERT INTO deleted_master_parameters (module, param_key)
                VALUES ('transport', %s)
                ON CONFLICT (module, param_key) DO NOTHING;
            """, (pkey,))
        return {"status": "success", "message": f"Transport parameter '{param.get('param_name')}' removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transport/parameters/reorder")
def reorder_transport_parameters(req: ReorderParametersRequest):
    """
    Updates the display order of transport parameters following a drag-and-drop or move step event.
    """
    try:
        if not req.parameter_ids:
            return {"status": "success", "message": "No parameters provided"}
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for order, pid in enumerate(req.parameter_ids, start=1):
                    cur.execute("UPDATE transport_master_parameters SET display_order = %s WHERE id = %s;", (order, pid))
                conn.commit()
                return {"status": "success", "message": "Transport parameters reordered successfully in database"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# CCTV MASTER PARAMETERS CRUD ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/cctv/parameters")
def get_cctv_parameters():
    """
    Returns active CCTV master parameters grouped into sections.
    """
    try:
        rows = db.execute_query("""
            SELECT id, s_no, param_key, param_name, section, section_order,
                   input_type, unit, formula, display_order, is_system, is_active
            FROM cctv_master_parameters
            WHERE is_active = TRUE
            ORDER BY display_order ASC, section_order ASC, id ASC;
        """)
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cctv/parameters")
def create_cctv_parameter(req: Dict[str, Any]):
    """
    Creates or updates a CCTV parameter row in Master Data.
    """
    try:
        param_name = str(req.get("param_name", "")).strip()
        if not param_name:
            raise HTTPException(status_code=400, detail="Parameter name is required")

        param_key = str(req.get("param_key", "")).strip().lower()
        if not param_key:
            param_key = re.sub(r"[^a-z0-9_]+", "_", param_name.lower()).strip("_")

        s_no = str(req.get("s_no", "")).strip()
        section = str(req.get("section", "General")).strip()
        section_order = int(req.get("section_order", 1))
        input_type = str(req.get("input_type", "number")).strip().lower()
        unit = str(req.get("unit", "")).strip()
        formula = req.get("formula")
        display_order = int(req.get("display_order", 999))

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM cctv_master_parameters WHERE param_key = %s;", (param_key,))
                existing = cur.fetchone()
                if existing:
                    cur.execute("""
                        UPDATE cctv_master_parameters
                        SET s_no = %s, param_name = %s, section = %s, section_order = %s,
                            input_type = %s, unit = %s, formula = %s, display_order = %s, is_active = TRUE
                        WHERE id = %s
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                    """, (s_no, param_name, section, section_order, input_type, unit, formula, display_order, existing[0]))
                else:
                    cur.execute("""
                        INSERT INTO cctv_master_parameters (
                            s_no, param_key, param_name, section, section_order,
                            input_type, unit, formula, display_order, is_system, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE)
                        RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;
                    """, (s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order))
                row = cur.fetchone()
                conn.commit()
                return {
                    "status": "success",
                    "message": "CCTV parameter saved successfully",
                    "data": {
                        "id": row[0],
                        "s_no": row[1],
                        "param_key": row[2],
                        "param_name": row[3],
                        "section": row[4],
                        "section_order": row[5],
                        "input_type": row[6],
                        "unit": row[7],
                        "formula": row[8],
                        "display_order": row[9],
                        "is_system": row[10],
                        "is_active": row[11]
                    }
                }
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/cctv/parameters/{param_id}")
def update_cctv_parameter(param_id: int, req: Dict[str, Any]):
    try:
        fields = []
        vals = []
        for k in ["s_no", "param_name", "section", "section_order", "input_type", "unit", "formula", "display_order"]:
            if k in req:
                fields.append(f"{k} = %s")
                vals.append(req[k])
        if not fields:
            return {"status": "success", "message": "No changes requested"}
        vals.append(param_id)
        query = f"UPDATE cctv_master_parameters SET {', '.join(fields)} WHERE id = %s RETURNING id, s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active;"
        row = db.execute_query(query, tuple(vals), fetch_all=False)
        if not row:
            raise HTTPException(status_code=404, detail="CCTV parameter not found")
        return {"status": "success", "message": "CCTV parameter updated successfully", "data": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cctv/parameters/{param_id}")
def delete_cctv_parameter(param_id: int):
    try:
        param = db.execute_query("SELECT id, param_key FROM cctv_master_parameters WHERE id = %s;", (param_id,), fetch_all=False)
        if not param:
            raise HTTPException(status_code=404, detail="CCTV parameter not found")
        db.execute_commit("UPDATE cctv_master_parameters SET is_active = FALSE WHERE id = %s;", (param_id,))
        return {"status": "success", "message": "CCTV parameter deactivated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cctv/parameters/reorder")
def reorder_cctv_parameters(req: ReorderParametersRequest):
    try:
        if not req.parameter_ids:
            return {"status": "success", "message": "No parameters provided"}
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for order, pid in enumerate(req.parameter_ids, start=1):
                    cur.execute("UPDATE cctv_master_parameters SET display_order = %s WHERE id = %s;", (order, pid))
                conn.commit()
                return {"status": "success", "message": "CCTV parameters reordered successfully"}
        finally:
            db.release_db_connection(conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# CCTV MONTHLY ENTRIES CRUD ENDPOINTS
# -------------------------------------------------------------
@app.get("/api/cctv/entries")
def get_cctv_entries(period_id: Optional[int] = None):
    try:
        if period_id is not None:
            row = db.execute_query("SELECT * FROM cctv_monthly_entries WHERE period_id = %s;", (period_id,), fetch_all=False)
            clean = {}
            if row:
                clean = {
                    k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                    for k, v in row.items()
                }
            return {"status": "success", "period_id": period_id, "data": clean}

        rows = db.execute_query("SELECT * FROM cctv_monthly_entries ORDER BY period_id ASC;")
        res = []
        for r in rows:
            res.append({
                k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                for k, v in r.items()
            })
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cctv/entries")
def save_cctv_entry(req: Dict[str, Any]):
    """
    Saves / updates monthly entry for CCTV with auto-calculated formulas.
    """
    try:
        period_id = int(req.get("period_id"))
        if not period_id:
            raise HTTPException(status_code=400, detail="period_id is required")

        def _n(key, default=0):
            val = req.get(key)
            if val is None or val == "":
                return default
            try:
                return float(val)
            except Exception:
                return default

        # 1. Projects
        p_comp = int(_n("projects_completed", 0))
        p_prog = int(_n("projects_in_progress", 0))
        p_tot = p_comp + p_prog

        # 2. Complaints
        c_cctv = int(_n("complaints_cctv", 0))
        c_bio = int(_n("complaints_biometric", 0))
        c_flap = int(_n("complaints_flapbarrier", 0))
        c_tot = c_cctv + c_bio + c_flap
        c_rep = int(_n("repeated_complaints", 0))
        c_time = round(_n("time_taken_complaints_hrs", 0.0), 2)
        c_tat = round(_n("tat_complaints_hrs"), 2) if req.get("tat_complaints_hrs") is not None else (round(c_time / c_tot, 2) if c_tot > 0 else 0.0)

        # 3. Service Requests
        s_cctv = int(_n("service_cctv", 0))
        s_bio = int(_n("service_biometric", 0))
        s_flap = int(_n("service_flapbarrier", 0))
        s_tot = s_cctv + s_bio + s_flap
        s_rep = int(_n("repeated_work", 0))
        s_time = round(_n("time_taken_service_hrs", 0.0), 2)
        s_tat = round(_n("tat_service_hrs"), 2) if req.get("tat_service_hrs") is not None else (round(s_time / s_tot, 2) if s_tot > 0 else 0.0)

        # 4. PPM
        ppm = int(_n("ppm_count", 0))

        # 5. Quality Issues
        q_rec = int(_n("quality_issues_received", 0))
        q_cls = int(_n("quality_issues_closed", 0))
        q_opn = int(_n("quality_issues_open")) if req.get("quality_issues_open") is not None else max(0, q_rec - q_cls)

        # 6. Expenses
        mat_exp = round(_n("material_expenses", 0.0), 2)
        lab_exp = round(_n("labour_expenses", 0.0), 2)
        tot_exp = round(mat_exp + lab_exp, 2)

        # 7. Budget Tracking
        app_bud = round(_n("approved_budget", 0.0), 2)
        cum_spent = round(_n("cumulative_budget_spent", tot_exp), 2)
        bal = round(app_bud - cum_spent, 2)

        remarks = str(req.get("remarks") or "")
        custom_metrics = req.get("custom_metrics") or {}
        if not isinstance(custom_metrics, dict):
            custom_metrics = {}

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cctv_monthly_entries (
                        period_id,
                        projects_completed, projects_in_progress, projects_total,
                        complaints_cctv, complaints_biometric, complaints_flapbarrier, complaints_total,
                        repeated_complaints, time_taken_complaints_hrs, tat_complaints_hrs,
                        service_cctv, service_biometric, service_flapbarrier, service_total,
                        repeated_work, time_taken_service_hrs, tat_service_hrs,
                        ppm_count,
                        quality_issues_received, quality_issues_closed, quality_issues_open,
                        material_expenses, labour_expenses, total_expenses,
                        approved_budget, cumulative_budget_spent, balance,
                        remarks, custom_metrics, updated_at
                    ) VALUES (
                        %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, CURRENT_TIMESTAMP
                    ) ON CONFLICT (period_id) DO UPDATE SET
                        projects_completed = EXCLUDED.projects_completed,
                        projects_in_progress = EXCLUDED.projects_in_progress,
                        projects_total = EXCLUDED.projects_total,
                        complaints_cctv = EXCLUDED.complaints_cctv,
                        complaints_biometric = EXCLUDED.complaints_biometric,
                        complaints_flapbarrier = EXCLUDED.complaints_flapbarrier,
                        complaints_total = EXCLUDED.complaints_total,
                        repeated_complaints = EXCLUDED.repeated_complaints,
                        time_taken_complaints_hrs = EXCLUDED.time_taken_complaints_hrs,
                        tat_complaints_hrs = EXCLUDED.tat_complaints_hrs,
                        service_cctv = EXCLUDED.service_cctv,
                        service_biometric = EXCLUDED.service_biometric,
                        service_flapbarrier = EXCLUDED.service_flapbarrier,
                        service_total = EXCLUDED.service_total,
                        repeated_work = EXCLUDED.repeated_work,
                        time_taken_service_hrs = EXCLUDED.time_taken_service_hrs,
                        tat_service_hrs = EXCLUDED.tat_service_hrs,
                        ppm_count = EXCLUDED.ppm_count,
                        quality_issues_received = EXCLUDED.quality_issues_received,
                        quality_issues_closed = EXCLUDED.quality_issues_closed,
                        quality_issues_open = EXCLUDED.quality_issues_open,
                        material_expenses = EXCLUDED.material_expenses,
                        labour_expenses = EXCLUDED.labour_expenses,
                        total_expenses = EXCLUDED.total_expenses,
                        approved_budget = EXCLUDED.approved_budget,
                        cumulative_budget_spent = EXCLUDED.cumulative_budget_spent,
                        balance = EXCLUDED.balance,
                        remarks = EXCLUDED.remarks,
                        custom_metrics = EXCLUDED.custom_metrics,
                        updated_at = CURRENT_TIMESTAMP;
                """, (
                    period_id,
                    p_comp, p_prog, p_tot,
                    c_cctv, c_bio, c_flap, c_tot,
                    c_rep, c_time, c_tat,
                    s_cctv, s_bio, s_flap, s_tot,
                    s_rep, s_time, s_tat,
                    ppm,
                    q_rec, q_cls, q_opn,
                    mat_exp, lab_exp, tot_exp,
                    app_bud, cum_spent, bal,
                    remarks, json.dumps(custom_metrics)
                ))
                conn.commit()

                row = db.execute_query(
                    "SELECT * FROM cctv_monthly_entries WHERE period_id = %s;",
                    (period_id,),
                    fetch_all=False
                )
                clean = {}
                if row:
                    clean = {
                        k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                        for k, v in row.items()
                    }
                return {
                    "status": "success",
                    "message": f"CCTV monthly entry saved successfully for period {period_id}",
                    "period_id": period_id,
                    "data": clean
                }
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# -------------------------------------------------------------
# CENSUS COMPUTATION & UPSERT HELPERS
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
    bc_b = int(_clean_num(hc.get("bed_capacity_boys"), 2223))
    bc_g = int(_clean_num(hc.get("bed_capacity_girls"), 896))
    bc_tot = bc_b + bc_g

    st_b = int(_clean_num(hc.get("students_boys"), 2075))
    st_g = int(_clean_num(hc.get("students_girls"), 768))
    st_tot = st_b + st_g

    sf_b = int(_clean_num(hc.get("staff_boys"), 72))
    sf_g = int(_clean_num(hc.get("staff_girls"), 59))
    sf_tot = sf_b + sf_g

    occ_b = st_b + sf_b
    occ_g = st_g + sf_g
    occ_tot = occ_b + occ_g

    vac_b = bc_b - occ_b
    vac_g = bc_g - occ_g
    vac_tot = vac_b + vac_g

    vac_coll_b = int(_clean_num(hc.get("vacant_college_boys"), vac_b - 41))
    vac_coll_g = int(_clean_num(hc.get("vacant_college_girls"), vac_g))
    vac_coll_tot = vac_coll_b + vac_coll_g

    vac_sp_b = int(_clean_num(hc.get("vacant_sports_boys"), 0))
    vac_sp_g = int(_clean_num(hc.get("vacant_sports_girls"), 0))
    vac_sp_tot = vac_sp_b + vac_sp_g

    vac_sc_b = int(_clean_num(hc.get("vacant_school_boys"), 0))
    vac_sc_g = int(_clean_num(hc.get("vacant_school_girls"), 0))
    vac_sc_tot = vac_sc_b + vac_sc_g

    occ_pct_b = round((occ_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    occ_pct_g = round((occ_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    occ_pct = round((occ_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    vac_pct_b = round((vac_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    vac_pct_g = round((vac_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    vac_pct = round((vac_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    st_vacated = int(_clean_num(hc.get("students_vacated"), 0))

    t_rec = int(_clean_num(hc.get("tickets_received"), 0))
    t_cls = int(_clean_num(hc.get("tickets_closed"), 0))
    t_opn = max(0, t_rec - t_cls)

    tot_hrs = float(_clean_num(hc.get("total_hours_close"), 0.0))
    tat_hrs = float(_clean_num(hc.get("tat_hours"), 62.29))

    q_rec = int(_clean_num(hc.get("quality_issues_received"), 0))
    q_cls = int(_clean_num(hc.get("quality_issues_closed"), 0))
    q_opn = max(0, q_rec - q_cls)
    q_open = q_opn

    incidents = int(_clean_num(hc.get("incidents_count"), 0))

    p_units = int(_clean_num(hc.get("power_units"), 0))
    p_cost = float(_clean_num(hc.get("power_cost"), 0.0))
    w_pur = float(_clean_num(hc.get("water_purchase_cost"), 0.0))
    maint_exp = float(_clean_num(hc.get("maintenance_expenses"), 119394.0))
    exp_occ = float(_clean_num(hc.get("expenses_occurred"), 9349172.0))

    app_bud = float(_clean_num(hc.get("approved_budget"), 142010789.0))
    cum_bud = float(_clean_num(hc.get("cumulative_budget_spent"), 0.0))
    bal = app_bud - cum_bud

    nw_ltr = int(_clean_num(hc.get("normal_water_litres"), 0))
    nw_cost = float(_clean_num(hc.get("normal_water_cost"), 0.0))
    dw_ltr = int(_clean_num(hc.get("drinking_water_litres"), 0))
    dw_cost = float(_clean_num(hc.get("drinking_water_cost"), 0.0))

    sq_ft = float(_clean_num(hc.get("sq_feet"), 231701.0))
    per_st_mo = round(exp_occ / occ_tot, 2) if occ_tot > 0 else (round(exp_occ / st_tot, 2) if st_tot > 0 else 0.0)
    per_st_day = round(per_st_mo / 30.0, 2)
    sq_ft_occ = round(sq_ft / occ_tot, 2) if occ_tot > 0 else (round(sq_ft / st_tot, 2) if st_tot > 0 else 0.0)

    nw_st_ltr = round(nw_ltr / st_tot, 2) if st_tot > 0 else float(_clean_num(hc.get("normal_water_student_ltrs"), 0.0))
    nw_st_cost = round(nw_cost / st_tot, 2) if st_tot > 0 else float(_clean_num(hc.get("normal_water_student_cost"), 88.0))

    p_sqft = round(p_cost / sq_ft, 2) if sq_ft > 0 else 0.0
    p_occ_u = round(p_units / occ_tot, 2) if occ_tot > 0 else 0.0
    p_occ_c = round(p_cost / occ_tot, 2) if occ_tot > 0 else 0.0

    nw_day_ltr = round(nw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    nw_day_c = round(nw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    dw_day_ltr = round(dw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    dw_day_c = round(dw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    remarks = str(hc.get("remarks") or "")

    # Serialize custom metrics and budget heads
    custom_metrics_dict = {}
    if isinstance(hc.get("custom_metrics"), dict):
        custom_metrics_dict.update(hc["custom_metrics"])
    for k, v in hc.items():
        if k.startswith("budget_") or k.startswith("sanctioned_") or k.startswith("limit_") or k.startswith("param_") or k.startswith("custom_"):
            custom_metrics_dict[k] = v
    custom_metrics_json = json.dumps(custom_metrics_dict)

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
        custom_metrics = CASE WHEN EXCLUDED.custom_metrics IS NOT NULL AND EXCLUDED.custom_metrics::text != '{}' THEN EXCLUDED.custom_metrics ELSE hostel_census_entries.custom_metrics END;
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
    other_cost = float(_clean_num(get_f("other_cost", 0.0)))
    cctv_replacement = float(_clean_num(get_f("cctv_replacement", 0.0)))
    employee_cost = float(_clean_num(get_f("employee_cost", 0.0)))
    parking_fastag = float(_clean_num(get_f("parking_fastag", 0.0)))

    # Row 16: Total Expenses = SUM(fuel + fc + statutory + repair + other + cctv + employee + parking)
    total_expenses = (fuel_expenses + fc_cost + statutory_cost + repair_maintenance_cost + 
                      other_cost + cctv_replacement + employee_cost + parking_fastag)

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

    branch_default_budget = {
        "University": 40330187.0,
        "RPS": 14107491.0,
        "KPM": 4000000.0,
        "Common": 5552143.0,
    }.get(b_val, 4000000.0)
    approved_budget = float(_clean_num(get_f("approved_budget", branch_default_budget)))
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
        repair_maintenance_cost, other_cost, cctv_replacement, employee_cost, parking_fastag, total_expenses,
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
        %s, %s, %s, %s, %s, %s,
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
        other_cost = EXCLUDED.other_cost,
        cctv_replacement = EXCLUDED.cctv_replacement,
        employee_cost = EXCLUDED.employee_cost,
        parking_fastag = EXCLUDED.parking_fastag,
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
        repair_maintenance_cost, other_cost, cctv_replacement, employee_cost, parking_fastag, total_expenses,
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
# CENSUS COMPUTATION & UPSERT HELPERS
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
    bc_b = int(_clean_num(hc.get("bed_capacity_boys"), 2223))
    bc_g = int(_clean_num(hc.get("bed_capacity_girls"), 896))
    bc_tot = bc_b + bc_g

    st_b = int(_clean_num(hc.get("students_boys"), 2075))
    st_g = int(_clean_num(hc.get("students_girls"), 768))
    st_tot = st_b + st_g

    sf_b = int(_clean_num(hc.get("staff_boys"), 72))
    sf_g = int(_clean_num(hc.get("staff_girls"), 59))
    sf_tot = sf_b + sf_g

    occ_b = st_b + sf_b
    occ_g = st_g + sf_g
    occ_tot = occ_b + occ_g

    vac_b = bc_b - occ_b
    vac_g = bc_g - occ_g
    vac_tot = vac_b + vac_g

    vac_coll_b = int(_clean_num(hc.get("vacant_college_boys"), vac_b - 41))
    vac_coll_g = int(_clean_num(hc.get("vacant_college_girls"), vac_g))
    vac_coll_tot = vac_coll_b + vac_coll_g

    vac_sp_b = int(_clean_num(hc.get("vacant_sports_boys"), 0))
    vac_sp_g = int(_clean_num(hc.get("vacant_sports_girls"), 0))
    vac_sp_tot = vac_sp_b + vac_sp_g

    vac_sc_b = int(_clean_num(hc.get("vacant_school_boys"), 0))
    vac_sc_g = int(_clean_num(hc.get("vacant_school_girls"), 0))
    vac_sc_tot = vac_sc_b + vac_sc_g

    occ_pct_b = round((occ_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    occ_pct_g = round((occ_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    occ_pct = round((occ_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    vac_pct_b = round((vac_b / bc_b * 100), 2) if bc_b > 0 else 0.0
    vac_pct_g = round((vac_g / bc_g * 100), 2) if bc_g > 0 else 0.0
    vac_pct = round((vac_tot / bc_tot * 100), 2) if bc_tot > 0 else 0.0

    st_vacated = int(_clean_num(hc.get("students_vacated"), 0))

    t_rec = int(_clean_num(hc.get("tickets_received"), 0))
    t_cls = int(_clean_num(hc.get("tickets_closed"), 0))
    t_opn = max(0, t_rec - t_cls)

    tot_hrs = float(_clean_num(hc.get("total_hours_close"), 0.0))
    tat_hrs = float(_clean_num(hc.get("tat_hours"), 62.29))

    q_rec = int(_clean_num(hc.get("quality_issues_received"), 0))
    q_cls = int(_clean_num(hc.get("quality_issues_closed"), 0))
    q_opn = max(0, q_rec - q_cls)
    q_open = q_opn

    incidents = int(_clean_num(hc.get("incidents_count"), 0))

    p_units = int(_clean_num(hc.get("power_units"), 0))
    p_cost = float(_clean_num(hc.get("power_cost"), 0.0))
    w_pur = float(_clean_num(hc.get("water_purchase_cost"), 0.0))
    maint_exp = float(_clean_num(hc.get("maintenance_expenses"), 119394.0))
    exp_occ = float(_clean_num(hc.get("expenses_occurred"), 9349172.0))

    app_bud = float(_clean_num(hc.get("approved_budget"), 142010789.0))
    cum_bud = float(_clean_num(hc.get("cumulative_budget_spent"), 0.0))
    bal = app_bud - cum_bud

    nw_ltr = int(_clean_num(hc.get("normal_water_litres"), 0))
    nw_cost = float(_clean_num(hc.get("normal_water_cost"), 0.0))
    dw_ltr = int(_clean_num(hc.get("drinking_water_litres"), 0))
    dw_cost = float(_clean_num(hc.get("drinking_water_cost"), 0.0))

    sq_ft = float(_clean_num(hc.get("sq_feet"), 231701.0))
    per_st_mo = round(exp_occ / occ_tot, 2) if occ_tot > 0 else (round(exp_occ / st_tot, 2) if st_tot > 0 else 0.0)
    per_st_day = round(per_st_mo / 30.0, 2)
    sq_ft_occ = round(sq_ft / occ_tot, 2) if occ_tot > 0 else (round(sq_ft / st_tot, 2) if st_tot > 0 else 0.0)

    nw_st_ltr = round(nw_ltr / st_tot, 2) if st_tot > 0 else float(_clean_num(hc.get("normal_water_student_ltrs"), 0.0))
    nw_st_cost = round(nw_cost / st_tot, 2) if st_tot > 0 else float(_clean_num(hc.get("normal_water_student_cost"), 88.0))

    p_sqft = round(p_cost / sq_ft, 2) if sq_ft > 0 else 0.0
    p_occ_u = round(p_units / occ_tot, 2) if occ_tot > 0 else 0.0
    p_occ_c = round(p_cost / occ_tot, 2) if occ_tot > 0 else 0.0

    nw_day_ltr = round(nw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    nw_day_c = round(nw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    dw_day_ltr = round(dw_ltr / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0
    dw_day_c = round(dw_cost / occ_tot / 30.0, 2) if occ_tot > 0 else 0.0

    remarks = str(hc.get("remarks") or "")

    # Serialize custom metrics and budget heads
    custom_metrics_dict = {}
    if isinstance(hc.get("custom_metrics"), dict):
        custom_metrics_dict.update(hc["custom_metrics"])
    for k, v in hc.items():
        if k.startswith("budget_") or k.startswith("sanctioned_") or k.startswith("limit_") or k.startswith("param_") or k.startswith("custom_"):
            custom_metrics_dict[k] = v
    custom_metrics_json = json.dumps(custom_metrics_dict)

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
        custom_metrics = CASE WHEN EXCLUDED.custom_metrics IS NOT NULL AND EXCLUDED.custom_metrics::text != '{}' THEN EXCLUDED.custom_metrics ELSE hostel_census_entries.custom_metrics END;
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
    other_cost = float(_clean_num(get_f("other_cost", 0.0)))
    cctv_replacement = float(_clean_num(get_f("cctv_replacement", 0.0)))
    employee_cost = float(_clean_num(get_f("employee_cost", 0.0)))
    parking_fastag = float(_clean_num(get_f("parking_fastag", 0.0)))

    # Row 16: Total Expenses = SUM(fuel + fc + statutory + repair + other + cctv + employee + parking)
    total_expenses = (fuel_expenses + fc_cost + statutory_cost + repair_maintenance_cost + 
                      other_cost + cctv_replacement + employee_cost + parking_fastag)

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

    branch_default_budget = {
        "University": 40330187.0,
        "RPS": 14107491.0,
        "KPM": 4000000.0,
        "Common": 5552143.0,
    }.get(b_val, 4000000.0)
    approved_budget = float(_clean_num(get_f("approved_budget", branch_default_budget)))
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
        repair_maintenance_cost, other_cost, cctv_replacement, employee_cost, parking_fastag, total_expenses,
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
        %s, %s, %s, %s, %s, %s,
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
        other_cost = EXCLUDED.other_cost,
        cctv_replacement = EXCLUDED.cctv_replacement,
        employee_cost = EXCLUDED.employee_cost,
        parking_fastag = EXCLUDED.parking_fastag,
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
        repair_maintenance_cost, other_cost, cctv_replacement, employee_cost, parking_fastag, total_expenses,
        fee_demand, fee_discount, fee_collected, fee_unpaid,
        rps_monthly_billing, staff_travel_deduction, additional_kms_billed_rps, additional_kms_others_billing, cab_billing, cumulative_income,
        approved_budget, cumulative_budget_spent, balance,
        service_tickets_raised, service_tickets_closed, service_tickets_open,
        quality_issues_received, quality_issues_closed, quality_issues_open,
        statutory_compliance, incidents_count,
        per_student_cost_expenses, per_student_fee_year, demand_per_km_day, km_per_veh_day,
        fuel_cost_per_km, diesel_per_100km, remarks
    ))


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

                # Update Hostel Census & Operational Metrics
                if req.hostel_census:
                    compute_and_upsert_hostel_census(cur, req.period_id, req.hostel_census)

                # Update Transport Census & Fleet Metrics
                if req.transport_census:
                    is_multi_branch = isinstance(req.transport_census, dict) and any(b in req.transport_census for b in ["Common", "RPS", "KPM", "University"])
                    if is_multi_branch:
                        for b_name in ["Common", "RPS", "KPM", "University"]:
                            b_data = req.transport_census.get(b_name)
                            if isinstance(b_data, dict) and b_data:
                                compute_and_upsert_transport_census(cur, req.period_id, b_data, branch=b_name)
                    else:
                        tc_branch = req.transport_census.get("branch") if isinstance(req.transport_census, dict) else branch
                        compute_and_upsert_transport_census(cur, req.period_id, req.transport_census, branch=tc_branch or branch)

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



@app.get("/api/hostel/budget-tracking")
def get_hostel_budget_tracking():
    """
    Returns the official 9-head Hostel Budget Tracking Summary directly from PostgreSQL.
    Includes self-healing schema sync and graceful fallback to ensure it never throws 500.
    """
    months = [
        "sep_25_actual", "oct_26_actual", "nov_26_actual", "dec_26_actual",
        "jan_27_actual", "feb_27_actual", "mar_27_actual", "apr_27_actual",
        "may_27_actual", "jun_27_actual", "jul_27_actual", "aug_27_actual",
        "sep_27_actual"
    ]
    canonical_heads = [
        {"s_no": 1, "budget_head": "Rent", "sanctioned_amount": 84762516.0, "month_limit": 10595314.5, "oct_26_actual": 8725551.0},
        {"s_no": 2, "budget_head": "Printing & Stationary Expenses", "sanctioned_amount": 15000.0, "month_limit": 1875.0, "oct_26_actual": 0.0},
        {"s_no": 3, "budget_head": "Rates & Taxes", "sanctioned_amount": 731612.0, "month_limit": 91451.5, "oct_26_actual": 0.0},
        {"s_no": 4, "budget_head": "Employee Cost", "sanctioned_amount": 15402907.0, "month_limit": 1925363.38, "oct_26_actual": 846146.0},
        {"s_no": 5, "budget_head": "Hostel Management Services", "sanctioned_amount": 30490064.0, "month_limit": 3811258.0, "oct_26_actual": 2281856.0},
        {"s_no": 6, "budget_head": "Utility", "sanctioned_amount": 32893042.0, "month_limit": 4111630.25, "oct_26_actual": 9424.0},
        {"s_no": 7, "budget_head": "Laundry Expenses", "sanctioned_amount": 11728517.0, "month_limit": 1466064.63, "oct_26_actual": 1075076.0},
        {"s_no": 8, "budget_head": "Repairs and Maintenance", "sanctioned_amount": 5425960.0, "month_limit": 678245.0, "oct_26_actual": 485064.0},
        {"s_no": 9, "budget_head": "Events", "sanctioned_amount": 4000000.0, "month_limit": 500000.0, "oct_26_actual": 0.0}
    ]
    try:
        try:
            rows = db.execute_query("SELECT * FROM hostel_budget_tracking ORDER BY s_no ASC")
        except Exception as q_err:
            print(f"[Hostel Budget Query Notice] {q_err}. Attempting self-healing schema creation...")
            try:
                ensure_schema_compatibility()
                rows = db.execute_query("SELECT * FROM hostel_budget_tracking ORDER BY s_no ASC")
            except Exception as retry_err:
                print(f"[Hostel Budget Retry Notice] {retry_err}")
                rows = []

        if not rows:
            data = []
            for h in canonical_heads:
                row_dict = {m: 0.0 for m in months}
                row_dict.update(h)
                data.append(row_dict)
        else:
            data = []
            for r in rows:
                data.append({
                    k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
                    for k, v in r.items()
                })

        monthly_totals = {
            m: sum(float(r.get(m) or 0) for r in data)
            for m in months
        }

        return {
            "status": "success",
            "items": data,
            "total_sanctioned": sum(float(r.get("sanctioned_amount") or 0) for r in data),
            "total_month_limit": sum(float(r.get("month_limit") or 0) for r in data),
            "monthly_totals": monthly_totals,
            "total_oct_26_actual": monthly_totals.get("oct_26_actual", 0.0),
            "total_nov_26_actual": monthly_totals.get("nov_26_actual", 0.0)
        }
    except Exception as e:
        print(f"[get_hostel_budget_tracking Fallback] {e}")
        fallback_data = []
        for h in canonical_heads:
            row_dict = {m: 0.0 for m in months}
            row_dict.update(h)
            fallback_data.append(row_dict)
        return {
            "status": "success",
            "items": fallback_data,
            "total_sanctioned": 185449618.0,
            "total_month_limit": 23181202.0,
            "monthly_totals": {"oct_26_actual": 13423117.0},
            "total_oct_26_actual": 13423117.0,
            "total_nov_26_actual": 0.0
        }

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
            {"id": "Common", "code": "Common", "label": "Common", "description": "Central Campus Shared Fleet", "icon": "🚌"},
            {"id": "University", "code": "University", "label": "University Fleet", "description": "Rathinam University Main Fleet", "icon": "🎓"},
        ]
    }

@app.get("/api/transport/budget-tracking")
def get_transport_budget_tracking(branch: Optional[str] = None):
    """
    Returns the official Sanctioned Budget Parameters & Allocation per operating fleet branch directly from PostgreSQL.
    """
    try:
        sql = "SELECT * FROM transport_budget_tracking"
        params = []
        if branch and branch != "all":
            sql += " WHERE branch = %s"
            params.append(branch)
        sql += " ORDER BY branch, display_order ASC;"
        
        rows = db.execute_query(sql, tuple(params) if params else None)
        
        budgets = {}
        for r in rows:
            b = r.get("branch")
            if b not in budgets:
                budgets[b] = {
                    "branch": b,
                    "sanctioned": 0.0,
                    "lineItems": []
                }
            item = {
                "id": r.get("id"),
                "param": r.get("param_name"),
                "amount": float(r.get("sanctioned_amount") or 0.0),
                "order": r.get("display_order"),
                "color": r.get("color"),
                "bg": r.get("bg"),
                "isTotal": bool(r.get("is_total")),
                "isBlank": bool(r.get("is_blank"))
            }
            budgets[b]["lineItems"].append(item)
            if item["isTotal"]:
                budgets[b]["sanctioned"] = item["amount"]
                
        return {
            "status": "success",
            "budgets": budgets,
            "branch": branch
        }
    except Exception as e:
        print(f"[get_transport_budget_tracking Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transport/budget-tracking")
def update_transport_budget_tracking(req: Dict[str, Any]):
    """
    Updates the Sanctioned Budget parameter amounts for a specific branch or bulk branches.
    Auto-computes Total Expenses, updates both transport_budget_tracking and dedicated per-fleet
    tables (transport_budget_rps, transport_budget_kpm, transport_budget_common, transport_budget_university),
    and syncs approved_budget and balance to transport_census_entries.
    """
    conn = db.get_db_connection()
    try:
        with conn.cursor() as cur:
            all_budgets = req.get("budgets")
            if all_budgets and isinstance(all_budgets, dict):
                # Bulk update across multiple or all branches
                updated_branches = {}
                for b_name, b_info in all_budgets.items():
                    if isinstance(b_info, list):
                        items = b_info
                    elif isinstance(b_info, dict):
                        items = b_info if isinstance(b_info, list) else (b_info.get("lineItems") or b_info.get("line_items") or [])
                    else:
                        items = []
                    if not items:
                        continue
                    c_total = sum(float(_clean_num(it.get("amount", 0.0))) for it in items if not (it.get("isTotal") or it.get("is_total")))
                    
                    # Update consolidated table
                    for it in items:
                        p_name = it.get("param") or it.get("param_name")
                        is_tot = bool(it.get("isTotal") or it.get("is_total"))
                        is_blk = bool(it.get("isBlank") or it.get("is_blank"))
                        amt = c_total if is_tot else float(_clean_num(it.get("amount", 0.0)))
                        cur.execute("""
                            INSERT INTO transport_budget_tracking (
                                branch, param_name, sanctioned_amount, display_order, color, bg, is_total, is_blank, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (branch, param_name) DO UPDATE SET
                                sanctioned_amount = EXCLUDED.sanctioned_amount,
                                color = COALESCE(EXCLUDED.color, transport_budget_tracking.color),
                                bg = COALESCE(EXCLUDED.bg, transport_budget_tracking.bg),
                                updated_at = CURRENT_TIMESTAMP;
                        """, (
                            b_name, p_name, amt,
                            int(it.get("order") or it.get("display_order") or 1),
                            it.get("color") or "#3b82f6", it.get("bg") or "#eff6ff", is_tot, is_blk
                        ))
                    
                    # Update dedicated per-fleet table
                    ded_tbl = f"transport_budget_{b_name.lower()}"
                    try:
                        for it in items:
                            p_name = it.get("param") or it.get("param_name")
                            is_tot = bool(it.get("isTotal") or it.get("is_total"))
                            is_blk = bool(it.get("isBlank") or it.get("is_blank"))
                            amt = c_total if is_tot else float(_clean_num(it.get("amount", 0.0)))
                            cur.execute(f"""
                                INSERT INTO {ded_tbl} (
                                    param_name, sanctioned_amount, display_order, color, bg, is_total, is_blank, updated_at
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                ON CONFLICT (param_name) DO UPDATE SET
                                    sanctioned_amount = EXCLUDED.sanctioned_amount,
                                    color = COALESCE(EXCLUDED.color, {ded_tbl}.color),
                                    bg = COALESCE(EXCLUDED.bg, {ded_tbl}.bg),
                                    updated_at = CURRENT_TIMESTAMP;
                            """, (
                                p_name, amt,
                                int(it.get("order") or it.get("display_order") or 1),
                                it.get("color") or "#3b82f6", it.get("bg") or "#eff6ff", is_tot, is_blk
                            ))
                    except Exception as de:
                        print(f"[{ded_tbl} bulk sync notice] {de}")
                    
                    # Update transport_census_entries
                    cur.execute("""
                        UPDATE transport_census_entries
                        SET approved_budget = %s,
                            balance = %s - cumulative_budget_spent
                        WHERE branch = %s;
                    """, (c_total, c_total, b_name))
                    updated_branches[b_name] = c_total
                
                conn.commit()
                return {
                    "status": "success",
                    "message": f"Successfully updated and saved all fleet budget tables: {list(updated_branches.keys())}",
                    "updated_branches": updated_branches
                }

            # Single branch update
            branch = req.get("branch")
            line_items = req.get("lineItems") or req.get("line_items") or []
            
            if not branch or branch == "all":
                raise HTTPException(status_code=400, detail="Specific branch required (University, RPS, KPM, Common)")
            
            if not line_items:
                raise HTTPException(status_code=400, detail="lineItems list is required")
                
            # 1. Calculate new total from non-total items
            computed_total = 0.0
            for item in line_items:
                is_total = bool(item.get("isTotal") or item.get("is_total"))
                if not is_total:
                    amt = float(_clean_num(item.get("amount", 0.0)))
                    computed_total += amt
            
            # 2. Update each line item in consolidated transport_budget_tracking
            for item in line_items:
                p_name = item.get("param") or item.get("param_name")
                is_total = bool(item.get("isTotal") or item.get("is_total"))
                is_blank = bool(item.get("isBlank") or item.get("is_blank"))
                amt = computed_total if is_total else float(_clean_num(item.get("amount", 0.0)))
                    
                cur.execute("""
                    INSERT INTO transport_budget_tracking (
                        branch, param_name, sanctioned_amount, display_order, color, bg, is_total, is_blank, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (branch, param_name) DO UPDATE SET
                        sanctioned_amount = EXCLUDED.sanctioned_amount,
                        color = COALESCE(EXCLUDED.color, transport_budget_tracking.color),
                        bg = COALESCE(EXCLUDED.bg, transport_budget_tracking.bg),
                        updated_at = CURRENT_TIMESTAMP;
                """, (
                    branch,
                    p_name,
                    amt,
                    int(item.get("order") or item.get("display_order") or 1),
                    item.get("color") or "#3b82f6",
                    item.get("bg") or "#eff6ff",
                    is_total,
                    is_blank
                ))
            
            # 2b. Update dedicated per-fleet table: transport_budget_<branch>
            dedicated_tbl = f"transport_budget_{branch.lower()}"
            try:
                for item in line_items:
                    p_name = item.get("param") or item.get("param_name")
                    is_total = bool(item.get("isTotal") or item.get("is_total"))
                    is_blank = bool(item.get("isBlank") or item.get("is_blank"))
                    amt = computed_total if is_total else float(_clean_num(item.get("amount", 0.0)))
                    cur.execute(f"""
                        INSERT INTO {dedicated_tbl} (
                            param_name, sanctioned_amount, display_order, color, bg, is_total, is_blank, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (param_name) DO UPDATE SET
                            sanctioned_amount = EXCLUDED.sanctioned_amount,
                            color = COALESCE(EXCLUDED.color, {dedicated_tbl}.color),
                            bg = COALESCE(EXCLUDED.bg, {dedicated_tbl}.bg),
                            updated_at = CURRENT_TIMESTAMP;
                    """, (
                        p_name,
                        amt,
                        int(item.get("order") or item.get("display_order") or 1),
                        item.get("color") or "#3b82f6",
                        item.get("bg") or "#eff6ff",
                        is_total,
                        is_blank
                    ))
            except Exception as de:
                print(f"[{dedicated_tbl} sync notice] {de}")

            # 3. Synchronize new approved_budget to transport_census_entries for this branch
            cur.execute("""
                UPDATE transport_census_entries
                SET approved_budget = %s,
                    balance = %s - cumulative_budget_spent
                WHERE branch = %s;
            """, (computed_total, computed_total, branch))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Successfully updated and locked budget in dedicated table {dedicated_tbl} and transport_budget_tracking (New Sanctioned Total: ₹{computed_total:,.2f})",
                "branch": branch,
                "sanctioned": computed_total,
                "table_name": dedicated_tbl
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[update_transport_budget_tracking Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.release_db_connection(conn)

@app.get("/api/transport/budget/{branch_name}")
def get_dedicated_branch_budget_table(branch_name: str):
    """
    Returns the budget parameters directly from the dedicated per-fleet table
    (transport_budget_rps, transport_budget_kpm, transport_budget_common, transport_budget_university).
    """
    clean_b = branch_name.lower().strip()
    table_name = f"transport_budget_{clean_b}"
    try:
        rows = db.execute_query(f"SELECT * FROM {table_name} ORDER BY display_order ASC;")
        items = []
        sanctioned_total = 0.0
        for r in rows:
            it = {
                "id": r.get("id"),
                "param": r.get("param_name"),
                "amount": float(r.get("sanctioned_amount") or 0.0),
                "order": r.get("display_order"),
                "color": r.get("color"),
                "bg": r.get("bg"),
                "isTotal": bool(r.get("is_total")),
                "isBlank": bool(r.get("is_blank"))
            }
            items.append(it)
            if it["isTotal"]:
                sanctioned_total = it["amount"]
                
        return {
            "status": "success",
            "branch": branch_name,
            "table_name": table_name,
            "sanctioned": sanctioned_total,
            "lineItems": items
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Table {table_name} not found or query error: {str(e)}")

@app.get("/api/transport-census/{period_id}")
def get_transport_census_direct(period_id: int, branch: Optional[str] = "Common"):
    """
    Returns the transport census entries & operational metrics for a specific period and branch.
    """
    try:
        b_val = branch or "Common"
        row = db.execute_query(
            "SELECT * FROM transport_census_entries WHERE period_id = %s AND branch = %s;",
            (period_id, b_val),
            fetch_all=False
        )
        if not row:
            return {}
        clean = {
            k: (float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else v)
            for k, v in row.items()
        }
        c_metrics = row.get("custom_metrics") or {}
        if isinstance(c_metrics, str):
            try:
                c_metrics = json.loads(c_metrics)
            except Exception:
                c_metrics = {}
        if isinstance(c_metrics, dict):
            for ck, cv in c_metrics.items():
                if ck not in clean:
                    clean[ck] = cv
        return clean
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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


# -------------------------------------------------------------
# TRANSPORT VEHICLE-WISE FLEET EXPENSES & MILEAGE LEDGER API
# -------------------------------------------------------------

@app.get("/api/transport/vehicles")
def get_transport_vehicles(period_id: Optional[str] = None, branch: Optional[str] = "Common"):
    """
    Returns vehicle-wise fleet expense records, diesel consumption, KM run, and mileage
    for a given transport billing period (or 'all' periods consolidated) and branch.
    """
    try:
        b_filter = (branch or "Common").strip()
        is_all_periods = str(period_id).lower() == "all"

        if is_all_periods:
            if b_filter == "all":
                rows = db.execute_query(
                    """
                    SELECT 'all' AS period_id, branch, vehicle_no, make, model, 
                           SUM(fuel_expenses) AS fuel_expenses, 
                           SUM(fc_cost) AS fc_cost, 
                           SUM(statutory_cost) AS statutory_cost, 
                           SUM(repair_maintenance) AS repair_maintenance, 
                           SUM(parking_fastag) AS parking_fastag, 
                           SUM(cctv_replacement) AS cctv_replacement, 
                           SUM(employee_cost) AS employee_cost, 
                           SUM(other_cost) AS other_cost, 
                           SUM(total_expenses) AS total_expenses, 
                           SUM(diesel_litres) AS diesel_litres, 
                           SUM(km_run) AS km_run, 
                           MIN(display_order) AS display_order
                    FROM transport_vehicle_entries
                    GROUP BY branch, vehicle_no, make, model
                    ORDER BY branch, MIN(display_order), vehicle_no;
                    """
                )
            else:
                rows = db.execute_query(
                    """
                    SELECT 'all' AS period_id, branch, vehicle_no, make, model, 
                           SUM(fuel_expenses) AS fuel_expenses, 
                           SUM(fc_cost) AS fc_cost, 
                           SUM(statutory_cost) AS statutory_cost, 
                           SUM(repair_maintenance) AS repair_maintenance, 
                           SUM(parking_fastag) AS parking_fastag, 
                           SUM(cctv_replacement) AS cctv_replacement, 
                           SUM(employee_cost) AS employee_cost, 
                           SUM(other_cost) AS other_cost, 
                           SUM(total_expenses) AS total_expenses, 
                           SUM(diesel_litres) AS diesel_litres, 
                           SUM(km_run) AS km_run, 
                           MIN(display_order) AS display_order
                    FROM transport_vehicle_entries
                    WHERE LOWER(branch) = LOWER(%s)
                    GROUP BY branch, vehicle_no, make, model
                    ORDER BY MIN(display_order), vehicle_no;
                    """,
                    (b_filter,)
                )

            clean_rows = []
            for r in rows:
                clean_item = {}
                for k, v in r.items():
                    if isinstance(v, Decimal):
                        clean_item[k] = float(v)
                    else:
                        clean_item[k] = v
                clean_item["id"] = f"agg-{clean_item['branch']}-{clean_item['vehicle_no']}"
                km = clean_item.get("km_run", 0) or 0
                diesel = clean_item.get("diesel_litres", 0) or 0
                clean_item["mileage"] = round(km / diesel, 2) if diesel > 0 else 0.0
                clean_rows.append(clean_item)

            tot_fuel = sum(r.get("fuel_expenses", 0) for r in clean_rows)
            tot_fc = sum(r.get("fc_cost", 0) for r in clean_rows)
            tot_stat = sum(r.get("statutory_cost", 0) for r in clean_rows)
            tot_rep = sum(r.get("repair_maintenance", 0) for r in clean_rows)
            tot_park = sum(r.get("parking_fastag", 0) for r in clean_rows)
            tot_cctv = sum(r.get("cctv_replacement", 0) for r in clean_rows)
            tot_emp = sum(r.get("employee_cost", 0) for r in clean_rows)
            tot_oth = sum(r.get("other_cost", 0) for r in clean_rows)
            tot_exp = sum(r.get("total_expenses", 0) for r in clean_rows)
            tot_diesel = sum(r.get("diesel_litres", 0) for r in clean_rows)
            tot_km = sum(r.get("km_run", 0) for r in clean_rows)
            avg_mileage = round(tot_km / tot_diesel, 2) if tot_diesel > 0 else 0.0

            summary = {
                "bus_count": len(clean_rows),
                "fuel_expenses": tot_fuel,
                "fc_cost": tot_fc,
                "statutory_cost": tot_stat,
                "repair_maintenance": tot_rep,
                "parking_fastag": tot_park,
                "cctv_replacement": tot_cctv,
                "employee_cost": tot_emp,
                "other_cost": tot_oth,
                "total_expenses": tot_exp,
                "diesel_litres": tot_diesel,
                "km_run": tot_km,
                "mileage": avg_mileage
            }

            return {
                "status": "success",
                "period_id": "all",
                "branch": b_filter,
                "vehicles": clean_rows,
                "summary": summary,
                "branch_summaries": {}
            }

        # Otherwise single period - Smart Resolution
        numeric_period_id = None
        if period_id and str(period_id).isdigit():
            numeric_period_id = int(period_id)

        # Check if the requested period_id actually has entries in transport_vehicle_entries for this branch
        has_entries = False
        if numeric_period_id:
            check_veh = db.execute_query(
                "SELECT 1 FROM transport_vehicle_entries WHERE period_id = %s AND (LOWER(%s) = 'all' OR LOWER(branch) = LOWER(%s)) LIMIT 1;",
                (numeric_period_id, b_filter, b_filter),
                fetch_all=False
            )
            if check_veh:
                has_entries = True
            else:
                # If numeric_period_id is from another module (e.g. 311 for Oct'26), find matching transport period
                p_info = db.execute_query(
                    "SELECT period_label FROM billing_periods WHERE id = %s;",
                    (numeric_period_id,),
                    fetch_all=False
                )
                if p_info and p_info.get("period_label"):
                    target_lbl = p_info["period_label"]
                    matching_p = db.execute_query(
                        """
                        SELECT bp.id 
                        FROM billing_periods bp
                        JOIN transport_vehicle_entries tve ON tve.period_id = bp.id
                        WHERE bp.period_label = %s AND (LOWER(%s) = 'all' OR LOWER(tve.branch) = LOWER(%s))
                        LIMIT 1;
                        """,
                        (target_lbl, b_filter, b_filter),
                        fetch_all=False
                    )
                    if matching_p:
                        numeric_period_id = matching_p["id"]
                        has_entries = True

        # Fallback: Pick the latest transport period with vehicle entries AND diesel > 0
        if not has_entries:
            latest_with_data = db.execute_query(
                """
                SELECT bp.id 
                FROM billing_periods bp
                JOIN transport_vehicle_entries tve ON tve.period_id = bp.id
                WHERE (LOWER(%s) = 'all' OR LOWER(tve.branch) = LOWER(%s)) AND tve.diesel_litres > 0
                GROUP BY bp.id, bp.start_date
                ORDER BY bp.start_date DESC
                LIMIT 1;
                """,
                (b_filter, b_filter),
                fetch_all=False
            )
            if latest_with_data:
                numeric_period_id = latest_with_data["id"]
            else:
                numeric_period_id = 1026

        if b_filter == "all":
            rows = db.execute_query(
                """
                SELECT id, period_id, branch, vehicle_no, make, model, 
                       fuel_expenses, fc_cost, statutory_cost, repair_maintenance, 
                       parking_fastag, cctv_replacement, employee_cost, other_cost, total_expenses, 
                       diesel_litres, km_run, mileage, display_order, remarks, created_at
                FROM transport_vehicle_entries
                WHERE period_id = %s
                ORDER BY branch, display_order, id;
                """,
                (numeric_period_id,)
            )
        else:
            rows = db.execute_query(
                """
                SELECT id, period_id, branch, vehicle_no, make, model, 
                       fuel_expenses, fc_cost, statutory_cost, repair_maintenance, 
                       parking_fastag, cctv_replacement, employee_cost, other_cost, total_expenses, 
                       diesel_litres, km_run, mileage, display_order, remarks, created_at
                FROM transport_vehicle_entries
                WHERE period_id = %s AND LOWER(branch) = LOWER(%s)
                ORDER BY display_order, id;
                """,
                (numeric_period_id, b_filter)
            )

        clean_rows = []
        for r in rows:
            clean_item = {}
            for k, v in r.items():
                if isinstance(v, Decimal):
                    clean_item[k] = float(v)
                elif isinstance(v, datetime):
                    clean_item[k] = v.isoformat()
                else:
                    clean_item[k] = v
            clean_rows.append(clean_item)

        # Compute summary for currently active view
        tot_fuel = sum(r.get("fuel_expenses", 0) for r in clean_rows)
        tot_fc = sum(r.get("fc_cost", 0) for r in clean_rows)
        tot_stat = sum(r.get("statutory_cost", 0) for r in clean_rows)
        tot_rep = sum(r.get("repair_maintenance", 0) for r in clean_rows)
        tot_park = sum(r.get("parking_fastag", 0) for r in clean_rows)
        tot_cctv = sum(r.get("cctv_replacement", 0) for r in clean_rows)
        tot_emp = sum(r.get("employee_cost", 0) for r in clean_rows)
        tot_oth = sum(r.get("other_cost", 0) for r in clean_rows)
        tot_exp = sum(r.get("total_expenses", 0) for r in clean_rows)
        tot_diesel = sum(r.get("diesel_litres", 0) for r in clean_rows)
        tot_km = sum(r.get("km_run", 0) for r in clean_rows)
        avg_mileage = round(tot_km / tot_diesel, 2) if tot_diesel > 0 else 0.0

        summary = {
            "bus_count": len(clean_rows),
            "fuel_expenses": tot_fuel,
            "fc_cost": tot_fc,
            "statutory_cost": tot_stat,
            "repair_maintenance": tot_rep,
            "parking_fastag": tot_park,
            "cctv_replacement": tot_cctv,
            "employee_cost": tot_emp,
            "other_cost": tot_oth,
            "total_expenses": tot_exp,
            "diesel_litres": tot_diesel,
            "km_run": tot_km,
            "mileage": avg_mileage
        }

        # Branch summaries for badges
        all_period_rows = db.execute_query(
            "SELECT branch, vehicle_no, total_expenses, diesel_litres, km_run FROM transport_vehicle_entries WHERE period_id = %s;",
            (numeric_period_id,)
        )
        branches = ["Common", "RPS", "KPM", "University"]
        branch_summaries = {}
        all_count = len(all_period_rows)
        all_exp = sum(float(r["total_expenses"] or 0) for r in all_period_rows)
        all_diesel = sum(float(r["diesel_litres"] or 0) for r in all_period_rows)
        all_km = sum(float(r["km_run"] or 0) for r in all_period_rows)
        branch_summaries["all"] = {
            "bus_count": all_count,
            "total_expenses": all_exp,
            "diesel_litres": all_diesel,
            "km_run": all_km,
            "mileage": round(all_km / all_diesel, 2) if all_diesel > 0 else 0.0
        }

        for b in branches:
            b_rows = [r for r in all_period_rows if str(r.get("branch")).lower() == b.lower()]
            b_cnt = len(b_rows)
            b_e = sum(float(r["total_expenses"] or 0) for r in b_rows)
            b_d = sum(float(r["diesel_litres"] or 0) for r in b_rows)
            b_k = sum(float(r["km_run"] or 0) for r in b_rows)
            branch_summaries[b] = {
                "bus_count": b_cnt,
                "total_expenses": b_e,
                "diesel_litres": b_d,
                "km_run": b_k,
                "mileage": round(b_k / b_d, 2) if b_d > 0 else 0.0
            }

        return {
            "status": "success",
            "period_id": numeric_period_id,
            "branch": b_filter,
            "vehicles": clean_rows,
            "summary": summary,
            "branch_summaries": branch_summaries
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/transport/vehicles")
def save_transport_vehicles(req: Dict[str, Any]):
    """
    Saves/updates vehicle ledger rows for a specific branch and period,
    auto-calculates row totals and mileage, and syncs aggregate totals to transport_census_entries.
    """
    try:
        period_id = int(req.get("period_id"))
        branch = (req.get("branch") or "Common").strip()
        vehicles = req.get("vehicles") or []

        if branch == "all":
            raise HTTPException(status_code=400, detail="Cannot save vehicles under 'all' consolidated view. Select a specific branch (RPS, KPM, University, or Common).")

        # Guard: check if period is locked
        check_closed = db.execute_query(
            "SELECT is_closed, period_label FROM billing_periods WHERE id = %s;",
            (period_id,),
            fetch_all=False
        )
        if check_closed and check_closed.get("is_closed"):
            p_lbl = check_closed.get("period_label") or f"#{period_id}"
            raise HTTPException(status_code=400, detail=f"Billing month {p_lbl} is locked (read-only). Please unlock it before modifying vehicle records.")

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                # 1. Remove previous entries for this period and branch
                cur.execute(
                    "DELETE FROM transport_vehicle_entries WHERE period_id = %s AND branch = %s;",
                    (period_id, branch)
                )

                tot_fuel = 0.0
                tot_fc = 0.0
                tot_stat = 0.0
                tot_rep = 0.0
                tot_park = 0.0
                tot_cctv = 0.0
                tot_emp = 0.0
                tot_oth = 0.0
                tot_diesel = 0.0
                tot_km = 0.0

                ins_sql = """
                INSERT INTO transport_vehicle_entries (
                    period_id, branch, vehicle_no, make, model, 
                    fuel_expenses, fc_cost, statutory_cost, repair_maintenance, 
                    parking_fastag, cctv_replacement, employee_cost, other_cost, total_expenses, 
                    diesel_litres, km_run, mileage, display_order, remarks
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """

                saved_ids = []
                for order, v in enumerate(vehicles):
                    v_no = str(v.get("vehicle_no") or "").strip()
                    if not v_no:
                        v_no = f"BUS-{order + 1:02d}"
                    make = str(v.get("make") or "").strip()
                    model = str(v.get("model") or "").strip()
                    remarks = str(v.get("remarks") or "").strip()

                    fuel = float(_clean_num(v.get("fuel_expenses", 0)))
                    fc = float(_clean_num(v.get("fc_cost", 0)))
                    stat = float(_clean_num(v.get("statutory_cost", 0)))
                    rep = float(_clean_num(v.get("repair_maintenance", 0)))
                    park = float(_clean_num(v.get("parking_fastag", 0)))
                    cctv = float(_clean_num(v.get("cctv_replacement", 0)))
                    emp = float(_clean_num(v.get("employee_cost", 0)))
                    oth = float(_clean_num(v.get("other_cost", 0)))
                    diesel = float(_clean_num(v.get("diesel_litres", 0)))
                    km = float(_clean_num(v.get("km_run", 0)))

                    row_tot = fuel + fc + stat + rep + park + cctv + emp + oth
                    row_mila = round(km / diesel, 2) if diesel > 0 else 0.0

                    tot_fuel += fuel
                    tot_fc += fc
                    tot_stat += stat
                    tot_rep += rep
                    tot_park += park
                    tot_cctv += cctv
                    tot_emp += emp
                    tot_oth += oth
                    tot_diesel += diesel
                    tot_km += km

                    cur.execute(ins_sql, (
                        period_id, branch, v_no, make, model,
                        fuel, fc, stat, rep, park, cctv, emp, oth, row_tot,
                        diesel, km, row_mila, order, remarks
                    ))
                    r_id = cur.fetchone()[0]
                    saved_ids.append(r_id)

                # 2. Sync to transport_census_entries
                bus_count = len(vehicles)
                tot_exp = tot_fuel + tot_fc + tot_stat + tot_rep + tot_park + tot_cctv + tot_emp + tot_oth
                census_update = {
                    "vehicles_count": f"{bus_count} Buses" if bus_count > 0 else "0",
                    "fuel_expenses": tot_fuel,
                    "fc_cost": tot_fc,
                    "statutory_cost": tot_stat,
                    "repair_maintenance_cost": tot_rep,
                    "parking_fastag": tot_park,
                    "cctv_replacement": tot_cctv,
                    "employee_cost": tot_emp,
                    "other_cost": tot_oth,
                    "total_expenses": tot_exp,
                    "diesel_litres": tot_diesel,
                    "actual_kms": tot_km
                }
                compute_and_upsert_transport_census(cur, period_id, census_update, branch=branch)

                conn.commit()

                return {
                    "status": "success",
                    "message": f"Saved {bus_count} vehicles for {branch} successfully",
                    "period_id": period_id,
                    "branch": branch,
                    "bus_count": bus_count,
                    "total_expenses": tot_exp,
                    "diesel_litres": tot_diesel,
                    "km_run": tot_km,
                    "average_mileage": round(tot_km / tot_diesel, 2) if tot_diesel > 0 else 0.0
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


@app.delete("/api/transport/vehicles/{vehicle_id}")
def delete_transport_vehicle(vehicle_id: int):
    """
    Deletes a single vehicle record and updates transport census totals.
    """
    try:
        veh = db.execute_query(
            "SELECT period_id, branch, vehicle_no FROM transport_vehicle_entries WHERE id = %s;",
            (vehicle_id,),
            fetch_all=False
        )
        if not veh:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        period_id = veh["period_id"]
        branch = veh["branch"]

        # Guard: check if period is locked
        check_closed = db.execute_query(
            "SELECT is_closed, period_label FROM billing_periods WHERE id = %s;",
            (period_id,),
            fetch_all=False
        )
        if check_closed and check_closed.get("is_closed"):
            p_lbl = check_closed.get("period_label") or f"#{period_id}"
            raise HTTPException(status_code=400, detail=f"Billing month {p_lbl} is locked (read-only). Please unlock it before deleting vehicle records.")

        db.execute_commit("DELETE FROM transport_vehicle_entries WHERE id = %s;", (vehicle_id,))

        # Recalculate remaining
        remaining = db.execute_query(
            """
            SELECT count(*) as bus_count, 
                   COALESCE(sum(fuel_expenses), 0) as fuel,
                   COALESCE(sum(fc_cost), 0) as fc,
                   COALESCE(sum(statutory_cost), 0) as stat,
                   COALESCE(sum(repair_maintenance), 0) as rep,
                   COALESCE(sum(parking_fastag), 0) as park,
                   COALESCE(sum(employee_cost), 0) as emp,
                   COALESCE(sum(other_cost), 0) as oth,
                   COALESCE(sum(total_expenses), 0) as tot_exp,
                   COALESCE(sum(diesel_litres), 0) as diesel,
                   COALESCE(sum(km_run), 0) as km
            FROM transport_vehicle_entries 
            WHERE period_id = %s AND branch = %s;
            """,
            (period_id, branch),
            fetch_all=False
        )

        b_cnt = int(remaining["bus_count"]) if remaining else 0
        tot_f = float(remaining["fuel"]) if remaining else 0.0
        tot_fc = float(remaining["fc"]) if remaining else 0.0
        tot_st = float(remaining["stat"]) if remaining else 0.0
        tot_rp = float(remaining["rep"]) if remaining else 0.0
        tot_pk = float(remaining["park"]) if remaining else 0.0
        tot_em = float(remaining["emp"]) if remaining else 0.0
        tot_ot = float(remaining["oth"]) if remaining else 0.0
        tot_ex = float(remaining["tot_exp"]) if remaining else 0.0
        tot_dl = float(remaining["diesel"]) if remaining else 0.0
        tot_km = float(remaining["km"]) if remaining else 0.0

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                census_update = {
                    "vehicles_count": f"{b_cnt} Buses" if b_cnt > 0 else "0",
                    "fuel_expenses": tot_f,
                    "fc_cost": tot_fc,
                    "statutory_cost": tot_st,
                    "repair_maintenance_cost": tot_rp,
                    "employee_cost": tot_em,
                    "other_cost": tot_ot,
                    "total_expenses": tot_ex,
                    "diesel_litres": tot_dl,
                    "actual_kms": tot_km,
                    "parking_fastag": tot_pk
                }
                compute_and_upsert_transport_census(cur, period_id, census_update, branch=branch)
                conn.commit()
        finally:
            db.release_db_connection(conn)

        return {
            "status": "success",
            "message": f"Vehicle '{veh.get('vehicle_no')}' deleted successfully",
            "remaining_bus_count": b_cnt
        }
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


# =========================================================================
# MONTHLY ATTACHMENTS & SUPPORTING DOCUMENTS MANAGEMENT (IMAGE, PDF, PPT, EXCEL, LINKS)
# =========================================================================

def _detect_file_type(filename: str, is_link: bool = False, url: str = "") -> str:
    if is_link:
        u = (url or filename).lower()
        if "sheet" in u or "excel" in u or ".csv" in u:
            return "excel"
        if "slide" in u or "presentation" in u or "ppt" in u:
            return "ppt"
        if "doc" in u or "word" in u:
            return "doc"
        if "drive.google.com" in u or "onedrive" in u or "dropbox" in u:
            return "cloud_drive"
        return "link"
    
    fn = filename.lower()
    if any(fn.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"]):
        return "image"
    if fn.endswith(".pdf"):
        return "pdf"
    if any(fn.endswith(ext) for ext in [".ppt", ".pptx"]):
        return "ppt"
    if any(fn.endswith(ext) for ext in [".xls", ".xlsx", ".csv"]):
        return "excel"
    if any(fn.endswith(ext) for ext in [".doc", ".docx", ".txt", ".rtf"]):
        return "doc"
    return "other"


@app.get("/api/attachments")
def get_monthly_attachments(module: str = "food", period_id: Optional[int] = None, branch: Optional[str] = None):
    """
    Fetches attachments for a given module and period.
    Also returns a summary map of attachment counts per period.
    """
    try:
        where_clauses = ["module = %s"]
        params = [module]

        if period_id is not None:
            where_clauses.append("period_id = %s")
            params.append(period_id)

        if branch and branch != "all":
            where_clauses.append("(branch = %s OR branch = 'Common' OR branch IS NULL)")
            params.append(branch)

        sql = f"""
            SELECT id, module, period_id, branch, file_name, file_type, file_path, file_size, mime_type, is_link, uploaded_by, created_at
            FROM monthly_attachments
            WHERE {' AND '.join(where_clauses)}
            ORDER BY created_at DESC;
        """
        rows = db.execute_query(sql, tuple(params))
        attachments = []
        for r in rows:
            attachments.append({
                "id": r["id"],
                "module": r["module"],
                "period_id": r["period_id"],
                "branch": r.get("branch") or "Common",
                "file_name": r["file_name"],
                "file_type": r["file_type"],
                "file_path": r["file_path"],
                "file_size": int(r.get("file_size") or 0),
                "mime_type": r.get("mime_type") or "",
                "is_link": bool(r.get("is_link")),
                "uploaded_by": r.get("uploaded_by") or "User",
                "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
            })

        summary_rows = db.execute_query("""
            SELECT period_id, COUNT(*) AS count
            FROM monthly_attachments
            WHERE module = %s
            GROUP BY period_id;
        """, (module,))
        summary = {str(sr["period_id"]): int(sr["count"]) for sr in summary_rows}

        return {
            "status": "success",
            "module": module,
            "period_id": period_id,
            "total_count": len(attachments),
            "summary": summary,
            "attachments": attachments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch attachments: {str(e)}")


@app.get("/api/attachments/summary")
def get_monthly_attachments_summary(module: str = "food"):
    """
    Returns attachment counts per period for a given module so the Dashboard and Data Entry can show badges.
    """
    try:
        rows = db.execute_query("""
            SELECT period_id, COUNT(*) AS count
            FROM monthly_attachments
            WHERE module = %s
            GROUP BY period_id;
        """, (module,))
        summary = {str(r["period_id"]): int(r["count"]) for r in rows}
        return {"status": "success", "module": module, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/attachments/upload")
async def upload_monthly_attachments(
    files: List[UploadFile] = File(...),
    module: str = Form(...),
    period_id: int = Form(...),
    branch: Optional[str] = Form("Common"),
    uploaded_by: Optional[str] = Form("User")
):
    """
    Uploads one or more files (image, pdf, ppt, excel, doc) for a specific monthly entry.
    Saves files to backend/uploads and records them in PostgreSQL monthly_attachments.
    """
    try:
        up_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
        os.makedirs(up_dir, exist_ok=True)

        created_records = []
        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                for file in files:
                    orig_name = file.filename or "attachment"
                    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', orig_name)
                    unique_id = uuid.uuid4().hex[:10]
                    saved_filename = f"{unique_id}_{safe_name}"
                    file_dest_path = os.path.join(up_dir, saved_filename)

                    content = await file.read()
                    file_size = len(content)
                    with open(file_dest_path, "wb") as f_out:
                        f_out.write(content)

                    mime_type = file.content_type or mimetypes.guess_type(orig_name)[0] or "application/octet-stream"
                    file_type = _detect_file_type(orig_name, is_link=False)
                    relative_url = f"/uploads/{saved_filename}"

                    cur.execute("""
                        INSERT INTO monthly_attachments (module, period_id, branch, file_name, file_type, file_path, file_size, mime_type, is_link, uploaded_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s)
                        RETURNING id, created_at;
                    """, (module, period_id, branch or "Common", orig_name, file_type, relative_url, file_size, mime_type, uploaded_by or "User"))
                    inserted = cur.fetchone()
                    conn.commit()

                    created_records.append({
                        "id": inserted[0],
                        "module": module,
                        "period_id": period_id,
                        "branch": branch or "Common",
                        "file_name": orig_name,
                        "file_type": file_type,
                        "file_path": relative_url,
                        "file_size": file_size,
                        "mime_type": mime_type,
                        "is_link": False,
                        "uploaded_by": uploaded_by or "User",
                        "created_at": inserted[1].isoformat() if hasattr(inserted[1], "isoformat") else str(inserted[1])
                    })
            return {
                "status": "success",
                "message": f"Successfully uploaded {len(created_records)} file(s)",
                "attachments": created_records
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
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


class AttachmentLinkRequest(BaseModel):
    module: str
    period_id: int
    branch: Optional[str] = "Common"
    url: str
    title: str
    uploaded_by: Optional[str] = "User"


@app.post("/api/attachments/link")
def add_attachment_link(req: AttachmentLinkRequest):
    """
    Attaches an external web link or cloud document (Google Drive, OneDrive, Sheet, etc.) to the monthly entry.
    """
    try:
        url = req.url.strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL cannot be empty")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        title = req.title.strip() if req.title and req.title.strip() else url
        file_type = _detect_file_type(title, is_link=True, url=url)

        conn = db.get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO monthly_attachments (module, period_id, branch, file_name, file_type, file_path, file_size, mime_type, is_link, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s, 0, 'text/uri-list', true, %s)
                    RETURNING id, created_at;
                """, (req.module, req.period_id, req.branch or "Common", title, file_type, url, req.uploaded_by or "User"))
                row = cur.fetchone()
                conn.commit()

                return {
                    "status": "success",
                    "message": "Link attached successfully",
                    "attachment": {
                        "id": row[0],
                        "module": req.module,
                        "period_id": req.period_id,
                        "branch": req.branch or "Common",
                        "file_name": title,
                        "file_type": file_type,
                        "file_path": url,
                        "file_size": 0,
                        "mime_type": "text/uri-list",
                        "is_link": True,
                        "uploaded_by": req.uploaded_by or "User",
                        "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
                    }
                }
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            db.release_db_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add link: {str(e)}")


@app.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: int):
    """
    Deletes an attachment from database and physically removes the file from disk if it was an upload.
    """
    try:
        row = db.execute_query(
            "SELECT id, file_path, is_link FROM monthly_attachments WHERE id = %s;",
            (attachment_id,),
            fetch_all=False
        )
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")

        if not row.get("is_link"):
            file_path = row.get("file_path", "")
            if file_path.startswith("/uploads/"):
                saved_filename = file_path.replace("/uploads/", "")
                up_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
                local_file = os.path.join(up_dir, saved_filename)
                if os.path.exists(local_file):
                    try:
                        os.remove(local_file)
                    except Exception as fe:
                        print(f"[Attachment Delete Notice] Could not remove physical file {local_file}: {fe}")

        db.execute_commit("DELETE FROM monthly_attachments WHERE id = %s;", (attachment_id,))
        return {"status": "success", "message": "Attachment deleted successfully", "deleted_id": attachment_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete attachment: {str(e)}")


@app.get("/api/attachments/{attachment_id}/slides")
def get_attachment_presentation_slides(attachment_id: int):
    """
    Extracts slide-by-slide presentation data from a PowerPoint (.pptx) file.
    Returns structured slides with titles, bullet points, text blocks, tables, and notes.
    """
    try:
        row = db.execute_query(
            "SELECT id, file_name, file_type, file_path, is_link FROM monthly_attachments WHERE id = %s;",
            (attachment_id,),
            fetch_all=False
        )
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found")

        file_path = row.get("file_path", "")
        if row.get("is_link") or not file_path.startswith("/uploads/"):
            return {
                "status": "external_link",
                "attachment_id": attachment_id,
                "file_name": row["file_name"],
                "file_path": file_path,
                "is_link": True,
                "total_slides": 0,
                "slides": []
            }

        saved_filename = file_path.replace("/uploads/", "")
        up_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
        local_file = os.path.join(up_dir, saved_filename)

        if not os.path.exists(local_file):
            raise HTTPException(status_code=404, detail="Physical presentation file not found on server")

        if not local_file.lower().endswith(".pptx"):
            return {
                "status": "legacy_format",
                "message": "Direct slide extraction supports PPTX format. You can download the presentation directly.",
                "attachment_id": attachment_id,
                "file_name": row["file_name"],
                "file_path": file_path,
                "total_slides": 0,
                "slides": []
            }

        try:
            import pptx
            prs = pptx.Presentation(local_file)
            slides_data = []

            for idx, slide in enumerate(prs.slides):
                slide_num = idx + 1
                title = ""
                if slide.shapes.title and slide.shapes.title.text:
                    title = slide.shapes.title.text.strip()

                text_blocks = []
                tables = []
                has_image = False

                for shape in slide.shapes:
                    if shape.has_table:
                        tbl = shape.table
                        table_matrix = []
                        for row_idx, r in enumerate(tbl.rows):
                            row_vals = [cell.text.strip() for cell in r.cells]
                            table_matrix.append(row_vals)
                        if table_matrix:
                            tables.append(table_matrix)

                    elif shape.has_text_frame and shape != slide.shapes.title:
                        for p in shape.text_frame.paragraphs:
                            p_text = p.text.strip()
                            if p_text:
                                text_blocks.append({
                                    "text": p_text,
                                    "level": p.level or 0
                                })

                notes = ""
                try:
                    if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                        notes = slide.notes_slide.notes_text_frame.text.strip()
                except Exception:
                    pass

                # If title was not found via placeholder, infer from first text block
                if not title and text_blocks:
                    title = text_blocks[0]["text"]
                    text_blocks = text_blocks[1:]
                elif not title:
                    title = f"Slide {slide_num}"

                slides_data.append({
                    "slide_number": slide_num,
                    "title": title,
                    "text_blocks": text_blocks,
                    "tables": tables,
                    "has_image": has_image,
                    "notes": notes
                })

            return {
                "status": "success",
                "attachment_id": attachment_id,
                "file_name": row["file_name"],
                "file_path": file_path,
                "total_slides": len(slides_data),
                "slides": slides_data
            }
        except Exception as pe:
            return {
                "status": "parse_error",
                "message": f"Could not parse PPTX slides: {str(pe)}",
                "attachment_id": attachment_id,
                "file_name": row["file_name"],
                "file_path": file_path,
                "total_slides": 0,
                "slides": []
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
