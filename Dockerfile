# Trio Coffee Shop Order API - production image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Don't copy .env or dev-only files if using .dockerignore

EXPOSE 8000

# Run migrations then start app (override CMD in compose for migration-only)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
