from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("store", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="project",
            name="featured",
            field=models.BooleanField(default=False),
        ),
    ]
