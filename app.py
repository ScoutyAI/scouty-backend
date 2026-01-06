import os
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

import psycopg2


HEADER = [
    "timestamp",
    "first_name", "last_name", "email", "company_name",
    "phone_code", "phone_number", "job_title", "website", "linkedin_profile",
    "categories", "find_suppliers", "repeat_orders", "challenge", "ai_used", "ai_tools",
    "rfqs", "rfq_frustration", "workflow_confidence", "rfq_worth", "landed_cost",
    "supplier_comm", "supplier_locations", "platforms", "ai_wish", "trust_ai",
    "mvp_review", "follow_up", "hear_about_us"
]

OPTIONAL_ID_FIELD = "submission_id"


def _normalized_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return ""
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _connect():
    db_url = _normalized_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL env var is missing.")
    return psycopg2.connect(db_url)


def _ensure_table():
    """
    Idempotent schema setup + migration:
    - Create table if missing
    - Add missing columns if table already exists with old schema
    - Create indexes afterwards (only after created_at exists)
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            # 1) Create base table (minimal)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quiz_submissions (
                    id BIGSERIAL PRIMARY KEY
                );
            """)

            # 2) Add columns safely (MIGRATION)
            cur.execute("ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS submission_id TEXT;")
            cur.execute("ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();")
            cur.execute("ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS timestamp TEXT;")

            # Add the rest of your fields
            for col in HEADER[1:]:
                cur.execute(f"ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS {col} TEXT;")

            # 3) Unique index for submission_id (dedupe only when provided)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_quiz_submissions_submission_id
                ON quiz_submissions(submission_id)
                WHERE submission_id IS NOT NULL;
            """)

            # 4) Now it's safe to create created_at index
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_quiz_submissions_created_at
                ON quiz_submissions(created_at DESC);
            """)

        conn.commit()


def create_app():
    app = Flask(__name__)

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").strip()
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(app, resources={r"/*": {"origins": origins}})

    @app.route("/health", methods=["GET"])
    def health():
        db_url_present = bool(os.environ.get("DATABASE_URL", "").strip())
        db_ok = False

        if db_url_present:
            try:
                with _connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                db_ok = True
            except Exception:
                db_ok = False

        return jsonify({"status": "ok", "db_configured": db_url_present, "db_ok": db_ok}), 200

    @app.route("/init", methods=["GET"])
    def init():
        # does NOT drop anything, just ensures schema exists
        _ensure_table()
        return jsonify({"ok": True, "message": "table ready", "table": "quiz_submissions"}), 200

    @app.route("/reset", methods=["GET"])
    def reset():
        # Use this only if you want to nuke and recreate the table
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS quiz_submissions;")
            conn.commit()

        _ensure_table()
        return jsonify({"ok": True, "message": "table DROPPED and recreated", "table": "quiz_submissions"}), 200

    @app.route("/submit-form", methods=["POST"])
    def submit_form():
        _ensure_table()

        data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})

        # Optional honeypot
        honeypot = (data.get("website_hp") or data.get("hp") or "").strip()
        if honeypot:
            return jsonify({"message": "ok"}), 200

        timestamp_str = data.get("timestamp") or (datetime.utcnow().isoformat() + "Z")
        submission_id = (data.get(OPTIONAL_ID_FIELD) or "").strip() or None

        cols = ["submission_id", "timestamp"] + HEADER[1:]
        values = [submission_id, timestamp_str] + [data.get(k, "") for k in HEADER[1:]]

        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)

        sql = f"""
            INSERT INTO quiz_submissions ({col_list})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING;
        """

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()

        return jsonify({"message": "ok"}), 200

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
