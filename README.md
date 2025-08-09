
# Scouty AI Form Backend

Simple Flask backend that accepts POSTs at `/submit-form`, appends them to a CSV, and returns JSON.

## Local dev
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export ALLOWED_ORIGINS="*"
python app.py
# Open http://localhost:8000/health
```

## Deploy (Render, Railway, Fly.io, Heroku)
- Create a new **Web Service** from this repo/folder.
- Build command: *(none)*
- Start command (if asked): `gunicorn app:app --workers 2 --threads 4 --timeout 120`
- Env vars:
  - `ALLOWED_ORIGINS` — e.g. `https://yourdomain.com, https://www.yourdomain.com`
  - `CSV_PATH` — optional path for the CSV file (defaults to `submissions.csv`)
- After deploy, verify `GET /health` returns `{ "status": "ok" }`.

## Endpoint
Your form should POST to: `https://<your-service-domain>/submit-form`
