# GeoLayers — Shapefile Layer Uploading & Mapping Platform

Django + DRF app for uploading shapefiles into PostGIS, styling/sharing them,
and composing them into Mapbox GL maps. Vector tiles are served by the shared
Martin instance in `../geo_infra` (function source `geolayers_tile`).

## Stack

- **Django 5** + **DRF** + **SimpleJWT** (browser: HttpOnly session; API clients: JWT)
- **PostgreSQL / PostGIS** (shared `geolayers` DB from geo-infra)
- **GDAL / ogr2ogr** — shapefile import
- **Martin** (shared) — MVT via `layers_data.geolayers_tile`
- **Mapbox GL JS** — map builder UI

## Architecture

```
apps/
  accounts/  User, roles, session + JWT auth
  layers/    Upload pipeline, LayerInfo, tile auth, external share links
  maps/      Saved map compositions
  core/      Template pages (dashboard, layers, maps)
```

Upload flow: `.zip` shapefile → `ogr2ogr` → `layers_data.layer_<uuid>` →
Martin `geolayers_tile?layer=` → Mapbox GL / external share link `/x/<token>/…`.

**KML / KMZ:** one file can mix points, lines and polygons, so it becomes a
`LayerGroup` with one layer (and table) per geometry type present
(`apps/layers/kml_import.py`). Each feature keeps its KML colour in
`kml_color` / `kml_stroke` / `kml_width`; the layer style starts from the most
common KML style with `useSourceColors: true`, and users can restyle it.
`/api/layer-groups/` lists, renames, shares or deletes a whole upload;
`POST /api/maps/<id>/layers/ {"group": …}` adds all of its layers. Needs GDAL's
LIBKML driver (`ogrinfo --formats | grep LIBKML`).

**Map URL / Layer URL:** owners create revocable links.
Layer URL → `/x/<token>/style.json`. Map URL → `/m/<token>/style.json`
(visible layers of the composition, live). Styles stay live; revoke / expiry / block apply immediately.

## Running with Docker (shared infrastructure)

```bash
# 1. Shared stack
cd ../geo_infra && docker compose up -d

# 2. This app (.env locally; on VPS use .env.prod contents as .env)
cd ../layeruploading_martintileserver
docker compose -f docker-compose.prod.yml up -d --build

# 3. After FIRST migrate (creates geolayers_tile function):
cd ../geo_infra && docker compose restart martin
```

Local live-reload: `docker compose up -d --build` (bind-mounts source).

| What | URL |
| --- | --- |
| App | http://&lt;host&gt;:8081 |
| Map builder tiles | http://&lt;host&gt;:8081/tiles/geolayers_tile/{z}/{x}/{y}?layer=layer_&lt;hex&gt; |
| Layer URL | http://&lt;host&gt;:8081/x/&lt;token&gt;/style.json |
| Map URL | http://&lt;host&gt;:8081/m/&lt;token&gt;/style.json |

`DATABASE_URL` password must equal `GEOLAYERS_DB_PASSWORD` in `geo_infra/.env`.
`TILE_AUTH_SHARED_SECRET` must equal `GEOLAYERS_TILE_AUTH_SHARED_SECRET` in `geo_infra/.env`.

## Environment files

| File | Use |
| --- | --- |
| `.env` | Local development (gitignored) |
| `.env.prod` | Production source of truth — deploy its contents as `.env` on the VPS (gitignored) |

## Key variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `postgis://geolayers_user:…@postgis:5432/geolayers` |
| `MAPBOX_ACCESS_TOKEN` | Mapbox GL basemap |
| `TILES_PUBLIC_URL` | Browser tiles base (default `/tiles`) |
| `MARTIN_INTERNAL_URL` | Django → Martin on `geo_shared` |
| `TILE_AUTH_SHARED_SECRET` | Nginx auth_request secret (required when `DEBUG=False`) |
| `SHARE_LINK_MAX_TTL_DAYS` | Max days ahead for finite share-link expiry (default 365) |
| `USE_TLS` | `True` once HTTPS terminates in front of `:8081` (Secure cookies + HSTS) |
| `THROTTLE_AUTH_*` / `AUTH_LOGIN_LOCKOUT_*` | Login/register abuse controls |
| `ALLOW_PUBLIC_SIGNUP` | `True` opens `/signup/` + `/api/auth/register/`; `False` keeps them closed |

## Auth model

1. Browser: `POST /api/auth/login/` sets `geolayers_sessionid` (HttpOnly) and returns `{ user }` only; UI APIs use session + CSRF via `Auth.apiFetch`.
2. API clients: `POST /api/auth/token/` + `/api/auth/token/refresh/` for JWT (Bearer).
3. Password change and logout blacklist outstanding refresh tokens; HTML `/logout/` is POST-only.
4. Public `/signup/` gated by `ALLOW_PUBLIC_SIGNUP`; roles carry upload / create-map / share permissions.
5. Abuse controls: Django throttles + login lockout; Nginx `limit_req` on `/api/auth/`.
6. Avatars are re-encoded before storage; share links stay capability URLs with revoke/block/expiry.

## Bootstrap

First account: open `/onetime/` (Admin + superuser). Public accounts use `/signup/` only when `ALLOW_PUBLIC_SIGNUP=True`.

## Production deploy (GitHub Actions)

Pushing to `main` does **not** update the VPS. Deploy only when you click the button:

1. Push your changes to `main`.
2. GitHub → **Actions** → **Deploy to production** → **Run workflow**.
3. Wait for the run to go green (SSH → `scripts/deploy.sh` → rebuild → smoke check on `:8081`).

Emergency fallback on the VPS (same script Actions uses):

```bash
cd /path/to/layeruploading_martintileserver
./scripts/deploy.sh
```

### Required GitHub Actions secrets

Repo **Settings → Secrets and variables → Actions**:

| Secret | Meaning |
| --- | --- |
| `DEPLOY_HOST` | VPS hostname or IP |
| `DEPLOY_USER` | SSH user |
| `DEPLOY_SSH_KEY` | Private key (full PEM) that can SSH as that user |
| `DEPLOY_PATH` | Absolute path to this repo clone on the VPS |
| `DEPLOY_SSH_PORT` | Optional; defaults to `22` if unset |

The VPS clone must be able to `git pull origin main` non-interactively (deploy key or credential helper). Shared infra (`geo_infra`) has its own separate Deploy workflow.
