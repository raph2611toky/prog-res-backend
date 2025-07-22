from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from apps.users.models import User
from datetime import datetime

class Command(BaseCommand):
    help = "Seeder pour administrateur, client, utilisateur, établissement, rôle, etc."

    def handle(self, *args, **kwargs):
        self.stdout.write("🚀 Suppression des anciennes données...")
        User.objects.all().delete()

        self.stdout.write("📦 Création des entités de base...")

        self.stdout.write("👤 Création des utilisateur...")
        User.objects.create(
            name="TOKY", email="tokynandrasana2611@gmail.com", password=make_password("toky1234"),
            sexe="M", birth_date=datetime.strptime('26-11-2003','%d-%m-%Y'),
            is_verified=True, is_staff=True, is_active=True,is_superuser=True,
        )
        User.objects.create(
            name="LADY", email="jennysclady@gmail.com", password=make_password("lady1234"),
            sexe="F", birth_date=datetime.strptime('26-11-2003','%d-%m-%Y'),
            is_verified=True, is_staff=False, is_active=True,is_superuser=False,
        )
        self.stdout.write("✅ Création des utilisateur reussi...")