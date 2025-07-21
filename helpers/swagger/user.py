from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

error_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'erreur': openapi.Schema(type=openapi.TYPE_STRING, description="Description de l'erreur")
    }
)

login_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'refresh': openapi.Schema(type=openapi.TYPE_STRING, description="Token de rafraîchissement JWT"),
        'access': openapi.Schema(type=openapi.TYPE_STRING, description="Token d'accès JWT"),
    }
)

register_request_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['name', 'email', 'password', 'sexe', 'birth_date'],  
    properties={
        'name': openapi.Schema(type=openapi.TYPE_STRING, description="Nom de l'utilisateur"),
        'email': openapi.Schema(type=openapi.TYPE_STRING, format='email', description="Adresse email"),
        'password': openapi.Schema(type=openapi.TYPE_STRING, description="Mot de passe"),
        'sexe': openapi.Schema(
            type=openapi.TYPE_STRING,
            enum=['masculin', 'feminin', 'I'],
            description="Sexe de l'utilisateur (M pour masculin, F pour féminin, I pour inconnu)"
        ),
        'birth_date': openapi.Schema(
            type=openapi.TYPE_STRING,
            format='date',
            description="Date de naissance (format: YYYY-MM-DD ou DD/MM/YYYY)"
        ),
        'profession_domaine': openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Domaine professionnel (optionnel, défaut: 'Inconnu')",
            default='Inconnu'
        ),
    }
)

register_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'email': openapi.Schema(type=openapi.TYPE_STRING, format='email', description="Email de l'utilisateur créé")
    }
)

logout_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'message': openapi.Schema(type=openapi.TYPE_STRING, description="Message de confirmation")
    }
)