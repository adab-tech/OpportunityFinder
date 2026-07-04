FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

# Run as a non-root user; the app writes nothing outside the working dir
# (SQLite fallback needs write access to /app/backend).
RUN useradd --create-home appuser && chown -R appuser /app/backend
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
