from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from helpers.constantes import TEMPLATES_EMAIL
from datetime import datetime
from dotenv import load_dotenv
import os, logging, traceback
import django

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
# django.setup()

load_dotenv()
LOGGER = logging.getLogger(__name__)

def envoyer_email(list_email_to_send:list, template_name:str, data:dict):
    try:
        data['current_year'] = datetime.now().year
        objet = data.get('subject', 'Objet d\'envoie d\'email ici.')
        data['logo_url'] = os.getenv('LOGO_SEXUALAI_URL')
        data['site_url'] = os.getenv('SITE_URL')
        data['support_email'] = os.getenv('SUPPORT_EMAIL')
        html_message = render_to_string(TEMPLATES_EMAIL[template_name], data)
        email_config = settings.EMAIL_HOST_USER
        send_mail(
            objet,
            '',
            email_config,
            list_email_to_send,
            html_message=html_message,
            fail_silently=False,
        )
        
        print("Email envoié avec succès✅.")
        LOGGER.info("Email envoié avec succès✅.")
    except Exception as e:
        print(f"Erreur lors d'envoie de l'email: {e}")
        print(traceback.format_exc())
        LOGGER.error(f"Erreur lors d'envoie de l'email: {e}")
