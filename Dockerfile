FROM python:3.11-slim

RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      unzip \
      curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app


# 2) Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN ls -lR /app

RUN curl -fsSL "https://storage.googleapis.com/image_art/archive.zip" -o archive.zip \
 && mkdir -p /app/openai/clip-vit-base-patch32 \
 && unzip -j archive.zip -d /app/openai/clip-vit-base-patch32 \
 && rm archive.zip

RUN ls -l /app/openai/clip-vit-base-patch32

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
