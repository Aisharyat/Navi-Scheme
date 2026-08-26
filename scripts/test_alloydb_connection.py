import sys
import os

# Add apps/api to path so it can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from src.config.settings import get_settings
from src.repositories.alloydb import get_engine, close_connection
from sqlalchemy import text, inspect


def main():
    print("==================================================")
    print("      Navi Scheme - AlloyDB Connection Test       ")
    print("==================================================")
    
    settings = get_settings()
    print(f"[CONFIG] Instance URI:      {settings.alloydb_instance_uri or '(Direct host connection)'}")
    print(f"[CONFIG] Database:          {settings.alloydb_database}")
    print(f"[CONFIG] User:              {settings.alloydb_user}")
    print(f"[CONFIG] IP Type:           {settings.alloydb_ip_type}")
    print(f"[CONFIG] IAM Auth:          {settings.alloydb_enable_iam_auth}")
    print(f"[CONFIG] Credentials File:  {settings.google_application_credentials or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', 'Not configured')}")
    if settings.alloydb_host:
        print(f"[CONFIG] Direct Host:       {settings.alloydb_host}:{settings.alloydb_port}")
    print("--------------------------------------------------")
    print("[1/3] Initializing connection...")

    try:
        engine = get_engine()
        with engine.connect() as conn:
            print("[2/3] Executing ping query (SELECT 1)...")
            res = conn.execute(text("SELECT 1;")).fetchone()
            print("  ==> Success! Connected to AlloyDB.")

            print("\n[3/3] Fetching database metadata & tables...")
            version_row = conn.execute(text("SELECT version();")).fetchone()
            if version_row:
                print(f"  PostgreSQL Version: {version_row[0]}")

            inspector = inspect(engine)
            schemas = inspector.get_schema_names()
            print(f"  Available Schemas:  {', '.join(schemas)}")

            for schema in ["public"] + [s for s in schemas if s not in ("public", "information_schema", "pg_catalog")]:
                tables = inspector.get_table_names(schema=schema)
                print(f"\n  [Schema '{schema}'] Tables ({len(tables)}):")
                if not tables:
                    print("    (No tables found in this schema)")
                for table in tables:
                    columns = inspector.get_columns(table, schema=schema)
                    col_str = ", ".join([f"{c['name']} ({c['type']})" for c in columns])
                    print(f"    - Table '{table}': {col_str}")
                    
                    try:
                        count_res = conn.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).fetchone()
                        row_count = count_res[0] if count_res else 0
                        print(f"      Total rows: {row_count}")

                        if row_count > 0:
                            sample_rows = conn.execute(text(f'SELECT * FROM "{schema}"."{table}" LIMIT 3')).mappings().all()
                            print(f"      Sample records (up to 3):")
                            for idx, row in enumerate(sample_rows, 1):
                                print(f"        Row {idx}: {dict(row)}")
                    except Exception as q_err:
                        print(f"      Could not query rows: {q_err}")

            print("\n==================================================")
            print("  CONNECTION & DATA FETCH TEST: ALL PASSED")
            print("==================================================")

    except Exception as e:
        err_name = type(e).__name__
        err_msg = str(e)
        print(f"\n[FAILED] Connection error: {err_name}", file=sys.stderr)
        print(f"Details: {err_msg}\n", file=sys.stderr)

        print("----------------- Troubleshooting -----------------", file=sys.stderr)
        if "DefaultCredentialsError" in err_name or "credentials" in err_msg.lower():
            print("Hint: Google Cloud credentials are required by the AlloyDB connector.", file=sys.stderr)
            print("1. Service Account Key: Place your GCP service account JSON key file in apps/api/ (e.g. key.json)", file=sys.stderr)
            print("   and add GOOGLE_APPLICATION_CREDENTIALS=key.json to apps/api/.env", file=sys.stderr)
            print("2. Google Cloud SDK: Run 'gcloud auth application-default login'", file=sys.stderr)
        elif "timed out" in err_msg.lower() or "unreachable" in err_msg.lower() or "connection refused" in err_msg.lower():
            print("Hint: Network connectivity issue.", file=sys.stderr)
            print("1. If connecting from your local machine outside GCP VPC, ensure Public IP is enabled on the instance and set ALLOYDB_IP_TYPE=PUBLIC in .env.", file=sys.stderr)
            print("2. If using AlloyDB Auth Proxy, run the proxy and specify ALLOYDB_HOST=127.0.0.1 in .env.", file=sys.stderr)
        elif "password" in err_msg.lower() or "authentication" in err_msg.lower():
            print("Hint: Check ALLOYDB_USER and ALLOYDB_PASSWORD in apps/api/.env.", file=sys.stderr)
        print("---------------------------------------------------", file=sys.stderr)
        sys.exit(1)
    finally:
        close_connection()


if __name__ == "__main__":
    main()

