import sys
import os

# Add apps/api to path so it can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from src.config.settings import get_settings
from src.repositories.alloydb import get_engine, close_connection
from src.repositories.scheme_repository import SchemeRepository
from sqlalchemy import text, inspect


def main():
    print("==================================================")
    print("      Navi Scheme - Database Connection Test      ")
    print("==================================================")
    
    settings = get_settings()
    print(f"[CONFIG] Database URL:      {settings.database_url or '(Not set - using AlloyDB fallback)'}")
    if not settings.database_url and settings.alloydb_instance_uri:
        print(f"[CONFIG] AlloyDB Instance:  {settings.alloydb_instance_uri}")
    print("--------------------------------------------------")
    print("[1/3] Initializing connection and tables...")

    try:
        # Initialize tables & default schemes if empty
        repo = SchemeRepository()
        repo.init_database()

        engine = get_engine()
        with engine.connect() as conn:
            print("[2/3] Executing ping query (SELECT 1)...")
            res = conn.execute(text("SELECT 1;")).fetchone()
            print("  ==> Success! Connected to database.")

            print("\n[3/3] Inspecting database tables and data...")
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print(f"  Available Tables: {tables}")

            for table in tables:
                columns = inspector.get_columns(table)
                col_names = [c["name"] for c in columns]
                print(f"\n  - Table '{table}': {len(columns)} columns ({', '.join(col_names[:5])}...)")
                
                try:
                    count_res = conn.execute(text(f'SELECT count(*) FROM "{table}"')).fetchone()
                    row_count = count_res[0] if count_res else 0
                    print(f"    Total records: {row_count}")

                    if row_count > 0:
                        sample_rows = conn.execute(text(f'SELECT id, slug, title, state, category FROM "{table}" LIMIT 3')).mappings().all()
                        print(f"    Sample entries:")
                        for idx, row in enumerate(sample_rows, 1):
                            print(f"      [{idx}] {row['title']} ({row['state']} | {row['category']})")
                except Exception as q_err:
                    print(f"    Could not query rows: {q_err}")

            print("\n==================================================")
            print("  DATABASE TEST & DATA VERIFICATION: ALL PASSED   ")
            print("==================================================")

    except Exception as e:
        err_name = type(e).__name__
        err_msg = str(e)
        print(f"\n[FAILED] Connection error: {err_name}", file=sys.stderr)
        print(f"Details: {err_msg}\n", file=sys.stderr)
        sys.exit(1)
    finally:
        close_connection()


if __name__ == "__main__":
    main()
