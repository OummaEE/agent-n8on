"""
setup_supabase.py — One-time Supabase setup for events_parsed table

Auto-creates the table using psycopg2 if SUPABASE_DB_PASSWORD is set in .env.
Otherwise prints the SQL for manual execution.

Usage:
    python setup_supabase.py
"""

import sys
import os
from pathlib import Path

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "")
FB_EVENTS_TABLE = os.getenv("FB_EVENTS_TABLE", "events_parsed")

SQL_FILE = Path(__file__).parent / "sql" / "create_events_parsed.sql"
DASHBOARD_URL = f"https://supabase.com/dashboard/project/{SUPABASE_URL.split('.')[0].split('//')[1]}/sql/new" if SUPABASE_URL else ""

_CREATE_SQL = SQL_FILE.read_text(encoding="utf-8") if SQL_FILE.exists() else f"""
CREATE TABLE IF NOT EXISTS {FB_EVENTS_TABLE} (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title            TEXT        NOT NULL,
    date             DATE,
    time             TEXT,
    location         TEXT,
    description      TEXT,
    registration_url TEXT,
    source_url       TEXT        UNIQUE,
    group_url        TEXT,
    group_name       TEXT,
    post_author      TEXT,
    image_url        TEXT,
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_{FB_EVENTS_TABLE}_date ON {FB_EVENTS_TABLE} (date) WHERE date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_{FB_EVENTS_TABLE}_group_url ON {FB_EVENTS_TABLE} (group_url);
CREATE INDEX IF NOT EXISTS idx_{FB_EVENTS_TABLE}_scraped_at ON {FB_EVENTS_TABLE} (scraped_at DESC);
"""


def _extract_project_ref(url: str) -> str:
    """Extract project ref from https://{ref}.supabase.co"""
    try:
        return url.split("//")[1].split(".")[0]
    except Exception:
        return ""


def _check_table_exists_rest(client, table: str) -> bool:
    """Check if table exists via REST API (no DDL needed)."""
    try:
        client.table(table).select("id").limit(1).execute()
        return True
    except Exception as e:
        msg = str(e)
        if "PGRST205" in msg or "not found" in msg.lower() or "does not exist" in msg.lower():
            return False
        # Any other error means it might exist but there's a different problem
        return False


def _create_table_via_psycopg2(db_password: str, project_ref: str, sql: str) -> tuple[bool, str]:
    """
    Try to auto-create the table using direct psycopg2 connection.

    Tries in order:
    1. Direct DB host: db.{ref}.supabase.co:5432 (most reliable for DDL)
    2. Supavisor session mode: aws-0-{region}.pooler.supabase.com:6543
       (session mode supports DDL, unlike transaction mode on port 5432)
    """
    try:
        import psycopg2
    except ImportError:
        return False, "psycopg2-binary не установлен: pip install psycopg2-binary"

    connection_targets = [
        # Direct connection (best for DDL)
        {
            "host":    f"db.{project_ref}.supabase.co",
            "port":    5432,
            "user":    "postgres",
            "label":   "direct",
        },
        # Supavisor session mode (supports DDL, port 6543)
        {
            "host":    "aws-0-eu-central-1.pooler.supabase.com",
            "port":    6543,
            "user":    f"postgres.{project_ref}",
            "label":   "pooler eu-central-1",
        },
        {
            "host":    "aws-0-us-east-1.pooler.supabase.com",
            "port":    6543,
            "user":    f"postgres.{project_ref}",
            "label":   "pooler us-east-1",
        },
        {
            "host":    "aws-0-us-west-1.pooler.supabase.com",
            "port":    6543,
            "user":    f"postgres.{project_ref}",
            "label":   "pooler us-west-1",
        },
        {
            "host":    "aws-0-ap-southeast-1.pooler.supabase.com",
            "port":    6543,
            "user":    f"postgres.{project_ref}",
            "label":   "pooler ap-southeast-1",
        },
    ]

    last_error = ""
    for target in connection_targets:
        label = target["label"]
        try:
            print(f"    Connecting via {label}...", end=" ", flush=True)
            conn = psycopg2.connect(
                host=target["host"],
                port=target["port"],
                dbname="postgres",
                user=target["user"],
                password=db_password,
                connect_timeout=8,
                sslmode="require",
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                # Execute each statement separately (split on ';')
                statements = [s.strip() for s in sql.split(";") if s.strip()]
                for stmt in statements:
                    cur.execute(stmt)
            conn.close()
            print("✅")
            return True, label
        except Exception as e:
            last_error = str(e)
            print(f"❌ {last_error[:80]}")
            continue

    return False, f"Все попытки подключения провалились. Последняя ошибка: {last_error}"


def main():
    print("=" * 65)
    print("  Supabase Setup — Facebook Scraper (events_parsed)")
    print("=" * 65)

    # ── Validate config ──────────────────────────────────────────
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\n❌ SUPABASE_URL и SUPABASE_KEY не заданы в .env")
        print("   Добавьте их и повторите запуск.")
        sys.exit(1)

    project_ref = _extract_project_ref(SUPABASE_URL)
    table = FB_EVENTS_TABLE
    print(f"\n   Project: {project_ref}")
    print(f"   Table:   {table}")

    # ── Step 1: Check if table already exists ───────────────────
    print(f"\n[1] Checking if {table} table exists...")
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        exists = _check_table_exists_rest(client, table)
    except ImportError:
        print("    ⚠️  supabase SDK не установлен: pip install supabase")
        exists = False
        client = None

    if exists:
        print(f"    ✅ Table '{table}' already exists!")
        _verify_connection(client, table)
        print(f"\n✅ Ready! Run: python main.py --force")
        return

    print(f"    ⚠️  Table '{table}' not found — need to create it.")

    # ── Step 2: Try auto-creation via psycopg2 ──────────────────
    if SUPABASE_DB_PASSWORD:
        print(f"\n[2] Auto-creating table via psycopg2...")
        ok, info = _create_table_via_psycopg2(SUPABASE_DB_PASSWORD, project_ref, _CREATE_SQL)
        if ok:
            print(f"    ✅ Table '{table}' created successfully via {info}!")
            if client:
                _verify_connection(client, table)
            print(f"\n✅ Ready! Run: python main.py --force")
            return
        else:
            print(f"\n    ❌ Auto-creation failed: {info}")
            print("    Falling back to manual setup instructions...")
    else:
        print(f"\n[2] SUPABASE_DB_PASSWORD not set — skipping auto-creation.")
        print(   "    To enable auto-creation, add to .env:")
        print(   "    SUPABASE_DB_PASSWORD=your_database_password")
        print(   "    (find it: Supabase Dashboard → Settings → Database)")

    # ── Step 3: Print manual instructions ───────────────────────
    _print_manual_instructions(table)
    sys.exit(1)


def _verify_connection(client, table: str) -> None:
    """Quick connection test — count rows."""
    try:
        r = client.table(table).select("id", count="exact").execute()
        count = r.count if r.count is not None else len(r.data)
        print(f"    ✅ Connection OK — {count} rows in {table}")
    except Exception as e:
        print(f"    ⚠️  Connection check: {e}")


def _print_manual_instructions(table: str) -> None:
    print(f"\n{'─' * 65}")
    print(f"  MANUAL SETUP: Run this SQL in Supabase Dashboard")
    if DASHBOARD_URL:
        print(f"  URL: {DASHBOARD_URL}")
    print(f"{'─' * 65}")
    for line in _CREATE_SQL.splitlines():
        print(f"  {line}")
    print(f"{'─' * 65}")
    print()
    print("  After running the SQL, re-run this script to verify.")


if __name__ == "__main__":
    main()
