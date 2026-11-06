# Data Cleaner Studio (web) — container image
# Base: slim Python 3.12. No build tools, no curl — the HEALTHCHECK below
# uses only the standard library, so it works on this image as-is.
FROM python:3.12-slim

# Keep Python from writing .pyc files and from buffering stdout, so
# Streamlit + scheduler logs show up immediately in `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first (cached layer; rebuilds stay fast when only
# app code changes).
# NOTE: requirements.txt is owned by the foundation agent and includes
# supabase (Supabase Auth + Postgres + Storage) alongside
# streamlit/pandas/altair/openpyxl. Do NOT add packages here — edit
# requirements.txt instead. If supabase is missing from
# requirements.txt, Supabase auth is unavailable and the app runs in
# LOCAL MODE (SQLite accounts) until it is added.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project (app.py, engine.py, feat_*.py, scheduler.py, ...).
# User data is NOT baked into the image — it lives in the /app/data volume.
COPY . .

# Streamlit's internal health endpoint. Uses urllib from the standard
# library because python:3.12-slim ships no curl/wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5)"

EXPOSE 8501

# Per-user files and the scheduler registry/log live here. On a VPS this is
# a named volume or a host bind-mount — never part of the image, so
# redeploys and container restarts do not wipe user data.
VOLUME ["/app/data"]

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
