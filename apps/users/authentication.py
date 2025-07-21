from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from apps.users.models import User
import uuid
from helpers.helper import get_token_from_request, get_user

class AnonymousOrAuthenticated(BaseAuthentication):
    def authenticate(self, request):
        try:
            token = get_token_from_request(request)

            if token:
                user = get_user(token)
                if not user:
                    raise AuthenticationFailed("Token invalide.")
                return (user, token)
            else:
                anonymous_user, _ = User.objects.get_or_create(
                    email='anonymous@anonymous.com',
                    is_anonymous=True,
                    defaults={
                        'sexe': 'I',
                        'birth_date': '1000-01-01',
                        'name': 'anonymous',
                        'password': make_password("An0nym0us!@?1000_01/01."),
                        'is_staff': False,
                        'is_superuser': False,
                        'is_verified': True,
                        'is_active': True
                    }
                )
                refresh = RefreshToken.for_user(anonymous_user)
                token = str(refresh.access_token)
                
                request.user = anonymous_user
                request.auth = f'Bearer {token}'
                
                return (anonymous_user, token)
                
        except Exception as e:
            raise AuthenticationFailed(f"Échec de l'authentification : {str(e)}")
    
