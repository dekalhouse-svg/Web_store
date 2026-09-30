import os

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from getpass import getpass
from store.models import DeveloperProfile


class Command(BaseCommand):
    help = "Crée ou met à jour le compte administrateur WEB STORE."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument("--username")
        parser.add_argument("--password")

    def handle(self, *args, **opts):
        email = (
            opts.get("email")
            or os.environ.get("ADMIN_EMAIL")
            or input("E-mail admin: ")
        ).strip().lower()

        username = (
            opts.get("username")
            or os.environ.get("ADMIN_USERNAME")
            or input("Username admin: ")
        ).strip()

        password = (
            opts.get("password")
            or os.environ.get("ADMIN_PASSWORD")
            or getpass("Mot de passe admin: ")
        )

        if not email or not username or not password:
            self.stderr.write(
                self.style.ERROR("Tous les champs sont obligatoires.")
            )
            return

        user = User.objects.filter(username=username).first()

        if user:
            user.email = email
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Admin existant mis à jour: {user.username}"
                )
            )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Admin créé: {user.username}")
        )
