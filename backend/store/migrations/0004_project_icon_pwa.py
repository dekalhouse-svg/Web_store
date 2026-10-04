from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0003_visitor")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="icon_data",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="project",
            name="pwa_verified",
            field=models.BooleanField(default=False),
        ),
    ]
