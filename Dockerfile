# Ekosight CEO Agent — container image for Google Cloud Run.
#
# The image keeps the repo's backend/ + frontend/ layout because the app
# resolves the dashboard at ../../frontend relative to app/main.py.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# App code + served frontend (preserve relative layout).
COPY backend /app/backend
COPY frontend /app/frontend

WORKDIR /app/backend

# Cloud Run sets $PORT (default 8080). Bind 0.0.0.0 so the platform can reach it.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
