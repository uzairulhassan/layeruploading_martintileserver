from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("maps", "0002_mapsharelink_mapsharelinkusage"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="mapproject",
            options={
                "ordering": ["-updated_at"],
                "permissions": [
                    ("create_mapproject", "Can create new maps"),
                    ("share_mapproject", "Can share maps with other users"),
                ],
            },
        ),
    ]
