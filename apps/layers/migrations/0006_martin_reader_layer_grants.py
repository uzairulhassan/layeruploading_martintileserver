# Ensure martin_reader can SELECT every layers_data table (existing + future).
# Without this, geolayers_tile (SECURITY INVOKER) returns 500 from Martin.

from django.db import migrations

FORWARD = r"""
GRANT USAGE ON SCHEMA layers_data TO martin_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA layers_data TO martin_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA layers_data
  GRANT SELECT ON TABLES TO martin_reader;
"""

REVERSE = r"""
ALTER DEFAULT PRIVILEGES IN SCHEMA layers_data
  REVOKE SELECT ON TABLES FROM martin_reader;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0005_layergroup"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
