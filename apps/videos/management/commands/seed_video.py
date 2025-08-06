from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from apps.users.models import User
from apps.videos.models import Chaine
from datetime import datetime

class Command(BaseCommand):
    help = "Seeder pour administrateur, client, utilisateur, établissement, rôle, etc."

    def handle(self, *args, **kwargs):
        self.stdout.write("🚀 Suppression des anciennes données...")
        Chaine.objects.all().delete()
        self.stdout.write("📦 Création des entités de base...")
        
        chaine = Chaine.objects.create(titre="Chaine de Streaming",description="Chaine de Streaming.")
        
        self.stdout.write(f"✅ Création de chaine reussi..., id: {chaine.id}")