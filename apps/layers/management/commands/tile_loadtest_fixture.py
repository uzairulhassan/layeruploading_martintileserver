"""
Create (or remove) a throwaway layer + user + share link for the geo-infra smoke/latency/load tests.

    python manage.py tile_loadtest_fixture [--points 5000]   # prints JSON on stdout
    python manage.py tile_loadtest_fixture --cleanup         # drops the table, deletes user + links

The layer is a real PostGIS table in layers_data (random points around Riyadh), so
Martin's geolayers_tile function does real work. The share link expires after one
day, even if --cleanup is never run.
"""
import json
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.layers.models import LayerInfo, LayerShareLink
from apps.layers.services import (
    _ensure_schema_exists,
    _ensure_spatial_index,
    _generate_table_name,
    _introspect_table,
    delete_layer,
)

LOADTEST_USERNAME = "loadtest_owner"
LOADTEST_EMAIL = "loadtest-owner@geolayers.invalid"
# Riyadh, roughly. Same area the GeoTrak tests use, so one tile list works for both.
BBOX = (46.55, 24.55, 46.90, 24.85)


class Command(BaseCommand):
    help = "Create or remove the GeoLayers load-test layer, user and share link (JSON on stdout)."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup", action="store_true")
        parser.add_argument("--points", type=int, default=5000)

    def handle(self, *args, **opts):
        user_model = get_user_model()
        if opts["cleanup"]:
            user = user_model.objects.filter(username=LOADTEST_USERNAME).first()
            dropped = 0
            if user:
                for layer in LayerInfo.objects.filter(owner=user):
                    delete_layer(layer)
                    dropped += 1
                user.delete()
            self.stdout.write(json.dumps({"dropped_layers": dropped, "deleted_user": bool(user)}))
            return

        password = secrets.token_urlsafe(18)
        user, _ = user_model.objects.get_or_create(
            username=LOADTEST_USERNAME, defaults={"email": LOADTEST_EMAIL}
        )
        user.set_password(password)
        user.is_active = True
        user.save()

        schema = "layers_data"
        table = _generate_table_name()
        minx, miny, maxx, maxy = BBOX
        _ensure_schema_exists(schema)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f'CREATE TABLE "{schema}"."{table}" ('
                "id serial PRIMARY KEY, name text, category integer, "
                "geom geometry(MultiPoint, 4326))"
            )
            cursor.execute(
                f'INSERT INTO "{schema}"."{table}" (name, category, geom) '
                "SELECT 'pt ' || g, g % 10, "
                "ST_Multi(ST_SetSRID(ST_MakePoint(%s + random() * %s, %s + random() * %s), 4326)) "
                "FROM generate_series(1, %s) AS g",
                [minx, maxx - minx, miny, maxy - miny, opts["points"]],
            )
        _ensure_spatial_index(schema, table)

        layer = LayerInfo.objects.create(
            owner=user,
            name="Load test points",
            description="Created by tile_loadtest_fixture; safe to delete.",
            schema_name=schema,
            table_name=table,
            source_filename="loadtest",
            **_introspect_table(schema, table),
        )
        link = LayerShareLink.objects.create(
            layer=layer, created_by=user, expires_at=timezone.now() + timedelta(days=1)
        )
        self.stdout.write(json.dumps({
            "username": LOADTEST_USERNAME,
            "password": password,
            "layer_id": str(layer.id),
            "layer_table": table,
            "share_token": link.token,
            "bounds": layer.bounds,
        }))
