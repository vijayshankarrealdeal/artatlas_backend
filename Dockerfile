FROM python:3.11-slim

RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      unzip \
      curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN curl -fsSL "https://storage.googleapis.com/image_art/archive.zip" -o archive.zip \
 && mkdir -p /app/repository \
 && unzip archive.zip -d /app/repository \
 && rm archive.zip

# 2) Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
