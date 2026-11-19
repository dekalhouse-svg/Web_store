from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0014_visitor_tokens_rate_limits")]

    operations = [
        migrations.AddField(
            model_name="developerprofile",
            name="avatar_data",
            field=models.TextField(blank=True),
        ),
    ]
