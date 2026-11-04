import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0004_layersharelink_nullable_expires_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LayerGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True)),
                (
                    "source_format",
                    models.CharField(choices=[("kml", "KML"), ("kmz", "KMZ")], max_length=10),
                ),
                ("source_filename", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="layer_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="layerinfo",
            name="group",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for layers split out of one KML/KMZ upload; null for shapefiles.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="layers",
                to="layers.layergroup",
            ),
        ),
        migrations.AddConstraint(
            model_name="layerinfo",
            constraint=models.UniqueConstraint(
                fields=("group", "geometry_type"), name="layerinfo_one_geometry_type_per_group"
            ),
        ),
    ]
