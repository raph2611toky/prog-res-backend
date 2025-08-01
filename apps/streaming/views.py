from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.streaming.models import VideoWatch
from apps.streaming.serializers import VideoWatchSerializer
from apps.users.models import default_created_at
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class VideoWatchUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Récupère les informations de visionnage pour une vidéo spécifique",
        tags=["VideoWatch"],
        responses={
            200: VideoWatchSerializer(),
            404: openapi.Response(
                description="Session de visionnage non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, code_id):
        try:
            video_watch = VideoWatch.objects.get(video__code_id=code_id, user=request.user)
            serializer = VideoWatchSerializer(video_watch)
            return Response(serializer.data, status=200)
        except VideoWatch.DoesNotExist:
            return Response({"erreur": "Session de visionnage non trouvée"}, status=404)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

    @swagger_auto_schema(
        operation_description="Met à jour ou crée une session de visionnage pour une vidéo spécifique",
        tags=["VideoWatch"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'last_position': openapi.Schema(type=openapi.TYPE_NUMBER, description="Dernière position en secondes", default=0.0),
                'quality': openapi.Schema(type=openapi.TYPE_STRING, description="Qualité sélectionnée (ex: '720p', 'auto')", default="auto"),
                'playback_speed': openapi.Schema(type=openapi.TYPE_NUMBER, description="Vitesse de lecture (ex: 1.0, 1.5)", default=1.0),
                'volume': openapi.Schema(type=openapi.TYPE_NUMBER, description="Niveau de volume (0.0 à 1.0)", default=1.0),
            }
        ),
        responses={
            200: VideoWatchSerializer(),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, code_id):
        try:
            video_watch, created = VideoWatch.objects.get_or_create(
                video__code_id=code_id,
                user=request.user,
                defaults={
                    'last_position': request.data.get('last_position', 0.0),
                    'quality': request.data.get('quality', 'auto'),
                    'playback_speed': request.data.get('playback_speed', 1.0),
                    'volume': request.data.get('volume', 1.0),
                    'last_watch': default_created_at()
                }
            )
            if not created:
                video_watch.last_position = request.data.get('last_position', video_watch.last_position)
                video_watch.quality = request.data.get('quality', video_watch.quality)
                video_watch.playback_speed = request.data.get('playback_speed', video_watch.playback_speed)
                video_watch.volume = request.data.get('volume', video_watch.volume)
                video_watch.last_watch = default_created_at()
                video_watch.save()
            serializer = VideoWatchSerializer(video_watch)
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)