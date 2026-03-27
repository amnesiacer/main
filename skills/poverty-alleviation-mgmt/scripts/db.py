"""
数据库连接与初始化模块
"""
import psycopg2
import psycopg2.extras

DB_URL = "postgresql://amnesiac:52Xiaofang@www.amnesiac.cn:15432/Mydates"

INIT_SQL = """
CREATE TABLE IF NOT EXISTS pam_projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    villages TEXT[],
    content TEXT,
    investment NUMERIC(15,2),
    operator VARCHAR(200),
    contract_start DATE,
    contract_end DATE,
    agreed_income NUMERIC(15,4),
    income_frequency VARCHAR(20) DEFAULT 'year',
    attachment_path TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pam_income_records (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES pam_projects(id) ON DELETE CASCADE,
    project_name VARCHAR(200),
    period_label VARCHAR(100),
    period_start DATE,
    period_end DATE,
    due_amount NUMERIC(15,4),
    paid_amount NUMERIC(15,4) DEFAULT 0,
    arrear_amount NUMERIC(15,4) GENERATED ALWAYS AS (due_amount - paid_amount) STORED,
    is_distributed BOOLEAN DEFAULT FALSE,
    distributed_at DATE,
    distributed_amount NUMERIC(15,4),
    remark TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, period_start)
);

CREATE TABLE IF NOT EXISTS pam_distribution_details (
    id SERIAL PRIMARY KEY,
    income_record_id INTEGER REFERENCES pam_income_records(id) ON DELETE CASCADE,
    project_name VARCHAR(200),
    period_label VARCHAR(100),
    name VARCHAR(100),
    id_card VARCHAR(18),
    amount NUMERIC(15,2),
    bank_card VARCHAR(30),
    remark TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_income_project ON pam_income_records(project_id);
CREATE INDEX IF NOT EXISTS idx_dist_record ON pam_distribution_details(income_record_id);
"""


def get_conn():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    return conn


def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_conn()
    cur = get_cursor(conn)
    try:
        cur.execute(INIT_SQL)
        conn.commit()
    finally:
        cur.close()
        conn.close()
