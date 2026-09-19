FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# GDAL/GEOS/PROJ are required both by GeoDjango's PostGIS backend and by the
# ogr2ogr binary used to import uploaded shapefiles into PostGIS tables.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media \
    && chmod +x /app/entrypoint.sh \
    && sed -i 's/\r$//' /app/entrypoint.sh

# Container listens on 8000; host maps 8001:8000 in docker-compose.prod.yml
EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "600", "--access-logfile", "-", "--error-logfile", "-"]
