"""Keep PostGIS layer tables in sync with ``LayerInfo`` rows.

Any delete path (API helpers, admin, user CASCADE, group CASCADE) must drop the
backing ``layers_data.layer_*`` table. ``delete_layer`` / ``delete_layer_group``
rely on this instead of dropping tables themselves.
"""
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import LayerInfo
from .services import drop_layer_table


@receiver(pre_delete, sender=LayerInfo)
def drop_layer_table_on_delete(sender, instance: LayerInfo, **kwargs):
    schema = (instance.schema_name or "").strip()
    table = (instance.table_name or "").strip()
    if schema and table:
        drop_layer_table(schema, table)
