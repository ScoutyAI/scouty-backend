import os
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

import psycopg2


# =========================
# CONFIG
# =========================

HEADER = [
    "timestamp",
    "first_name", "last_name", "email", "company_name",
    "phone_code", "phone_number", "job_title", "website", "linkedin_profile",
    "categories", "find_suppliers", "repeat_orders", "challenge", "ai_used", "ai_tools",
    "rfqs", "rfq_frustration", "workflow_confidence", "rfq_worth", "landed_cost",
    "supplier_comm", "supplier_locations", "platforms", "ai_wish", "trust_ai",
    "mvp_review", "follow_up", "hear_about_us"
]

# Optional: if your frontend sends a unique ID per submission, we can prevent duplicates.
OPTIONAL_ID_FIELD = "submission_id"


def _normalized_db_url() -> str:
    """
    Render Postgres connections commonly require SSL for external connections.
    Adding sslmode=require is safe.
    """
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
    Creates the table + index if they don't exist.
    Called by /init and /submit-form so the app always self-heals.
    """

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS quiz_submissions (
        id BIGSERIAL PRIMARY KEY,
        submission_id TEXT UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        timestamp TEXT,

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

    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_quiz_submissions_created_at
    ON quiz_submissions(created_at DESC);
    """

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            cur.execute(create_index_sql)
        conn.commit()


def create_app():
    app = Flask(__name__)

    # CORS
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").strip()
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(
        app,
        resources={
            r"/submit-form": {"origins": origins},
            r"/health": {"origins": origins},
            r"/init": {"origins": origins},
            r"/reset": {"origins": origins},
        },
    )

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
        """
        SAFE init: does NOT delete data.
        It only ensures the table exists (and index exists).
        """
        _ensure_table()
        return jsonify({"ok": True, "message": "table ready", "table": "quiz_submissions"}), 200

    @app.route("/reset", methods=["POST"])
    def reset():
        """
        DANGEROUS: drops the table then recreates it.
        Protected by a secret so random visitors can't wipe your DB.

        Set env var: RESET_TOKEN = some-long-random-string
        Then call:
          POST /reset
          Header: X-Reset-Token: <RESET_TOKEN>
        """
        expected = os.environ.get("RESET_TOKEN", "").strip()
        provided = request.headers.get("X-Reset-Token", "").strip()

        if not expected:
            return jsonify({"ok": False, "error": "RESET_TOKEN is not set on server"}), 400
        if provided != expected:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS quiz_submissions;")
            conn.commit()

        _ensure_table()
        return jsonify({"ok": True, "message": "table reset and ready", "table": "quiz_submissions"}), 200

    @app.route("/submit-form", methods=["POST"])
    def submit_form():
        _ensure_table()

        # Accept either form-encoded or JSON payloads
        if request.form:
            data = request.form.to_dict()
        else:
            data = request.get_json(silent=True) or {}

        # Optional honeypot for bots (if your HTML sends it)
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
            ON CONFLICT (submission_id) DO NOTHING;
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
