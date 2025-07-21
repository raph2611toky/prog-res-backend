from drf_yasg import openapi

bot_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'bot_response': openapi.Schema(type=openapi.TYPE_STRING, description="Réponse générée par le bot")
    }
)
message_request_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['conversation', 'contenu'],
    properties={
        'conversation': openapi.Schema(
            type=openapi.TYPE_INTEGER,
            description="ID de la conversation à laquelle le message est associé"
        ),
        'contenu': openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Contenu du message envoyé par l'utilisateur"
        ),
        'lang': openapi.Schema(
            type=openapi.TYPE_STRING,
            enum=['FR', 'MG'],
            description="Langue du message (optionnel, 'fr' pour français ou 'MG' pour le malagasy)"
        ),
    }
)

error_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'error': openapi.Schema(type=openapi.TYPE_STRING, description="Description de l'erreur")
    }
)

conversation_request_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['titre'],
    properties={
        'titre': openapi.Schema(
            type=openapi.TYPE_STRING,
            description="Titre de la nouvelle conversation"
        ),
    },
    description="Données requises pour créer une nouvelle conversation. Le champ 'user' est automatiquement défini à partir de l'utilisateur authentifié."
)
