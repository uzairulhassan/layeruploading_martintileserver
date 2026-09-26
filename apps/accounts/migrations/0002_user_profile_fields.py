from django.db import migrations, models
import apps.accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=apps.accounts.models.user_avatar_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="email_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="username_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
