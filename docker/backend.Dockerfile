FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY backend/ ./
RUN uv pip install --system --no-cache -e .

EXPOSE 8000

CMD ["uvicorn", "nivesh.main:app", "--host", "0.0.0.0", "--port", "8000"]
