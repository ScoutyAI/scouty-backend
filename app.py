import os
import csv
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

# Postgres driver
import psycopg2
from psycopg2.extras import RealDictCursor


HEADER = [
    "timestamp",
    "first_name","last_name","email","company_name",
    "phone_code","phone_number","job_title","website","linkedin_profile",
    "categories","find_suppliers","repeat_orders","challenge","ai_used","ai_tools",
    "rfqs","rfq_frustration","workflow_confidence","rfq_worth","landed_cost",
    "supplier_comm","supplier_locations","platforms","ai_wish","trust_ai",
    "mvp_review","follow_up","hear_about_us"
]

TABLE_NAME = "quiz_submissions"


def create_app():
    app = Flask(__name__)

    # CSV fallback (Render Disk)
    app.config["CSV_PATH"] = os.environ.get("CSV_PATH", "/var/data/submissions.csv")

    # Postgres (Render managed DB)
    app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL")  # set in Render env vars

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(app, resources={r"/submit-form": {"origins": origins}})

    def now_utc_iso():
        return datetime.now(timezone.utc).isoformat()

    # ---------- CSV helpers ----------
    def ensure_csv():
        p = app.config["CSV_PATH"]
        parent = os.path.dirname(p)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        if not os.path.exists(p):
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(HEADER)

    def write_csv(data: dict):
        ensure_csv()
        row = [now_utc_iso()] + [data.get(k, "") for k in HEADER[1:]]
        with open(app.config["CSV_PATH"], "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    # ---------- Postgres helpers ----------
    def pg_conn():
        # Render provides DATABASE_URL like: postgresql://user:pass@host/db
        return psycopg2.connect(app.config["DATABASE_URL"], sslmode="require")

    def ensure_table():
        # Create table if not exists
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            company_name TEXT,
            phone_code TEXT,
            phone_number TEXT,
            job_title TEXT,
            website TEXT,
            linkedin_profile TEXT,
            categories TEXT,
            find_suppliers TEXT,
            repeat_orders TEXT,
            challenge TEXT,
            ai_used TEXT,
            ai_tools TEXT,
            rfqs TEXT,
            rfq_frustration TEXT,
            workflow_confidence TEXT,
            rfq_worth TEXT,
            landed_cost TEXT,
            supplier_comm TEXT,
            supplier_locations TEXT,
            platforms TEXT,
            ai_wish TEXT,
            trust_ai TEXT,
            mvp_review TEXT,
            follow_up TEXT,
            hear_about_us TEXT
        );
        """
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)

    def insert_row(data: dict):
        ensure_table()
        cols = HEADER[:]  # includes "timestamp"
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        sql = f"INSERT INTO {TABLE_NAME} ({col_sql}) VALUES ({placeholders});"

        values = [datetime.now(timezone.utc)] + [data.get(k, "") for k in HEADER[1:]]

        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)

    # ---------- Routes ----------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "db_configured": bool(app.config["DATABASE_URL"])
        }), 200

    @app.route("/init", methods=["GET"])
    def init_db():
        if not app.config["DATABASE_URL"]:
            return jsonify({"ok": False, "error": "DATABASE_URL not set"}), 400
        ensure_table()
        return jsonify({"ok": True, "message": "table ready", "table": TABLE_NAME}), 200

    @app.route("/submit-form", methods=["POST"])
    def submit_form():
        # Accept either form-encoded or JSON
        if request.form:
            data = request.form.to_dict()
        else:
            data = request.get_json(silent=True) or {}

        # Prefer Postgres if available, else CSV
        if app.config["DATABASE_URL"]:
            insert_row(data)
            return jsonify({"message": "ok", "stored_in": "postgres"}), 200
        else:
            write_csv(data)
            return jsonify({"message": "ok", "stored_in": "csv"}), 200

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
