import uuid

from django.conf import settings
from django.db import models

from apps.layers.models import LayerInfo


class MapProject(models.Model):
    """A saved composition of layers with a basemap, viewport and z-order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="maps")

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    basemap_style = models.CharField(max_length=255, default="mapbox://styles/mapbox/streets-v12")
    center_lng = models.FloatField(default=0)
    center_lat = models.FloatField(default=0)
    zoom = models.FloatField(default=2)

    layers = models.ManyToManyField(LayerInfo, through="MapLayer", related_name="maps")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        permissions = [
            ("share_mapproject", "Can share maps with other users"),
        ]

    def __str__(self):
        return self.name


class MapLayer(models.Model):
    """Through table controlling per-map layer order, visibility and style overrides."""

    map = models.ForeignKey(MapProject, on_delete=models.CASCADE, related_name="map_layers")
    layer = models.ForeignKey(LayerInfo, on_delete=models.CASCADE, related_name="map_layers")
    order = models.PositiveIntegerField(default=0)
    visible = models.BooleanField(default=True)
    opacity = models.FloatField(default=1.0)
    style_override = models.JSONField(null=True, blank=True, help_text="Per-map override of the layer's default style")

    class Meta:
        ordering = ["order"]
        unique_together = ("map", "layer")

    def __str__(self):
        return f"{self.map.name} :: {self.layer.name}"


class MapShare(models.Model):
    class Permission(models.TextChoices):
        VIEW = "view", "View only"
        EDIT = "edit", "Can edit layers & layout"

    map = models.ForeignKey(MapProject, on_delete=models.CASCADE, related_name="shares")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shared_maps")
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="map_shares_granted"
    )
    permission = models.CharField(max_length=10, choices=Permission.choices, default=Permission.VIEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("map", "shared_with")

    def __str__(self):
        return f"{self.map.name} -> {self.shared_with} ({self.permission})"
