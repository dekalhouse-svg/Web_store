from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from store.models import Notification, NotificationReminderLog, Project, PushSubscription
from store.views import _send_web_push


class Command(BaseCommand):
    help = "Envoie les rappels WEB STORE dus aux développeurs (sans doublons)."

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0
        checked = 0
        users = User.objects.filter(
            is_active=True, developer_profile__status="ACTIF"
        ).exclude(is_staff=True).select_related("developer_profile")

        for user in users.iterator():
            checked += 1
            has_projects = Project.objects.filter(developer=user).exists()

            # Rappel de création uniquement si le compte n'a encore aucun projet.
            if not has_projects:
                age_days = (now - user.date_joined).days
                due = max((d for d in (2, 7, 14) if age_days >= d), default=None)
                if due is not None:
                    anchor = user.date_joined.isoformat()
                    key = f"no_project:{user.pk}:{anchor}:{due}"
                    if self._send_once(user, key, "no_project", due,
                        "Votre premier projet vous attend",
                        "Vous n'avez pas encore publié de projet sur WEB STORE. Prenez quelques minutes pour présenter votre premier site ou PWA.",
                        "/pages/projects.html"):
                        sent += 1

            # L'inactivité est mesurée depuis la dernière connexion connue.
            if user.last_login:
                inactive_days = (now - user.last_login).days
                due = max((d for d in (14, 30) if inactive_days >= d), default=None)
                if due is not None:
                    anchor = user.last_login.isoformat()
                    key = f"inactive:{user.pk}:{anchor}:{due}"
                    if self._send_once(user, key, "inactive", due,
                        "Votre espace WEB STORE vous attend",
                        f"Cela fait environ {due} jours que vous ne vous êtes pas connecté. Revenez suivre vos projets et vos messages.",
                        "/pages/dashboard.html"):
                        sent += 1

        self.stdout.write(self.style.SUCCESS(
            f"Rappels terminés : {sent} notification(s) envoyée(s), {checked} compte(s) vérifié(s)."
        ))

    def _send_once(self, user, key, reminder_type, days, title, body, target_url):
        try:
            with transaction.atomic():
                NotificationReminderLog.objects.create(
                    user=user, reminder_key=key, reminder_type=reminder_type, threshold_days=days
                )
                notification = Notification.objects.create(
                    recipient=user, title=title, body=body, category="activity", target_url=target_url
                )
        except IntegrityError:
            return False

        # Le push est envoyé après validation en base : une panne push ne perd pas le rappel interne.
        for subscription in PushSubscription.objects.filter(user=user).iterator():
            _send_web_push(subscription, notification)
        return True
