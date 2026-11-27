import os
from database import get_db_connection, release_db_connection

params = [
    ('1', 'projects_completed', 'Completed', 'Projects', 1, 'number', 'Projects', None, 1),
    ('', 'projects_in_progress', 'In Progress', 'Projects', 1, 'number', 'Projects', None, 2),
    ('', 'projects_total', 'Total', 'Projects', 1, 'number', 'Projects', 'projects_completed + projects_in_progress', 3),
    ('2', 'complaints_cctv', 'CCTV', 'Complaints', 2, 'number', 'Nos', None, 4),
    ('', 'complaints_biometric', 'Biometric', 'Complaints', 2, 'number', 'Nos', None, 5),
    ('', 'complaints_flapbarrier', 'Flapbarrier', 'Complaints', 2, 'number', 'Nos', None, 6),
    ('', 'complaints_total', 'Total', 'Complaints', 2, 'number', 'Nos', 'complaints_cctv + complaints_biometric + complaints_flapbarrier', 7),
    ('', 'repeated_complaints', 'Repeated complaints', 'Complaints', 2, 'number', 'Nos', None, 8),
    ('', 'time_taken_complaints_hrs', 'Time taken all complaints (Hrs)', 'Complaints', 2, 'decimal', 'Hrs', None, 9),
    ('', 'tat_complaints_hrs', 'TAT (Turn Around Time) Hrs', 'Complaints', 2, 'decimal', 'Hrs', None, 10),
    ('3', 'service_cctv', 'CCTV', 'Service request', 3, 'number', 'Nos', None, 11),
    ('', 'service_biometric', 'Biometric', 'Service request', 3, 'number', 'Nos', None, 12),
    ('', 'service_flapbarrier', 'Flapbarrier', 'Service request', 3, 'number', 'Nos', None, 13),
    ('', 'service_total', 'Total', 'Service request', 3, 'number', 'Nos', 'service_cctv + service_biometric + service_flapbarrier', 14),
    ('', 'repeated_work', 'Repeated work', 'Service request', 3, 'number', 'Nos', None, 15),
    ('', 'time_taken_service_hrs', 'Time taken all service request (Hrs)', 'Service request', 3, 'decimal', 'Hrs', None, 16),
    ('', 'tat_service_hrs', 'TAT (Turn Around Time) Hrs', 'Service request', 3, 'decimal', 'Hrs', None, 17),
    ('5', 'ppm_count', 'PPM', 'PPM', 4, 'number', 'Nos', None, 18),
    ('4', 'quality_issues_received', 'No. of Quality issues Received', 'Quality Issues', 5, 'number', 'Issues', None, 19),
    ('5', 'quality_issues_closed', 'No. of Quality issues Closed', 'Quality Issues', 5, 'number', 'Issues', None, 20),
    ('6', 'quality_issues_open', 'No. of Quality issues in Open', 'Quality Issues', 5, 'number', 'Issues', 'quality_issues_received - quality_issues_closed', 21),
    ('7', 'material_expenses', 'Material Expenses', 'Expenses', 6, 'cost', '₹', None, 22),
    ('8', 'labour_expenses', 'Labour Expenses', 'Expenses', 6, 'cost', '₹', None, 23),
    ('9', 'total_expenses', 'Total Expenses', 'Expenses', 6, 'cost', '₹', 'material_expenses + labour_expenses', 24),
    ('10', 'approved_budget', 'Approved Budget', 'Budget Tracking', 7, 'cost', '₹', None, 25),
    ('11', 'cumulative_budget_spent', 'Cumulative Budget spent (Actual expenses) till now', 'Budget Tracking', 7, 'cost', '₹', None, 26),
    ('12', 'balance', 'Balance', 'Budget Tracking', 7, 'cost', '₹', 'approved_budget - cumulative_budget_spent', 27)
]

