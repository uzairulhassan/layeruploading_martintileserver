# GeoLayers — Shapefile Layer Uploading & Mapping Platform

Django + DRF app for uploading shapefiles into PostGIS, styling/sharing them,
and composing them into Mapbox GL maps. Vector tiles are served by the shared
Martin instance in `../geo_infra` (function source `geolayers_tile`).

## Stack

- **Django 5** + **DRF** + **SimpleJWT**
- **PostgreSQL / PostGIS** (shared `geolayers` DB from geo-infra)
- **GDAL / ogr2ogr** — shapefile import
- **Martin** (shared) — MVT via `layers_data.geolayers_tile`
- **Mapbox GL JS** — map builder UI

## Architecture

```
apps/
  accounts/  User, roles, JWT auth
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
(full composition). Styles stay live; revoke / expiry / block apply immediately.

## Running with Docker (shared infrastructure)

```bash
# 1. Shared stack
cd ../geo_infra && docker compose up -d

# 2. This app (use .env locally; on VPS copy .env.prod → .env first)
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
| `.env.prod` | Production values — copy to VPS as `.env` (gitignored) |

## Key variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `postgis://geolayers_user:…@postgis:5432/geolayers` |
| `MAPBOX_ACCESS_TOKEN` | Mapbox GL basemap |
| `TILES_PUBLIC_URL` | Browser tiles base (default `/tiles`) |
| `MARTIN_INTERNAL_URL` | Django → Martin on `geo_shared` |
| `TILE_AUTH_SHARED_SECRET` | Nginx auth_request secret |

## Bootstrap

First account: open `/onetime/` (Admin + superuser). Later accounts: `/signup/`.
