from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("store", "0008_favorite_and_clear_test_comments")]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="visitor",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="comments", to="store.visitor"),
        ),
        migrations.AddField(
            model_name="comment",
            name="is_hidden",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="CommentReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(default="OUVERT", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="store.comment")),
                ("visitor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="comment_reports", to="store.visitor")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