def seed():
    conn = get_db_connection()
    cur = conn.cursor()

    # Ensure tables exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cctv_master_parameters (
            id SERIAL PRIMARY KEY,
            s_no VARCHAR(20) DEFAULT '',
            param_key VARCHAR(100) NOT NULL UNIQUE,
            param_name VARCHAR(255) NOT NULL,
            section VARCHAR(100) NOT NULL,
            section_order INT NOT NULL DEFAULT 1,
            input_type VARCHAR(50) NOT NULL DEFAULT 'number',
            unit VARCHAR(50) DEFAULT '',
            formula TEXT DEFAULT NULL,
            display_order INT NOT NULL DEFAULT 50,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE cctv_master_parameters ADD COLUMN IF NOT EXISTS s_no VARCHAR(20) DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_cctv_master_params_section ON cctv_master_parameters(section);
        CREATE INDEX IF NOT EXISTS idx_cctv_master_params_active ON cctv_master_parameters(is_active);

        CREATE TABLE IF NOT EXISTS cctv_monthly_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            branch VARCHAR(50) NOT NULL DEFAULT 'all',
            projects_completed INT DEFAULT 0,
            projects_in_progress INT DEFAULT 0,
            projects_total INT DEFAULT 0,
            complaints_cctv INT DEFAULT 0,
            complaints_biometric INT DEFAULT 0,
            complaints_flapbarrier INT DEFAULT 0,
            complaints_total INT DEFAULT 0,
            repeated_complaints INT DEFAULT 0,
            time_taken_complaints_hrs NUMERIC(10, 2) DEFAULT 0.0,
            tat_complaints_hrs NUMERIC(10, 2) DEFAULT 0.0,
            service_cctv INT DEFAULT 0,
            service_biometric INT DEFAULT 0,
            service_flapbarrier INT DEFAULT 0,
            service_total INT DEFAULT 0,
            repeated_work INT DEFAULT 0,
            time_taken_service_hrs NUMERIC(10, 2) DEFAULT 0.0,
            tat_service_hrs NUMERIC(10, 2) DEFAULT 0.0,
            ppm_count INT DEFAULT 0,
            quality_issues_received INT DEFAULT 0,
            quality_issues_closed INT DEFAULT 0,
            quality_issues_open INT DEFAULT 0,
            material_expenses NUMERIC(15, 2) DEFAULT 0.0,
            labour_expenses NUMERIC(15, 2) DEFAULT 0.0,
            total_expenses NUMERIC(15, 2) DEFAULT 0.0,
            approved_budget NUMERIC(15, 2) DEFAULT 0.0,
            cumulative_budget_spent NUMERIC(15, 2) DEFAULT 0.0,
            balance NUMERIC(15, 2) DEFAULT 0.0,
            remarks TEXT DEFAULT '',
            custom_metrics JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cctv_monthly_entries_period ON cctv_monthly_entries(period_id);
        ALTER TABLE cctv_monthly_entries ADD COLUMN IF NOT EXISTS branch VARCHAR(50) NOT NULL DEFAULT 'all';
    ''')
    conn.commit()

    # Seed parameters
    for p in params:
        cur.execute('''
            INSERT INTO cctv_master_parameters (s_no, param_key, param_name, section, section_order, input_type, unit, formula, display_order, is_system, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE)
            ON CONFLICT (param_key) DO UPDATE
            SET s_no = EXCLUDED.s_no,
                param_name = EXCLUDED.param_name,
                section = EXCLUDED.section,
                section_order = EXCLUDED.section_order,
                input_type = EXCLUDED.input_type,
                unit = EXCLUDED.unit,
                formula = EXCLUDED.formula,
                display_order = EXCLUDED.display_order;
        ''', p)

    # Seed CCTV billing periods (Jun - Dec 2026)
    cctv_periods = [
        ('Jun 1st to 30th', '2026-06', '2026-06-01', '2026-06-30', 'cctv'),
        ('Jul 1st to 31st', '2026-07', '2026-07-01', '2026-07-31', 'cctv'),
        ('Aug 1st to 31st', '2026-08', '2026-08-01', '2026-08-31', 'cctv'),
        ('Sep 1st to 30th', '2026-09', '2026-09-01', '2026-09-30', 'cctv'),
        ('Oct 1st to 31st', '2026-10', '2026-10-01', '2026-10-31', 'cctv'),
        ('Nov 1st to 30th', '2026-11', '2026-11-01', '2026-11-30', 'cctv'),
        ('Dec 1st to 31st', '2026-12', '2026-12-01', '2026-12-31', 'cctv')
    ]

    for cp in cctv_periods:
        cur.execute('''
            SELECT id FROM billing_periods WHERE module = %s AND period_code = %s;
        ''', (cp[4], cp[1]))
        row = cur.fetchone()
        if not row:
            cur.execute('''
                INSERT INTO billing_periods (fiscal_year_id, period_label, period_code, start_date, end_date, module, branch, is_closed)
                VALUES (1, %s, %s, %s, %s, %s, 'all', FALSE);
            ''', cp)

    # Original CCTV Monthly Entries (Jun'26 - Oct'26)
    cctv_entries = [
        # (period_code, proj_comp, proj_prog, proj_tot, comp_cctv, comp_bio, comp_flap, comp_tot, rep_comp, time_comp, tat_comp, srv_cctv, srv_bio, srv_flap, srv_tot, rep_work, time_srv, tat_srv, ppm, qi_rec, qi_cls, qi_opn, mat_exp, lab_exp, tot_exp, app_bud, cum_spent, bal)
        ('2026-06', 4, 11, 15,  23, 8, 3, 34,   0, 43.0, 1.26,   25, 6, 3, 34,   0, 59.0, 1.74,   50,   0, 0, 0,   4422, 142114, 146536,   3139116, 146536, 2992580),
        ('2026-07', 0, 8, 8,    62, 2, 8, 72,   0, 85.5, 1.19,   31, 7, 2, 40,   0, 52.0, 1.30,   92,   0, 0, 0,   91981, 146075, 238056,  3139116, 384592, 2754524),
        ('2026-08', 0, 8, 8,    2, 20, 4, 26,   0, 28.0, 1.08,   2, 25, 2, 29,   0, 51.0, 1.76,   61,   0, 0, 0,   174339, 145532, 319871, 3139116, 704463, 2434653),
        ('2026-09', 0, 8, 8,    24, 3, 8, 35,   0, 29.0, 0.83,   34, 3, 3, 40,   0, 92.0, 2.29,   126,  0, 0, 0,   17362, 142459, 159821,  3139116, 836704, 2302412),
        ('2026-10', 1, 8, 9,    14, 0, 1, 15,   0, 112.0, 7.47,  17, 2, 1, 20,   0, 35.0, 1.75,   118,  0, 0, 0,   85417, 156596, 242013,  3139116, 1078717, 2060399),
    ]

    for entry in cctv_entries:
        p_code = entry[0]
        cur.execute("SELECT id FROM billing_periods WHERE module = 'cctv' AND period_code = %s;", (p_code,))
        p_row = cur.fetchone()
        if p_row:
            pid = p_row[0]
            cur.execute('''
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
                    approved_budget, cumulative_budget_spent, balance
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
                    %s, %s, %s
                ) ON CONFLICT (period_id) DO UPDATE
                SET projects_completed = EXCLUDED.projects_completed,
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
                    balance = EXCLUDED.balance;
            ''', (pid, *entry[1:]))
            print(f"Seeded CCTV {p_code} entry with period_id={pid}")

    conn.commit()
    cur.close()
    release_db_connection(conn)
    print("Parameters, periods, and Jun-Oct CCTV entries seeded successfully!")

if __name__ == '__main__':
    seed()
