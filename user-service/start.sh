#!/bin/sh
set -e

# Migrations are NOT run here — same decoupled pattern as auth-service.
# Run explicitly:
#   docker compose exec user-service alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload