FROM python:3.12-slim

WORKDIR /app

# System dependencies for asyncua, psycopg2, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000 4840
