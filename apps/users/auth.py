from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework_simplejwt.tokens import TokenError
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.exceptions import APIException

from django.contrib.auth.hashers import make_password

from apps.users.serializers import UserSerializer, LoginSerializer, RegisterSerializer, UpdateProfileSerializer
from apps.users.models import User, UserOtp, default_created_at

from dotenv import load_dotenv
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from bleach.sanitizer import Cleaner
import random, string
from datetime import timedelta, datetime
from django.utils import timezone

from helpers.swagger.user import *
from helpers.services.google.authentication import handle_google_callback, get_google_auth_url
from helpers.services.emails import envoyer_email
from helpers.helper import generate_jwt_token, enc_dec, decode_jwt_token

from uuid import uuid4
import os, traceback, time

load_dotenv()


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    @swagger_auto_schema(
        tags=['Users'],
        request_body=LoginSerializer,
        responses={
            200: login_response_schema,
            400: error_schema,
        },
        operation_description="Connecte un utilisateur et renvoie des tokens JWT."
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            return Response({"erreur": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def check_if_user_exist(self, email):
        return User.objects.filter(email=email).exists()

    def validate_data(self, data):
        try:
            keys = ['name', 'email', 'password', 'birth_date']
            if any(key not in data.keys() for key in keys):
                return False
            return True
        except Exception:
            False

    def post(self, request):
        try:
            user_data = request.data
            if not self.validate_data(user_data):
                return Response({'erreur': 'Tous les attributs sont requis'}, status=status.HTTP_400_BAD_REQUEST)

            birth_date = request.data['birth_date'].replace('/', '-')
            user_data['birth_date'] = birth_date

            if self.check_if_user_exist(request.data['email']):
                return Response({'erreur': 'email existant'}, status=status.HTTP_400_BAD_REQUEST)

            if "profession_domaine" not in user_data:
                user_data["profession_domaine"] = "Inconu"
            if user_data.get('sexe', 'I').lower() not in ['masculin', 'feminin','f','m']:
                user_data['sexe'] = 'I'
            else:
                user_data['sexe'] = user_data['sexe'].strip()[0].upper()

            code_otp = ''.join(random.choices(string.digits, k=6))

            serializer = RegisterSerializer(data=user_data)
            if serializer.is_valid(raise_exception=True):
                user = User.objects.get(email=serializer.validated_data["email"])

                date_expiration = timezone.now() + timedelta(minutes=30)
                UserOtp.objects.create(code_otp=code_otp, user=user, expirer_le=date_expiration)

                data = {
                    'subject': 'Vérification de votre compte Sexual AI',
                    'prenom': user.name.split()[0],
                    'nom': ' '.join(user.name.split()[1:]) if len(user.name.split()) > 1 else '',
                    'code_otp': code_otp,
                    'user_email': 'tokynandrasana2611@gmail.com',
                    'type_utilisateur': 'user' if user.is_staff else 'client',
                }

                envoyer_email([user.email], 'envoie_code_otp', data)

                return Response({"email": serializer.validated_data["email"], 'message':f"Une code Otp de verification a été envoyé à {user.email}"}, status=status.HTTP_201_CREATED)
            else:
                return Response({'erreur': 'erreur de sérialisation'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return Response({"erreur": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class GoogleCallbackUserView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Callback pour l'authentification Google",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["code", "state"],
            properties={
                "code": openapi.Schema(type=openapi.TYPE_STRING, description="Code OAuth Google"),
                "state": openapi.Schema(type=openapi.TYPE_STRING, description="État OAuth")
            }
        ),
        responses={
            200: openapi.Response(
                description="Connexion réussie",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "refresh": openapi.Schema(type=openapi.TYPE_STRING, description="Token de rafraîchissement JWT"),
                        "access": openapi.Schema(type=openapi.TYPE_STRING, description="Token d'accès JWT"),
                        "email": openapi.Schema(type=openapi.TYPE_STRING, description="Email du user"),
                        "message": openapi.Schema(type=openapi.TYPE_STRING, description="Message de succès")
                    }
                )
            ),
            400: openapi.Response(
                description="Code invalide ou manquant",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}
                )
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}
                )
            )
        },
        tags=["Google Auth"]
    )
    def post(self, request):
        try:
            code = request.data.get('code')
            state = request.data.get('state')
            id_info = handle_google_callback(code, state)

            email = id_info.get('email')
            email_verified = id_info.get('email_verified')

            if not email or not email_verified:
                raise APIException("Email non vérifié ou manquant", code=400)
            
            expiration = id_info.get('exp')
            if not expiration or int(expiration) < int(time.time()):
                return Response({"detail": "Le token Google a expiré."}, status=401)

            if User.objects.filter(email=email).exists():
                user = User.objects.get(email=email)
                user.is_active = True
                user.save()

                token = RefreshToken.for_user(user)
                return Response({
                    "success": True,
                    "refresh": str(token),
                    "access": str(token.access_token),
                    "email": user.email,
                    "message": "Connexion user réussie via Google"
                })
            name = id_info.get('name')
            code_id = str(uuid4())
            picture = id_info.get('picture')
            user = User.objects.create(email=email, name=name, code_id=code_id, picture=picture, sexe='I',is_verified=True, is_active=True)
            refresh = RefreshToken.for_user(user)
            return Response({"message": "Inscription reussi via Google ✅", 'success':True, 'email':email, 'refresh':str(refresh), 'access':str(refresh.access_token)}, status=404)

        except Exception as e:
            print(traceback.format_exc(), e)
            return Response({"erreur": str(e)}, status=getattr(e, 'code', status.HTTP_500_INTERNAL_SERVER_ERROR))

class GoogleAuthUrlView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @swagger_auto_schema(
        operation_description="Obtenir l'URL d'authentification Google",
        responses={
            200: openapi.Response(
                description="Succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "success": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Indicateur de succès"),
                        "redirect_url": openapi.Schema(type=openapi.TYPE_STRING, description="URL de redirection Google"),
                        "state": openapi.Schema(type=openapi.TYPE_STRING, description="État OAuth")
                    }
                )
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"detail": openapi.Schema(type=openapi.TYPE_STRING)}
                )
            )
        },
        tags=["Google Auth"]
    )
    def get(self, request):
        try:
            print("get url of google auth ....")
            redirect_url, state = get_google_auth_url()
            print("✅ success getting url...")
            return Response({
                "success": True,
                "redirect_url": redirect_url,
                "state": state
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)+str(traceback.format_exc())}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
