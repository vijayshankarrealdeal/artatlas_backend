FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Environment settings
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Expose port
EXPOSE 8080

# Run FastAPI app (update this line to match root-level main.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
