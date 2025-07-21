from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport.requests import Request
import os
from django.conf import settings
from rest_framework.exceptions import APIException
from urllib.parse import urljoin
from dotenv import load_dotenv
import traceback

load_dotenv()

SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']
REDIRECT_URI = "https://sexualai.learnix.school/auth/google/callback"
print(REDIRECT_URI)

def get_google_auth_url():
    try:
        secret_json_path = os.path.join(settings.BASE_DIR, 'helpers/services/google/client_secret.json')
        flow = Flow.from_client_secrets_file(
            secret_json_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        return authorization_url, state
    except Exception as e:
        print(traceback.format_exc())
        raise APIException(detail=f"Erreur lors de la génération du lien Google: {str(e)}")

def handle_google_callback(code, state):
    try:
        if not code:
            raise APIException(detail="Code requis", code=400)

        secret_json_path = os.path.join(settings.BASE_DIR, 'helpers/services/google/client_secret.json')
        flow = Flow.from_client_secrets_file(
            secret_json_path,
            scopes=SCOPES,
            state=state,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials

        idinfo = id_token.verify_oauth2_token(
            credentials.id_token,
            Request(),
            os.getenv('GOOGLE_CLIENT_ID')
        )

        return idinfo
    except ValueError as ve:
        print(traceback.format_exc())
        raise APIException(detail="Code invalide ou expiré", code=400)
    except Exception as e:
        print(traceback.format_exc())
        raise APIException(detail=f"Erreur serveur: {str(e)+str(traceback.format_exc())}")

