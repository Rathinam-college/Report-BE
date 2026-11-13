-- ============================================================
-- RATHINAM GROUP OF INSTITUTIONS
-- FOOD & DINING OPERATIONS MANAGEMENT SYSTEM
-- PostgreSQL 16 Relational Database Schema & Reporting Views
-- Compatible with: Food.xlsx Master & Monthly Entry Data
-- ============================================================

-- ------------------------------------------------------------
-- 1. CLEANUP (Drop existing views, tables, and types)
-- ------------------------------------------------------------
DROP VIEW IF EXISTS vw_food_mom_variance CASCADE;
DROP VIEW IF EXISTS vw_food_category_share CASCADE;
DROP VIEW IF EXISTS vw_food_monthly_matrix CASCADE;
DROP VIEW IF EXISTS vw_food_executive_summary CASCADE;
DROP VIEW IF EXISTS vw_food_monthly_ledger CASCADE;

DROP TABLE IF EXISTS dining_census_entries CASCADE;
DROP TABLE IF EXISTS monthly_expense_entries CASCADE;
DROP TABLE IF EXISTS utility_meter_logs CASCADE;
DROP TABLE IF EXISTS cost_heads CASCADE;
DROP TABLE IF EXISTS expense_categories CASCADE;
DROP TABLE IF EXISTS vendors CASCADE;
DROP TABLE IF EXISTS billing_periods CASCADE;
DROP TABLE IF EXISTS fiscal_years CASCADE;

DROP TYPE IF EXISTS cost_behavior_enum CASCADE;
DROP TYPE IF EXISTS entry_status_enum CASCADE;
DROP TYPE IF EXISTS vendor_type_enum CASCADE;

-- ------------------------------------------------------------
-- 2. ENUM TYPES
-- ------------------------------------------------------------
CREATE TYPE cost_behavior_enum AS ENUM ('variable', 'semi_variable', 'fixed');
CREATE TYPE entry_status_enum AS ENUM ('draft', 'audited', 'locked');
CREATE TYPE vendor_type_enum AS ENUM ('internal', 'catering', 'housekeeping', 'event_manpower', 'fuel_supplier', 'utility', 'maintenance');

-- ------------------------------------------------------------
-- 3. MASTER DATA TABLES
-- ------------------------------------------------------------

