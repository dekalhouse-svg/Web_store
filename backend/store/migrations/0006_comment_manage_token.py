from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0005_login_attempt")]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="manage_token_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
