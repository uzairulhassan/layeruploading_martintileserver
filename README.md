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
- **Martin** — auto-discovers every PostGIS table with a geometry column and
  serves it as vector tiles, no manual tile-source configuration required
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
```

### How a shapefile becomes a map layer

1. User uploads a `.zip` containing `.shp/.shx/.dbf/.prj` via the Layers page.
2. `apps/layers/services.py` extracts it, runs `ogr2ogr` to import it into a
   brand-new table `layers_data.layer_<uuid>` (reprojected to EPSG:4326).
3. The table's geometry type, feature count, bounding box and attribute schema
   are introspected from PostGIS and stored on a `LayerInfo` row (the metadata
   record — this is where style/label config and sharing live).
4. Martin, running against the same database, automatically publishes that
   table as vector tiles at `MARTIN_TILE_SERVER_URL/layer_<uuid>/{z}/{x}/{y}` —
   no registration step needed.
5. The Layers page **XYZ link** action exposes a shareable XYZ template plus a
   GeoTrak import package (`xyz_url`, `source_layer`, `suggested_geometry` on
   the API) so external MapLibre clients can consume the same tiles.
6. The map builder adds it as a `vector` source in Mapbox GL JS using that URL
   and styles it (fill/line/circle + optional text labels) from `LayerInfo.style`
   / `LayerInfo.label_config`.

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
# edit .env: set MAPBOX_ACCESS_TOKEN and MARTIN_TILE_SERVER_URL

docker compose up --build
```

`docker-compose.yml` only starts `db` and `web` — Martin runs separately
(its own binary/container/service) against the same database. Point
`MARTIN_TILE_SERVER_URL` in `.env` at wherever that instance is reachable.
See `martin/config.example.yaml` if you'd rather pin it to an explicit config
instead of Martin's default auto-discovery (any spatial table, including
each new `layers_data.layer_<uuid>` table, is served automatically either way).

- App: http://localhost:6000
- Create an admin user: `docker compose exec web python manage.py createsuperuser`

## Server deployment (Docker)

The app is served on **port 6000** (see `Dockerfile` / `docker-compose.yml`).
This compose file only manages `db` and `web` — Martin is assumed to already
be running on the server as its own service, so make sure `.env`'s
`MARTIN_TILE_SERVER_URL` points at it. Also set `DEBUG=False` and
`ALLOWED_HOSTS` to your domain/IP (e.g. `ALLOWED_HOSTS=your-server-ip,your-domain.com`).

```bash
# 1. Copy the repo to the server and configure environment
cp .env.example .env
# edit .env: DEBUG=False, ALLOWED_HOSTS, MAPBOX_ACCESS_TOKEN, DATABASE_URL,
#            MARTIN_TILE_SERVER_URL (pointing at the already-running Martin), etc.

# 2. Build images and start db + web in the background
docker compose up -d --build
```

- App: `http://<server-ip>:6000`

Database migrations and `collectstatic` run automatically on container start
(see `entrypoint.sh`), so no separate migration step is required after
`up -d`. To run migrations manually (e.g. after pulling new code into an
already-running stack):

```bash
docker compose exec web python manage.py migrate
```

Other useful commands:

```bash
# View logs (web service)
docker compose logs -f web

# Rebuild and restart after pulling new code, without touching the db volume
docker compose up -d --build

# Create an admin user
docker compose exec web python manage.py createsuperuser

# Stop and remove containers/network (keeps volumes — db data & media persist)
docker compose down

# Stop and remove containers/network AND volumes (wipes db data & uploaded media)
docker compose down -v
```

## Local development (without Docker)

Requirements: Python 3.12, PostgreSQL + PostGIS extension, GDAL (`ogr2ogr` on
your `PATH`), and a running Martin binary/service.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # point DATABASE_URL at your local PostGIS instance

python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

Run Martin separately against the same database, e.g.:

```bash
martin postgresql://gis_user:gis_password@localhost:5432/gis_app
```

## Key environment variables (`.env`)

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostGIS connection string, shared with Martin |
| `MAPBOX_ACCESS_TOKEN` | Basemap token used by Mapbox GL JS in templates |
| `MARTIN_TILE_SERVER_URL` | Base URL the browser uses to fetch vector tiles |
| `OGR2OGR_PATH` | Path to the `ogr2ogr` binary (defaults to `ogr2ogr` on `PATH`) |
| `ACCESS_TOKEN_LIFETIME_MINUTES` / `REFRESH_TOKEN_LIFETIME_DAYS` | JWT lifetimes |

## API overview

| Endpoint | Notes |
| --- | --- |
| `POST /api/auth/register/`, `/login/`, `/token/refresh/`, `/logout/` | JWT auth |
| `GET/PATCH /api/auth/me/` | Current user profile |
| `GET /api/auth/users/?search=` | User directory for share pickers |
| `CRUD /api/auth/roles/` | Role & permission management |
| `CRUD /api/layers/`, `POST /api/layers/{id}/share/`, `/unshare/` | Layer upload (multipart), styling, sharing |
| `CRUD /api/maps/`, `GET/POST /api/maps/{id}/layers/`, `PATCH/DELETE /api/maps/{id}/layers/{map_layer_id}/`, `POST /api/maps/{id}/reorder/`, `/share/`, `/unshare/` | Map composition & sharing |

## Tests

```bash
python manage.py test
```
