import os
import json
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

import psycopg2
from psycopg2.extras import Json


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
    "mvp_review", "follow_up", "hear_about_us",
]

OPTIONAL_ID_FIELD = "submission_id"


def _normalized_db_url() -> str:
    """
    Render Postgres often requires SSL for external connections.
    Adding sslmode=require is safe even when internal connections work without it.
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
    Creates the table if it doesn't exist, and ensures index exists.
    Also creates raw_payload JSONB column to store full submission payload.
    Safe to call repeatedly.
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
        hear_about_us TEXT,

        raw_payload JSONB
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


def _log_request_summary(prefix: str = "REQ"):
    """
    Logs what actually reached Flask. Check Render logs.
    """
    try:
        raw = request.get_data(cache=True) or b""
        print(
            f"{prefix} path={request.path} "
            f"ct={request.content_type} "
            f"len={len(raw)} "
            f"form_keys={list(request.form.keys())} "
            f"args_keys={list(request.args.keys())}"
        )
    except Exception as e:
        print(f"{prefix} logging_error={e}")


def _read_payload() -> tuple[dict, str]:
    """
    Robustly read payload from:
      - multipart/form-data (FormData)
      - application/x-www-form-urlencoded
      - application/json
      - fallback: try parse raw body as JSON
    Returns: (data_dict, mode)
    """
    # 1) Form fields (works for multipart/form-data and x-www-form-urlencoded)
    if request.form and len(request.form.keys()) > 0:
        return request.form.to_dict(flat=True), "form"

    # 2) JSON body (fetch with Content-Type: application/json)
    js = request.get_json(silent=True)
    if isinstance(js, dict) and js:
        return js, "json"

    # 3) Fallback: raw body parse as JSON (some clients forget headers)
    raw = (request.get_data(cache=True) or b"").decode("utf-8", errors="ignore").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed, "raw_json"
            return {"_raw": raw, "_parsed_non_dict": parsed}, "raw_non_dict"
        except Exception:
            return {"_raw": raw}, "raw_text"

    # 4) Nothing received
    return {}, "empty"


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
            r"/latest": {"origins": origins},
            r"/debug-receive": {"origins": origins},
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
        Dev/ops helper endpoint.
        In production it is DISABLED (set ENV=production in Render env vars).
        If enabled, it ensures table exists (does NOT drop rows).
        """
        if os.environ.get("ENV", "").lower() == "production":
            return jsonify({"ok": False, "error": "init is disabled in production"}), 403

        _ensure_table()
        return jsonify({"ok": True, "message": "table ready", "table": "quiz_submissions"}), 200

    @app.route("/debug-receive", methods=["POST"])
    def debug_receive():
        """
        Debug endpoint to see exactly what Flask receives.
        Call it from your frontend temporarily if needed.
        """
        _log_request_summary("DEBUG")
        data, mode = _read_payload()
        return jsonify({
            "ok": True,
            "mode": mode,
            "content_type": request.content_type,
            "form_keys": list(request.form.keys()),
            "json_present": isinstance(request.get_json(silent=True), dict),
            "raw_len": len(request.get_data(cache=True) or b""),
            "received_keys": list(data.keys()),
            "received_sample": {k: data.get(k) for k in list(data.keys())[:10]},
        }), 200

    @app.route("/submit-form", methods=["POST"])
    def submit_form():
        _ensure_table()

        _log_request_summary("SUBMIT")
        data, mode = _read_payload()

        # Honeypot / anti-spam support (if your HTML sends it)
        honeypot = (data.get("website_hp") or data.get("hp") or "").strip()
        if honeypot:
            return jsonify({"message": "ok"}), 200

        # If we literally received nothing, return an error so you notice.
        # (If you prefer silent success, change to 200.)
        if not data:
            return jsonify({
                "ok": False,
                "error": "empty_payload",
                "hint": "Your frontend is not sending fields (often missing name=..., disabled inputs, or wrong Content-Type).",
                "content_type": request.content_type,
                "mode": mode,
            }), 400

        # Timestamp (keep your previous behavior)
        timestamp_str = (data.get("timestamp") or "").strip() or (datetime.utcnow().isoformat() + "Z")

        # Optional: strict dedupe if client sends submission_id
        submission_id = (data.get(OPTIONAL_ID_FIELD) or "").strip() or None

        # Map known columns
        cols = ["submission_id", "timestamp"] + HEADER[1:] + ["raw_payload"]
        values = [submission_id, timestamp_str] + [data.get(k, "") for k in HEADER[1:]] + [Json(data)]

        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)

        # IMPORTANT:
        # Only apply ON CONFLICT if submission_id is present.
        # If submission_id is None, the unique constraint doesn't conflict, but this logic is clearer
        # and prevents "accidental do-nothing" behavior if you later change how submission_id is sent.
        if submission_id:
            sql = f"""
                INSERT INTO quiz_submissions ({col_list})
                VALUES ({placeholders})
                ON CONFLICT (submission_id) DO NOTHING;
            """
        else:
            sql = f"""
                INSERT INTO quiz_submissions ({col_list})
                VALUES ({placeholders});
            """

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()

        return jsonify({"message": "ok", "mode": mode, "received_keys": len(data.keys())}), 200

    @app.route("/latest", methods=["GET"])
    def latest():
        """
        Quick sanity-check endpoint: returns the most recent submission.
        Protect it with a simple token if you want (optional):
          - Set env var LATEST_TOKEN, then call /latest?token=...
        """
        token_required = os.environ.get("LATEST_TOKEN", "").strip()
        if token_required:
            token = (request.args.get("token") or "").strip()
            if token != token_required:
                return jsonify({"ok": False, "error": "unauthorized"}), 401

        _ensure_table()

        sql = """
            SELECT
                id,
                submission_id,
                created_at,
                timestamp,
                first_name,
                last_name,
                email,
                company_name,
                raw_payload
            FROM quiz_submissions
            ORDER BY created_at DESC
            LIMIT 1;
        """

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()

        if not row:
            return jsonify({"ok": True, "latest": None}), 200

        latest_row = {
            "id": row[0],
            "submission_id": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
            "timestamp": row[3],
            "first_name": row[4],
            "last_name": row[5],
            "email": row[6],
            "company_name": row[7],
            "raw_payload": row[8],  # helpful for debugging what arrived
        }

        return jsonify({"ok": True, "latest": latest_row}), 200

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