-- Fiscal Year Master (e.g., 2026-2027)
CREATE TABLE fiscal_years (
    id              SERIAL PRIMARY KEY,
    year_code       VARCHAR(10) NOT NULL UNIQUE,       -- '2026-2027'
    start_date      DATE NOT NULL,                     -- 2026-06-01
    end_date        DATE NOT NULL,                     -- 2027-05-31
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Monthly Billing Cycles / Periods Master
CREATE TABLE billing_periods (
    id              SERIAL PRIMARY KEY,
    fiscal_year_id  INT NOT NULL REFERENCES fiscal_years(id) ON DELETE RESTRICT,
    period_code     VARCHAR(10) NOT NULL UNIQUE,       -- '2026-06', '2026-07'
    period_label    VARCHAR(20) NOT NULL,              -- "Jun'26", "Jul'26"
    start_date      DATE NOT NULL,                     -- 2026-06-01
    end_date        DATE NOT NULL,                     -- 2026-06-30
    operating_days  INT NOT NULL DEFAULT 30,           -- Days mess operated
    is_closed       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Vendors & Service Agencies Master
CREATE TABLE vendors (
    id              SERIAL PRIMARY KEY,
    vendor_code     VARCHAR(30) NOT NULL UNIQUE,       -- 'VEND-ADITHYA', 'VEND-SIRI'
    name            VARCHAR(150) NOT NULL,             -- 'Adithya Housekeeping'
    vendor_type     vendor_type_enum NOT NULL DEFAULT 'internal',
    contact_person  VARCHAR(100),
    phone           VARCHAR(25),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Major Expense Categories Master
CREATE TABLE expense_categories (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(30) NOT NULL UNIQUE,       -- 'FOOD_MATERIAL', 'FOOD_LABOUR'
    name            VARCHAR(100) NOT NULL,             -- 'Food Material', 'Food Labour'
    display_order   INT NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Specific Cost Heads / Line Items Master
CREATE TABLE cost_heads (
    id              SERIAL PRIMARY KEY,
    category_id     INT NOT NULL REFERENCES expense_categories(id) ON DELETE RESTRICT,
    default_vendor_id INT REFERENCES vendors(id) ON DELETE SET NULL,
    code            VARCHAR(50) NOT NULL UNIQUE,       -- 'MAT_ISSUED', 'FUEL_GAS', 'SALARY'
    name            VARCHAR(120) NOT NULL,             -- 'Material issued', 'Fuel Expenses (Gas)'
    cost_behavior   cost_behavior_enum NOT NULL DEFAULT 'variable',
    display_order   INT NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 4. ENTRY DATA TABLES (PERIODIC TRANSACTIONS)
-- ------------------------------------------------------------

-- Monthly Financial Expense Entries (Direct Ledger)
CREATE TABLE monthly_expense_entries (
    id              BIGSERIAL PRIMARY KEY,
    period_id       INT NOT NULL REFERENCES billing_periods(id) ON DELETE RESTRICT,
    cost_head_id    INT NOT NULL REFERENCES cost_heads(id) ON DELETE RESTRICT,
    vendor_id       INT REFERENCES vendors(id) ON DELETE SET NULL,
    amount          NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    status          entry_status_enum NOT NULL DEFAULT 'audited',
    remarks         TEXT,
    recorded_by     VARCHAR(50) DEFAULT 'Operations Team',
    audited_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_period_cost_head UNIQUE (period_id, cost_head_id)
);

-- Student & Staff Dining Census / Attendance (For Per-Head Metrics)
CREATE TABLE dining_census_entries (
    id                  SERIAL PRIMARY KEY,
    period_id           INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE RESTRICT,
    active_students     INT NOT NULL DEFAULT 0,        -- Total enrolled hostel diners
    active_staff        INT NOT NULL DEFAULT 0,        -- Total enrolled dining staff
    production_meals    INT NOT NULL DEFAULT 0,        -- Total meal plates produced
    booked_tokens       INT NOT NULL DEFAULT 0,        -- Advance booked meals
    scanned_tokens      INT NOT NULL DEFAULT 0,        -- Actually scanned tokens
    unscanned_meals     INT GENERATED ALWAYS AS (booked_tokens - scanned_tokens) STORED,
    remarks             TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Utility Logs (Optional Granular Tracking for Water & LPG)
CREATE TABLE utility_meter_logs (
    id                  BIGSERIAL PRIMARY KEY,
    period_id           INT NOT NULL REFERENCES billing_periods(id) ON DELETE RESTRICT,
    utility_type        VARCHAR(30) NOT NULL,          -- 'water_tanker', 'drinking_can', 'lpg_cylinders'
    units_consumed      NUMERIC(10, 2) NOT NULL,       -- Litres, Cans, or KG
    unit_rate           NUMERIC(10, 2) NOT NULL,       -- Cost per unit
    total_cost          NUMERIC(12, 2) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 5. INDEXES FOR PERFORMANCE
-- ------------------------------------------------------------
CREATE INDEX idx_exp_entries_period ON monthly_expense_entries(period_id);
CREATE INDEX idx_exp_entries_cost_head ON monthly_expense_entries(cost_head_id);
CREATE INDEX idx_exp_entries_vendor ON monthly_expense_entries(vendor_id);
CREATE INDEX idx_periods_start ON billing_periods(start_date);

-- ------------------------------------------------------------
-- 6. REPORTING & ANALYTICAL VIEWS
-- ------------------------------------------------------------

-- View 1: Complete Normalized Monthly Food Ledger with Hierarchy
CREATE OR REPLACE VIEW vw_food_monthly_ledger AS
SELECT 
    p.period_code,
    p.period_label,
    p.start_date AS period_date,
    c.name AS category_name,
    c.display_order AS category_order,
    ch.name AS line_item,
    ch.code AS cost_head_code,
    ch.cost_behavior,
    v.name AS vendor_name,
    e.amount,
    e.status
FROM monthly_expense_entries e
JOIN billing_periods p ON e.period_id = p.id
JOIN cost_heads ch ON e.cost_head_id = ch.id
JOIN expense_categories c ON ch.category_id = c.id
LEFT JOIN vendors v ON e.vendor_id = v.id
ORDER BY p.start_date, c.display_order, ch.display_order;

-- View 2: Executive Monthly Category Totals & Grand Total
CREATE OR REPLACE VIEW vw_food_executive_summary AS
SELECT 
    p.period_code,
    p.period_label,
    p.start_date,
    SUM(CASE WHEN c.code = 'FOOD_MATERIAL' THEN e.amount ELSE 0 END) AS total_material_fuel,
    SUM(CASE WHEN c.code = 'FOOD_LABOUR' THEN e.amount ELSE 0 END) AS total_labour,
    SUM(CASE WHEN c.code IN ('FOOD_MATERIAL', 'FOOD_LABOUR') THEN e.amount ELSE 0 END) AS subtotal_food_expenses,
    SUM(CASE WHEN c.code = 'FC_MAINTENANCE' THEN e.amount ELSE 0 END) AS total_maintenance_utilities,
    SUM(CASE WHEN c.code = 'EVENTS_ADDITIONAL' THEN e.amount ELSE 0 END) AS total_event_purchase,
    SUM(CASE WHEN c.code = 'FOOD_FESTIVAL' THEN e.amount ELSE 0 END) AS total_food_festival,
    SUM(e.amount) AS grand_total_expenses
FROM monthly_expense_entries e
JOIN billing_periods p ON e.period_id = p.id
JOIN cost_heads ch ON e.cost_head_id = ch.id
JOIN expense_categories c ON ch.category_id = c.id
GROUP BY p.period_code, p.period_label, p.start_date
ORDER BY p.start_date;

-- View 3: Month-over-Month (MoM) Variance Analysis
CREATE OR REPLACE VIEW vw_food_mom_variance AS
WITH ranked_ledger AS (
    SELECT 
        p.id AS period_id,
        p.period_label,
        p.start_date,
        ch.id AS cost_head_id,
        ch.name AS line_item,
        c.name AS category_name,
        e.amount,
        LAG(e.amount) OVER (PARTITION BY ch.id ORDER BY p.start_date) AS prev_month_amount
    FROM monthly_expense_entries e
    JOIN billing_periods p ON e.period_id = p.id
    JOIN cost_heads ch ON e.cost_head_id = ch.id
    JOIN expense_categories c ON ch.category_id = c.id
)
SELECT 
    period_label,
    category_name,
    line_item,
    amount AS current_amount,
    prev_month_amount,
    (amount - prev_month_amount) AS mom_diff_inr,
    CASE 
        WHEN prev_month_amount IS NULL OR prev_month_amount = 0 THEN NULL
        ELSE ROUND(((amount - prev_month_amount) / prev_month_amount) * 100, 2)
    END AS mom_growth_pct
FROM ranked_ledger
ORDER BY start_date, category_name, line_item;

-- View 4: Percentage Share of Total Monthly Expenditure
CREATE OR REPLACE VIEW vw_food_category_share AS
WITH monthly_totals AS (
    SELECT period_id, SUM(amount) AS total_month_spend
    FROM monthly_expense_entries
    GROUP BY period_id
)
SELECT 
    p.period_label,
    c.name AS category_name,
    ch.name AS line_item,
    e.amount,
    mt.total_month_spend,
    ROUND((e.amount / mt.total_month_spend) * 100, 2) AS percentage_share
FROM monthly_expense_entries e
JOIN billing_periods p ON e.period_id = p.id
JOIN cost_heads ch ON e.cost_head_id = ch.id
JOIN expense_categories c ON ch.category_id = c.id
JOIN monthly_totals mt ON e.period_id = mt.period_id
ORDER BY p.start_date, c.display_order, ch.display_order;

-- View 5: Cross-Tab Matrix Matching Food.xlsx (Jun'26 to Oct'26)
CREATE OR REPLACE VIEW vw_food_monthly_matrix AS
SELECT 
    c.name AS category,
    ch.name AS description,
    MAX(CASE WHEN p.period_code = '2026-06' THEN e.amount ELSE NULL END) AS "Jun_26",
    MAX(CASE WHEN p.period_code = '2026-07' THEN e.amount ELSE NULL END) AS "Jul_26",
    MAX(CASE WHEN p.period_code = '2026-08' THEN e.amount ELSE NULL END) AS "Aug_26",
    MAX(CASE WHEN p.period_code = '2026-09' THEN e.amount ELSE NULL END) AS "Sept_26",
    MAX(CASE WHEN p.period_code = '2026-10' THEN e.amount ELSE NULL END) AS "Oct_26",
    SUM(e.amount) AS total_5_months,
    ROUND(AVG(e.amount), 2) AS monthly_avg
FROM cost_heads ch
JOIN expense_categories c ON ch.category_id = c.id
LEFT JOIN monthly_expense_entries e ON ch.id = e.cost_head_id
LEFT JOIN billing_periods p ON e.period_id = p.id
GROUP BY c.id, c.name, c.display_order, ch.id, ch.name, ch.display_order
ORDER BY c.display_order, ch.display_order;

-- ============================================================
-- 7. SEED DATA (EXACT DATA FROM Food.xlsx)
-- ============================================================

-- 1. Fiscal Year
INSERT INTO fiscal_years (year_code, start_date, end_date) 
VALUES ('2026-2027', '2026-06-01', '2027-05-31');

-- 2. Billing Periods (Jun'26 to Oct'26)
INSERT INTO billing_periods (fiscal_year_id, period_code, period_label, start_date, end_date, operating_days) VALUES
(1, '2026-06', 'Jun''26', '2026-06-01', '2026-06-30', 30),
(1, '2026-07', 'Jul''26', '2026-07-01', '2026-07-31', 31),
(1, '2026-08', 'Aug''26', '2026-08-01', '2026-08-31', 31),
(1, '2026-09', 'Sept''26', '2026-09-01', '2026-09-30', 30),
(1, '2026-10', 'Oct''26', '2026-10-01', '2026-10-31', 31);

-- 3. Vendors
INSERT INTO vendors (vendor_code, name, vendor_type) VALUES
('VEND-INTERNAL', 'In-House Dining Management', 'internal'),
('VEND-LPG', 'Commercial LPG Gas Agency', 'fuel_supplier'),
('VEND-CATERING', 'External Catering Partner', 'catering'),
('VEND-ADITHYA', 'Adithya Housekeeping Services', 'housekeeping'),
('VEND-SIRI', 'Siri Event Staffing', 'event_manpower'),
('VEND-MAINT', 'Food Court Equipment & Civil Contractors', 'maintenance'),
('VEND-WATER', 'Campus Water & Tanker Logistics', 'utility'),
('VEND-TRANSPORT', 'Food Vehicle Logistics', 'utility');

-- 4. Expense Categories
INSERT INTO expense_categories (code, name, display_order) VALUES
('FOOD_MATERIAL', 'Food Material', 1),
('FOOD_LABOUR', 'Food Labour', 2),
('FC_MAINTENANCE', 'FC maintenance/ Power/Water/Veh', 3),
('EVENTS_ADDITIONAL', 'Event/ Additional food', 4),
('FOOD_FESTIVAL', 'Food Festival', 5);

-- 5. Cost Heads / Line Items
INSERT INTO cost_heads (category_id, default_vendor_id, code, name, cost_behavior, display_order) VALUES
(1, 1, 'MAT_ISSUED', 'Material issued', 'variable', 1),
(1, 2, 'FUEL_GAS', 'Fuel Expenses (Gas)', 'variable', 2),
(2, 1, 'LAB_SALARY', 'Salary', 'fixed', 3),
(2, 3, 'LAB_CATERING', 'Catering Vendor', 'semi_variable', 4),
(2, 4, 'LAB_HOUSEKEEPING', 'Adithya Housekeeping', 'fixed', 5),
(2, 5, 'LAB_SIRI_EVENT', 'Siri event', 'semi_variable', 6),
(3, 6, 'FC_MAINTENANCE', 'Food Court Maintenance', 'semi_variable', 7),
(3, 7, 'FC_WATER', 'Water consumption', 'semi_variable', 8),
(3, 8, 'FC_VEHICLE', 'Food Vehicle', 'semi_variable', 9),
(4, 1, 'EVENT_PURCHASE', 'Event Purchase', 'variable', 10),
(5, 1, 'FOOD_FESTIVAL', 'Food Festival', 'variable', 11);

-- 6. Monthly Transaction Entries (Exact values from Food.xlsx)

-- Period 1: Jun'26 (period_id: 1)
INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount) VALUES
(1, 1, 5839162.00),   -- Material issued
(1, 2, 823395.00),    -- Fuel Expenses (Gas)
(1, 3, 1694705.00),   -- Salary
(1, 4, 260700.00),    -- Catering Vendor
(1, 5, 469920.00),    -- Adithya Housekeeping
(1, 6, 229268.00),    -- Siri event
(1, 7, 293075.00),    -- Food Court Maintenance
(1, 8, 89756.25),     -- Water consumption
(1, 9, 43392.11),     -- Food Vehicle
(1, 10, 254495.00);   -- Event Purchase

-- Period 2: Jul'26 (period_id: 2)
INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount) VALUES
(2, 1, 7361269.00),   -- Material issued
(2, 2, 958560.00),    -- Fuel Expenses (Gas)
(2, 3, 1628691.00),   -- Salary
(2, 4, 410500.00),    -- Catering Vendor
(2, 5, 525580.00),    -- Adithya Housekeeping
(2, 6, 302604.00),    -- Siri event
(2, 7, 131972.00),    -- Food Court Maintenance
(2, 8, 159129.40),    -- Water consumption
(2, 9, 30441.70),     -- Food Vehicle
(2, 10, 217870.00);   -- Event Purchase

-- Period 3: Aug'26 (period_id: 3)
INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount) VALUES
(3, 1, 6949789.00),   -- Material issued
(3, 2, 717708.00),    -- Fuel Expenses (Gas)
(3, 3, 1862412.00),   -- Salary
(3, 4, 299600.00),    -- Catering Vendor
(3, 5, 507320.00),    -- Adithya Housekeeping
(3, 6, 297851.00),    -- Siri event
(3, 7, 275221.00),    -- Food Court Maintenance
(3, 8, 149484.33),    -- Water consumption
(3, 9, 24023.88),     -- Food Vehicle
(3, 10, 114490.00),   -- Event Purchase
(3, 11, 551639.00);   -- Food Festival

-- Period 4: Sept'26 (period_id: 4)
INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount) VALUES
(4, 1, 9891873.00),   -- Material issued
(4, 2, 1042274.00),   -- Fuel Expenses (Gas)
(4, 3, 1834324.00),   -- Salary
(4, 4, 515200.00),    -- Catering Vendor
(4, 5, 464530.00),    -- Adithya Housekeeping
(4, 6, 495760.00),    -- Siri event
(4, 7, 327232.00),    -- Food Court Maintenance
(4, 8, 215954.70),    -- Water consumption
(4, 9, 33940.45),     -- Food Vehicle
(4, 10, 76775.00);    -- Event Purchase

-- Period 5: Oct'26 (period_id: 5)
-- Note: Water consumption pending audit reconciliation
INSERT INTO monthly_expense_entries (period_id, cost_head_id, amount, remarks) VALUES
(5, 1, 9140730.00, NULL),                      -- Material issued
(5, 2, 982945.00, NULL),                       -- Fuel Expenses (Gas)
(5, 3, 1988139.00, NULL),                      -- Salary
(5, 4, 498600.00, NULL),                       -- Catering Vendor
(5, 5, 459360.00, NULL),                       -- Adithya Housekeeping
(5, 6, 550121.60, NULL),                       -- Siri event
(5, 7, 378443.00, NULL),                       -- Food Court Maintenance
(5, 9, 81039.58, 'Vehicle overhaul & fuel'),   -- Food Vehicle
(5, 10, 210525.00, 'Festive events');          -- Event Purchase

-- ------------------------------------------------------------
-- 8. VALIDATION QUERY TO VERIFY TOTALS MATCH Food.xlsx
-- ------------------------------------------------------------
-- SELECT * FROM vw_food_executive_summary;
-- SELECT * FROM vw_food_monthly_matrix;

