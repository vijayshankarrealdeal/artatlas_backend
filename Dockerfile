# ---- build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- runtime stage ----
FROM python:3.11-slim

# Create an unprivileged user for security
RUN adduser --disabled-password --gecos '' appuser
USER appuser

ENV PATH="${PATH}:/home/appuser/.local/bin" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /home/appuser/.local /home/appuser/.local
COPY --chown=appuser:appuser app/ ./app/

# Expose the port FastAPI listens on
EXPOSE 8000

# Gunicorn w/ Uvicorn workers for multiple processes
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "app.main:app"]
