from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0003_geolayers_tile_function"),
    ]

    operations = [
        migrations.AlterField(
            model_name="layersharelink",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Leave blank for a link that never expires (still revocable).",
                null=True,
            ),
        ),
    ]
