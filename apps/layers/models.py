import uuid

from django.conf import settings
from django.db import models


class LayerInfo(models.Model):
    """Metadata for a shapefile that has been imported into its own PostGIS table.

    The actual geographic features live in a dynamically created table
    (``table_name``) rather than in a Django model, since every uploaded
    shapefile has its own arbitrary attribute schema. Martin discovers that
    table directly from PostGIS and serves it as vector tiles; this row only
    tracks ownership, styling and sharing.
    """

    class GeometryType(models.TextChoices):
        POINT = "Point", "Point"
        MULTIPOINT = "MultiPoint", "MultiPoint"
        LINESTRING = "LineString", "LineString"
        MULTILINESTRING = "MultiLineString", "MultiLineString"
        POLYGON = "Polygon", "Polygon"
        MULTIPOLYGON = "MultiPolygon", "MultiPolygon"
        GEOMETRY = "Geometry", "Geometry"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="layers")

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    schema_name = models.CharField(max_length=63)
    table_name = models.CharField(max_length=63, unique=True)

    geometry_type = models.CharField(max_length=30, choices=GeometryType.choices, default=GeometryType.GEOMETRY)
    srid = models.IntegerField(default=4326)
    feature_count = models.IntegerField(default=0)
    bounds = models.JSONField(null=True, blank=True, help_text="[minx, miny, maxx, maxy] in EPSG:4326")

    attribute_schema = models.JSONField(default=list, blank=True, help_text="[{name, type}] of imported columns")

    style = models.JSONField(default=dict, blank=True, help_text="MapLibre/Mapbox GL paint+layout style")
    label_config = models.JSONField(default=dict, blank=True, help_text="{field, min_zoom, text_color, ...}")

    source_filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("upload_layerinfo", "Can upload new layers"),
            ("share_layerinfo", "Can share layers with other users"),
        ]

    def __str__(self):
        return self.name


class LayerShare(models.Model):
    class Permission(models.TextChoices):
        VIEW = "view", "View only"
        EDIT = "edit", "Can edit style & labels"

    layer = models.ForeignKey(LayerInfo, on_delete=models.CASCADE, related_name="shares")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_layers")
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="layer_shares_granted"
    )
    permission = models.CharField(max_length=10, choices=Permission.choices, default=Permission.VIEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("layer", "shared_with")

    def __str__(self):
        return f"{self.layer.name} -> {self.shared_with} ({self.permission})"
