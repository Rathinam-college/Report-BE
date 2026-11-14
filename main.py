from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import re
import bcrypt
import database as db
import system_manager

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

@app.on_event("startup")
def startup_event():
    try:
        db.auto_migrate()
    except Exception as e:
        print(f"Startup schema migration warning: {e}")

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
    category_id: int
    name: str
    code: Optional[str] = None
    cost_behavior: Optional[str] = "variable"
    default_vendor_id: Optional[int] = None
    display_order: Optional[int] = None
    is_active: bool = True

class ReorderCostHeadsRequest(BaseModel):
    cost_head_ids: List[int]

class CategoryCreate(BaseModel):
    name: str
    code: Optional[str] = None
    display_order: Optional[int] = None
    module: Optional[str] = "food"

class CategoryUpdate(BaseModel):
    name: str
    code: Optional[str] = None
    display_order: Optional[int] = None
    is_active: bool = True
    module: Optional[str] = "food"

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
def get_periods():
    try:
        return db.execute_query("SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed FROM billing_periods ORDER BY start_date")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/master/periods")
def get_master_periods():
    return get_periods()

@app.post("/api/periods")
def create_period(req: PeriodCreate):
    try:
        import re
        import calendar

        label = req.period_label.strip()
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
                existing = db.execute_query("SELECT COUNT(*) as cnt FROM billing_periods", fetch_all=False)
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
        INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days, is_closed)
        VALUES (1, %s, %s, %s, %s, %s, false)
        RETURNING id, period_code, period_label;
        """
        new_period = db.execute_query(
            insert_sql,
            (derived_code, label, start_date, end_date, operating_days),
            fetch_all=False
        )

        if req.clone_from_period_id:
            clone_sql = """
            INSERT INTO monthly_expense_entries (period_id, cost_head_id, vendor_id, amount, remarks, status)
            SELECT %s, cost_head_id, vendor_id, amount, 'Cloned from baseline', 'draft'
            FROM monthly_expense_entries
            WHERE period_id = %s;
            """
            db.execute_commit(clone_sql, (new_period["id"], req.clone_from_period_id))

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
@app.get("/api/overview")
def get_overview():
    try:
        exec_rows = db.execute_query("SELECT * FROM vw_food_executive_summary ORDER BY start_date")
        
        grand_total = sum(float(r["grand_total_expenses"]) for r in exec_rows)
        avg_monthly = grand_total / len(exec_rows) if exec_rows else 0
        total_material = sum(float(r["total_material_fuel"]) for r in exec_rows)
        total_labour = sum(float(r["total_labour"]) for r in exec_rows)
        total_maint = sum(float(r["total_maintenance_utilities"]) for r in exec_rows)
        total_events = sum(float(r["total_event_purchase"]) + float(r["total_food_festival"]) for r in exec_rows)

        trend = []
        for r in exec_rows:
            trend.append({
                "period_code": r["period_code"],
                "period_label": r["period_label"],
                "total": float(r["grand_total_expenses"]),
                "material_fuel": float(r["total_material_fuel"]),
                "labour": float(r["total_labour"]),
                "maintenance": float(r["total_maintenance_utilities"]),
                "events_festivals": float(r["total_event_purchase"]) + float(r["total_food_festival"])
            })

        return {
            "summary": {
                "grand_total": round(grand_total, 2),
                "monthly_avg": round(avg_monthly, 2),
                "total_material_fuel": round(total_material, 2),
                "material_share_pct": round((total_material / grand_total * 100), 2) if grand_total else 0,
                "total_labour": round(total_labour, 2),
                "labour_share_pct": round((total_labour / grand_total * 100), 2) if grand_total else 0,
                "total_maintenance": round(total_maint, 2),
                "maintenance_share_pct": round((total_maint / grand_total * 100), 2) if grand_total else 0,
                "total_events_festivals": round(total_events, 2),
                "events_share_pct": round((total_events / grand_total * 100), 2) if grand_total else 0
            },
            "trend": trend
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/matrix")
def get_matrix(module: str = "food"):
    """
    Dynamically generates the operational matrix for periods, categories, and active cost heads.
    Supports filtering by module ('food', 'hostel', 'transport', 'all').
    """
    try:
        periods = db.execute_query(
            "SELECT id, period_code, period_label, start_date, operating_days, is_closed FROM billing_periods ORDER BY start_date"
        )
        num_periods = len(periods) or 1

        if module and module != "all":
            categories = db.execute_query(
                "SELECT id, code, name, display_order, module FROM expense_categories WHERE is_active = true AND module = %s ORDER BY display_order",
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
                "SELECT id, code, name, display_order, module FROM expense_categories WHERE is_active = true ORDER BY display_order"
            )
            cost_heads = db.execute_query("""
                SELECT ch.id, ch.category_id, ch.name, ch.code, ch.cost_behavior, ch.display_order, ch.default_vendor_id, v.name AS vendor_name
                FROM cost_heads ch
                LEFT JOIN vendors v ON ch.default_vendor_id = v.id
                WHERE ch.is_active = true
                ORDER BY ch.display_order
            """)

        entries = db.execute_query("SELECT cost_head_id, period_id, amount, remarks FROM monthly_expense_entries")
        entry_map = {}
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

            categories_data.append({
                "category_id": cat_id,
                "category_name": cat["name"],
                "category_code": cat["code"],
                "display_order": cat["display_order"],
                "items": formatted_items,
                "subtotal": {
                    "amounts": {str(k): round(v, 2) for k, v in cat_subtotal_by_period.items()},
                    "total": round(cat_total, 2),
                    "avg": cat_avg
                }
            })

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
                hostel_census_data[str(hr["period_id"])] = {
                    k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                    for k, v in hr.items()
                }
        except Exception as he:
            print(f"[Hostel Census Query Notice] {he}")

        # Query Transport Census / Fleet Metrics
        transport_census_data = {}
        try:
            t_rows = db.execute_query("SELECT * FROM transport_census_entries")
            for tr in t_rows:
                transport_census_data[str(tr["period_id"])] = {
                    k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                    for k, v in tr.items()
                }
        except Exception as te:
            print(f"[Transport Census Query Notice] {te}")

        return {
            "periods": periods,
            "categories": categories_data,
            "grand_total": grand_total_data,
            "census": census_data,
            "hostel_census": hostel_census_data,
            "transport_census": transport_census_data
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
def get_master_data():
    try:
        periods = db.execute_query("SELECT id, period_code, period_label, start_date, end_date, operating_days, is_closed FROM billing_periods ORDER BY start_date")
        categories = db.execute_query("SELECT id, code, name, display_order, is_active FROM expense_categories WHERE is_active = true ORDER BY display_order")
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
        existing = db.execute_query("SELECT id, code, cost_behavior, default_vendor_id FROM cost_heads WHERE id = %s", (cost_head_id,), fetch_all=False)
        if not existing:
            raise HTTPException(status_code=404, detail="Cost head not found")

        code = req.code or existing["code"]
        behavior = req.cost_behavior or existing["cost_behavior"] or "variable"
        vendor_id = req.default_vendor_id if req.default_vendor_id is not None else existing["default_vendor_id"]

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
            (req.category_id, req.name.strip(), code, behavior, vendor_id, req.display_order, req.is_active, cost_head_id)
        )
        return {"status": "success", "message": f"Cost head updated successfully"}
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

@app.get("/api/master/categories")
def get_categories(module: Optional[str] = None):
    try:
        if module and module != "all":
            return db.execute_query("""
                SELECT 
                    c.id, c.code, c.name, c.display_order, c.is_active, c.module,
                    COUNT(ch.id) AS cost_head_count
                FROM expense_categories c
                LEFT JOIN cost_heads ch ON c.id = ch.category_id AND ch.is_active = true
                WHERE c.is_active = true AND c.module = %s
                GROUP BY c.id, c.code, c.name, c.display_order, c.is_active, c.module
                ORDER BY c.display_order;
            """, (module,))
        return db.execute_query("""
            SELECT 
                c.id, c.code, c.name, c.display_order, c.is_active, c.module,
                COUNT(ch.id) AS cost_head_count
            FROM expense_categories c
            LEFT JOIN cost_heads ch ON c.id = ch.category_id AND ch.is_active = true
            WHERE c.is_active = true
            GROUP BY c.id, c.code, c.name, c.display_order, c.is_active, c.module
            ORDER BY c.display_order;
        """)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/master/categories")
def create_category(req: CategoryCreate):
    try:
        code = req.code
        if not code or not code.strip():
            clean = re.sub(r'[^a-zA-Z0-9]+', '_', req.name).strip('_').upper()
            code = f"CAT_{clean[:20]}"

        display_order = req.display_order
        if display_order is None:
            max_row = db.execute_query("SELECT COALESCE(MAX(display_order), 0) + 1 AS next_order FROM expense_categories", fetch_all=False)
            display_order = max_row["next_order"] if max_row else 10

        mod = req.module or "food"
        insert_sql = """
        INSERT INTO expense_categories (name, code, display_order, is_active, module) 
        VALUES (%s, %s, %s, true, %s) 
        RETURNING id, name, code, display_order, module;
        """
        cat = db.execute_query(insert_sql, (req.name.strip(), code, display_order, mod), fetch_all=False)
        return {"status": "success", "category": cat}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/master/categories/{category_id}")
def update_category(category_id: int, req: CategoryUpdate):
    try:
        update_sql = "UPDATE expense_categories SET name = %s, display_order = COALESCE(%s, display_order), is_active = %s WHERE id = %s;"
        db.execute_commit(update_sql, (req.name.strip(), req.display_order, req.is_active, category_id))
        return {"status": "success", "message": "Category updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/master/categories/{category_id}")
def delete_category(category_id: int):
    """
    Delete or deactivate an expense category. Checks for historical entries first.
    """
    try:
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
                # Soft deactivate category and associated cost heads to preserve financial integrity
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
                
                for item in req.entries:
                    upsert_sql = """
                    INSERT INTO monthly_expense_entries (period_id, cost_head_id, vendor_id, amount, remarks, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (period_id, cost_head_id)
                    DO UPDATE SET
                        amount = EXCLUDED.amount,
                        vendor_id = EXCLUDED.vendor_id,
                        remarks = EXCLUDED.remarks,
                        updated_at = CURRENT_TIMESTAMP;
                    """
                    cur.execute(upsert_sql, (req.period_id, item.cost_head_id, item.vendor_id, item.amount, item.remarks))

                # Update dining census (Students count, Staff count, Others, Total Persons, Production count)
                if any(v is not None for v in [req.active_students, req.active_staff, req.others_count, req.total_persons, req.production_meals]):
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
                    hc = req.hostel_census
                    hc_sql = """
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
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s
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
                    cur.execute(hc_sql, (
                        req.period_id,
                        int(hc.get("bed_capacity_boys") or 0),
                        int(hc.get("bed_capacity_girls") or 0),
                        int(hc.get("bed_capacity_total") or 0),
                        int(hc.get("students_boys") or 0),
                        int(hc.get("students_girls") or 0),
                        int(hc.get("students_total") or 0),
                        int(hc.get("staff_boys") or 0),
                        int(hc.get("staff_girls") or 0),
                        int(hc.get("staff_total") or 0),
                        int(hc.get("total_occupied") or 0),
                        int(hc.get("vacant_total") or 0),
                        int(hc.get("vacant_college") or 0),
                        float(hc.get("occupied_pct") or 0.0),
                        float(hc.get("vacant_pct") or 0.0),
                        int(hc.get("students_vacated") or 0),
                        int(hc.get("tickets_received") or 0),
                        int(hc.get("tickets_closed") or 0),
                        int(hc.get("tickets_open") or 0),
                        float(hc.get("tat_hours") or 0.0),
                        int(hc.get("quality_issues_received") or 0),
                        int(hc.get("quality_issues_closed") or 0),
                        int(hc.get("quality_issues_open") or 0),
                        int(hc.get("incidents_count") or 0),
                        int(hc.get("power_units") or 0),
                        float(hc.get("power_cost") or 0.0),
                        float(hc.get("water_purchase_cost") or 0.0),
                        int(hc.get("normal_water_litres") or 0),
                        float(hc.get("normal_water_cost") or 0.0),
                        int(hc.get("drinking_water_litres") or 0),
                        float(hc.get("drinking_water_cost") or 0.0),
                        float(hc.get("sq_feet") or 231701.0),
                        float(hc.get("approved_budget") or 131788118.0),
                        float(hc.get("cumulative_budget_spent") or 0.0),
                        str(hc.get("remarks") or "")
                    ))

                # Update Transport Census & Fleet Metrics
                if req.transport_census:
                    tc = req.transport_census
                    tc_sql = """
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
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s
                    )
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
                    cur.execute(tc_sql, (
                        req.period_id,
                        str(tc.get("vehicles_count") or "18+1"),
                        int(tc.get("passengers_count") or 0),
                        int(tc.get("students_count") or 0),
                        int(tc.get("staff_count") or 0),
                        float(tc.get("approved_kms") or 0.0),
                        float(tc.get("actual_kms") or 0.0),
                        float(tc.get("additional_kms") or 0.0),
                        float(tc.get("excess_kms_rps") or 0.0),
                        float(tc.get("fuel_expenses") or 0.0),
                        float(tc.get("diesel_litres") or 0.0),
                        float(tc.get("fc_cost") or 0.0),
                        float(tc.get("statutory_cost") or 0.0),
                        float(tc.get("repair_maintenance_cost") or 0.0),
                        float(tc.get("employee_cost") or 0.0),
                        float(tc.get("other_cost") or 0.0),
                        float(tc.get("total_expenses") or 0.0),
                        float(tc.get("fee_demand") or 0.0),
                        float(tc.get("fee_collected") or 0.0),
                        float(tc.get("fee_unpaid") or 0.0),
                        int(tc.get("service_tickets_raised") or 0),
                        int(tc.get("service_tickets_closed") or 0),
                        int(tc.get("service_tickets_open") or 0),
                        int(tc.get("quality_issues_received") or 0),
                        int(tc.get("quality_issues_closed") or 0),
                        int(tc.get("quality_issues_open") or 0),
                        int(tc.get("statutory_compliance") or 1),
                        int(tc.get("incidents_count") or 0),
                        float(tc.get("approved_budget") or 13730137.73),
                        float(tc.get("cumulative_budget_spent") or 0.0),
                        str(tc.get("remarks") or "")
                    ))

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

@app.post("/api/workstation/clone")
def clone_period_data(req: ClonePeriodRequest):
    try:
        clone_sql = """
        INSERT INTO monthly_expense_entries (period_id, cost_head_id, vendor_id, amount, remarks, status)
        SELECT %s, cost_head_id, vendor_id, amount, 'Cloned from baseline', 'draft'
        FROM monthly_expense_entries
        WHERE period_id = %s
        ON CONFLICT (period_id, cost_head_id)
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
