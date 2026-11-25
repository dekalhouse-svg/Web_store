from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0021_developer_suspension_appeal")]

    operations = [
        migrations.AddField(
            model_name="developerprofile",
            name="public_username",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AlterField(
            model_name="pendingdeveloperregistration",
            name="username",
            field=models.CharField(max_length=150),
        ),
        migrations.RemoveConstraint(
            model_name="pendingdeveloperregistration",
            name="uniq_pending_dev_username_ci",
        ),
        migrations.AddConstraint(
            model_name="pendingdeveloperregistration",
            constraint=models.UniqueConstraint(condition=~models.Q(phone=""), fields=("phone",), name="uniq_pending_dev_phone"),
        ),
        migrations.AddConstraint(
            model_name="developerprofile",
            constraint=models.UniqueConstraint(condition=~models.Q(phone=""), fields=("phone",), name="uniq_developer_profile_phone"),
        ),
    ]
