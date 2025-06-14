# ---- build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Create a virtualenv path for installation
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage ----
FROM python:3.11-slim

# Add a non-root user
RUN adduser --disabled-password --gecos '' appuser
USER appuser

ENV PATH="/home/appuser/.local/bin:/install/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /install

# Copy your app
COPY --chown=appuser:appuser app/ ./app/

# Expose FastAPI port
EXPOSE 8000

# Start the app using Gunicorn and Uvicorn workers
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:${PORT}", "app.main:app"]