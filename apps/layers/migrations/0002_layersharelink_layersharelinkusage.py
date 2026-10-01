# Generated manually — LayerShareLink + LayerShareLinkUsage for XYZ tile sharing.

import apps.layers.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LayerShareLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token", models.CharField(default=apps.layers.models._generate_share_token, editable=False, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("is_blocked", models.BooleanField(default=False, help_text="Admins can block a link without deleting it.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="layer_share_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "layer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="share_links",
                        to="layers.layerinfo",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LayerShareLinkUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("request_count", models.PositiveBigIntegerField(default=0)),
                ("last_request_at", models.DateTimeField()),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="usage",
                        to="layers.layersharelink",
                    ),
                ),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
        migrations.AddConstraint(
            model_name="layersharelinkusage",
            constraint=models.UniqueConstraint(fields=("link", "date"), name="layer_share_link_usage_unique"),
        ),
    ]
