import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "food_operations")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Create connection pool
db_pool = None

def get_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
    return db_pool

def get_db_connection():
    pool = get_db_pool()
    return pool.getconn()

def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)

def execute_query(query, params=None, fetch_all=True):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            if fetch_all:
                res = cur.fetchall()
            else:
                res = cur.fetchone()
            conn.commit()
            return res
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        release_db_connection(conn)

def execute_commit(query, params=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            conn.commit()
            return cur.rowcount
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        release_db_connection(conn)

def auto_migrate():
    """
    Automatically verifies and applies schema migrations on startup.
    Idempotent: safe to run multiple times across environments.
    """
    migrations = [
        """
        CREATE TABLE IF NOT EXISTS dining_census_entries (
            id SERIAL PRIMARY KEY,
            period_id INT NOT NULL UNIQUE REFERENCES billing_periods(id) ON DELETE CASCADE,
            active_students INT NOT NULL DEFAULT 0,
            active_staff INT NOT NULL DEFAULT 0,
            others_count INT NOT NULL DEFAULT 0,
            total_persons INT NOT NULL DEFAULT 0,
            production_meals INT NOT NULL DEFAULT 0,
            booked_tokens INT NOT NULL DEFAULT 0,
            scanned_tokens INT NOT NULL DEFAULT 0,
            unscanned_meals INT NOT NULL DEFAULT 0,
            remarks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS others_count INT NOT NULL DEFAULT 0;",
        "ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS total_persons INT NOT NULL DEFAULT 0;",
        "ALTER TABLE dining_census_entries ADD COLUMN IF NOT EXISTS production_meals INT NOT NULL DEFAULT 0;"
    ]
    for sql in migrations:
        try:
            execute_commit(sql)
        except Exception as e:
            print(f"[AutoMigrate] Notice: {e}")


