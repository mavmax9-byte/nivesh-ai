FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY backend/ ./
RUN uv pip install --system --no-cache -e .

CMD ["celery", "-A", "nivesh.core.celery_app.celery_app", "worker", "--loglevel=INFO"]
