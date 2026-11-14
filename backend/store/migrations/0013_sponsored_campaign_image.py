from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0012_sponsored_campaigns")]

    operations = [
        migrations.AddField(
            model_name="sponsoredcampaign",
            name="image_data",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
    ]
