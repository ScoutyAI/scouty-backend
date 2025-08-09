import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import csv

def create_app():
    app = Flask(__name__)

    # Config: default to /var/data/submissions.csv so it works on Render disks,
    # but allow override via env CSV_PATH.
    app.config["CSV_PATH"] = os.environ.get("CSV_PATH", "/var/data/submissions.csv")
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")

    # Allow CORS for submit endpoint (comma-separated origins allowed, or *)
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(app, resources={r"/submit-form": {"origins": origins}})

    HEADER = [
        "timestamp",
        "first_name","last_name","email","company_name",
        "phone_code","phone_number","job_title","website","linkedin_profile",
        "categories","find_suppliers","repeat_orders","challenge","ai_used","ai_tools",
        "rfqs","rfq_frustration","workflow_confidence","rfq_worth","landed_cost",
        "supplier_comm","supplier_locations","platforms","ai_wish","trust_ai",
        "mvp_review","follow_up","hear_about_us"
    ]

    def ensure_csv():
        p = app.config["CSV_PATH"]
        # Make sure parent directory exists (e.g., /var/data)
        parent = os.path.dirname(p)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        # Create file with header if it doesn't exist
        if not os.path.exists(p):
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(HEADER)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status":"ok"}), 200

    @app.route("/submit-form", methods=["POST"])
    def submit_form():
        ensure_csv()
        # Accept either form-encoded or JSON payloads
        if request.form:
            data = request.form.to_dict()
        else:
            data = request.get_json(silent=True) or {}
        row = [datetime.utcnow().isoformat() + "Z"] + [data.get(k, "") for k in HEADER[1:]]
        with open(app.config["CSV_PATH"], "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
        return jsonify({"message": "ok"}), 200

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
