# GeoLayers — Shapefile Layer Uploading & Mapping Platform

A Django + Django REST Framework application for uploading shapefiles, turning
each one into its own PostGIS table, styling/labeling it, sharing it with
other users, and composing shared layers into savable, shareable web maps
rendered with Mapbox GL JS and tiled by [Martin](https://martin.maplibre.org/).

## Stack

- **Django 5** — server-rendered templates for the app shell (login, dashboard,
  layer manager, map builder)
- **Django REST Framework** + **SimpleJWT** — JSON API secured with short-lived
  JWT access tokens and rotating refresh tokens (auto-refreshed by the frontend)
- **PostgreSQL + PostGIS** — stores app metadata *and* the dynamically created
  per-layer geometry tables
- **GDAL/`ogr2ogr`** — imports each uploaded shapefile into its own PostGIS table
- **Martin** — publishes `layers_data.layer_*` tables as vector tiles (catalog
  reloads every few seconds so new uploads are tile-ready quickly)
- **Mapbox GL JS** — basemap + vector tile rendering in the browser

## Architecture

```
apps/
  accounts/  Custom User model, Role/Permission management, JWT auth endpoints
  layers/    LayerInfo metadata, shapefile -> PostGIS import pipeline, sharing
  maps/      MapProject (saved layer compositions), ordering, sharing
  core/      Template views (dashboard, layer manager, map builder) + nav shell
templates/   Django templates (base shell, login, dashboard, layers, maps)
static/      Vanilla JS/CSS frontend (JWT wrapper, layer manager, map builder)
martin/      Entrypoint that generates Martin's runtime config for Compose
```

### How a shapefile becomes a map layer

1. User uploads a `.zip` containing `.shp/.shx/.dbf/.prj` via the Layers page.
2. `apps/layers/services.py` extracts it, runs `ogr2ogr` to import it into a
   brand-new table `layers_data.layer_<uuid>` (reprojected to EPSG:4326).
3. The table's geometry type, feature count, bounding box and attribute schema
   are introspected from PostGIS and stored on a `LayerInfo` row (the metadata
   record — this is where style/label config and sharing live).
4. Martin publishes that table as vector tiles at
   `MARTIN_TILE_SERVER_URL/layer_<uuid>/{z}/{x}/{y}`. The upload API waits
   until Martin's catalog lists the new source before returning.
5. The Layers **Share** dialog exposes a live XYZ template
   (`xyz_url`, `source_layer`, `suggested_geometry` on the API) for any
   external client that can consume XYZ / MVT tiles.
6. The map builder adds it as a `vector` source in Mapbox GL JS using that URL
   and styles it (fill/line/circle + optional text labels) from `LayerInfo.style`
   / `LayerInfo.label_config`, then fits the viewport to layer bounds.

### Auth model

Login (`POST /api/auth/login/`) both establishes a Django session (so
server-rendered pages know who's signed in) **and** returns a JWT
access/refresh pair, which the frontend (`static/js/auth.js`) stores and
attaches to every API call. On a `401` it silently calls
`/api/auth/token/refresh/` once and retries. Refresh tokens rotate and old
ones are blacklisted (`rest_framework_simplejwt.token_blacklist`).

### Roles & permissions

`accounts.Role` wraps Django's built-in `Permission` objects so admins can
compose named roles (e.g. "GIS Editor") from fine-grained permissions,
including the custom `layers.share_layerinfo` / `maps.share_mapproject`
permissions declared on those models. Manage roles at `/admin/` or via the
`/api/auth/roles/` endpoint (staff-only by default).

Layer/map access itself is owner + explicit-share based:
- **Owner** — full control (edit, delete, share).
- **Shared — edit** — can restyle/relabel a layer or change a map's layer
  composition, but can't delete or re-share it.
- **Shared — view** — read-only.

## Local development (Docker)

```bash
cp .env.example .env
# edit .env: set MAPBOX_ACCESS_TOKEN (and secrets as needed)

docker compose up --build
```

Compose starts **db**, **web**, and **martin** together:

| Service | Host URL / port |
| --- | --- |
| App (UI + API) | http://localhost:8000 |
| Martin tiles | http://localhost:3000 |
| PostGIS | localhost:5432 |

**Cost-lean Martin defaults** (see `martin/entrypoint.sh`):

- Tile cache **64MB** (not Martin’s ~512MB default)
- **2** HTTP workers (not 8)
- Postgres pool **5** (not 20)
- Catalog refresh **on upload/delete only** (Django restarts Martin via `docker.sock`)
- `auto_bounds: skip` (map fitBounds uses Django layer bounds)
- Soft `mem_limit: 256m` on the Martin container

```bash
docker compose exec web python manage.py createsuperuser
```

## Production (Docker)

Use `docker-compose.prod.yml` (project name `geolayers`):

| Service | Host port |
| --- | --- |
| App | **8001** → container 8000 |
| Martin | **3002** → container 3000 |
| PostGIS | **5435** → container 5432 |

```bash
cd /home/layeruploading_martintileserver   # or your deploy path
cp .env.example .env   # first time only; then edit for production
# Required: DEBUG=False, SECRET_KEY, ALLOWED_HOSTS, POSTGRES_PASSWORD,
# MAPBOX_ACCESS_TOKEN, MARTIN_TILE_SERVER_URL=http://<public-host>:3002

docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Migrations and `collectstatic` run on web container start (`entrypoint.sh`).

```bash
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml up -d --build web martin
docker compose -f docker-compose.prod.yml down      # keeps volumes
docker compose -f docker-compose.prod.yml down -v   # wipes db + media
```

## Local development (without Docker)

Requirements: Python 3.12, PostgreSQL + PostGIS, GDAL (`ogr2ogr` on `PATH`),
and Martin.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # point DATABASE_URL at local PostGIS; set MARTIN_INTERNAL_URL if needed

python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

Run Martin separately, e.g.:

```bash
# edit connection_string in martin/config.example.yaml first
martin --config martin/config.example.yaml
# or:  martin postgresql://gis_user:gis_password@localhost:5432/gis_app
```

## Key environment variables (`.env`)

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostGIS connection string for Django |
| `MAPBOX_ACCESS_TOKEN` | Basemap token for Mapbox GL JS |
| `MARTIN_TILE_SERVER_URL` | Browser-facing Martin base URL |
| `MARTIN_INTERNAL_URL` | Django→Martin URL inside Docker (default `http://martin:3000`) |
| `MARTIN_READY_TIMEOUT` | Seconds to wait for Martin catalog after upload (default 90) |
| `MARTIN_DOCKER_CONTAINER` | Container name for on-demand restart (compose sets `geolayers-martin`) |
| `OGR2OGR_PATH` | Path to `ogr2ogr` (default `ogr2ogr`) |
| `ACCESS_TOKEN_LIFETIME_MINUTES` / `REFRESH_TOKEN_LIFETIME_DAYS` | JWT lifetimes |
| `POSTGRES_*` | Used by prod compose for the `db` service |

## API overview

| Endpoint | Notes |
| --- | --- |
| `POST /api/auth/register/`, `/login/`, `/token/refresh/`, `/logout/` | JWT auth |
| `GET/PATCH /api/auth/me/` | Current user profile |
| `GET /api/auth/users/?search=` | User directory for share pickers |
| `CRUD /api/auth/roles/` | Role & permission management |
| `CRUD /api/layers/`, `POST /api/layers/{id}/share/`, `/unshare/` | Layer upload (multipart), styling, sharing |
| `CRUD /api/maps/`, `GET/POST /api/maps/{id}/layers/`, `PATCH/DELETE /api/maps/{id}/layers/{map_layer_id}/`, `POST /api/maps/{id}/reorder/`, `/share/`, `/unshare/` | Map composition & sharing |
