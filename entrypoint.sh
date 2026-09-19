#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PYEOF'
import os
import sys
import time

import environ
import psycopg2

env = environ.Env()
# Docker Compose env vars take precedence over values in .env
environ.Env.read_env("/app/.env", overwrite=False)
db = env.db_url("DATABASE_URL")

for attempt in range(60):
    try:
        psycopg2.connect(
            dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"],
            host=db["HOST"], port=db["PORT"],
        ).close()
        break
    except psycopg2.OperationalError:
        time.sleep(1)
else:
    sys.exit("Database never became available")
PYEOF

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
