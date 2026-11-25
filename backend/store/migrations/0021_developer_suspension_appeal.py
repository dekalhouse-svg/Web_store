from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0020_admin_role")]
    operations = [
        migrations.AddField(model_name="developerprofile", name="suspension_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="developerprofile", name="appeal_message", field=models.TextField(blank=True)),
        migrations.AddField(model_name="developerprofile", name="appeal_status", field=models.CharField(choices=[("AUCUNE", "Aucune"), ("EN_ATTENTE", "En attente"), ("ACCEPTEE", "Acceptée")], default="AUCUNE", max_length=20)),
        migrations.AddField(model_name="developerprofile", name="appealed_at", field=models.DateTimeField(blank=True, null=True)),
    ]
