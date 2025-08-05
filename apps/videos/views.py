from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.videos.models import Video, Chaine, VideoPlaylist, Playlist, Commentaire, Message, Tag, VideoVue, VideoLike, VideoDislike, VideoRegarderPlusTard,VideoUpload, VideoChunk, VideoProcessingTask
from apps.videos.serializers import VideoSerializer, ChaineSerializer, CommentaireSerializer, MessageSerializer, TagSerializer, PlaylistSerializer
from apps.videos.tasks import process_video_conversion, generate_video_affichage
from helpers.helper import LOGGER, get_token_from_request, get_user, format_file_size, get_available_info, format_duration

from drf_yasg.utils import swagger_auto_schema
from django.core.files import File
from drf_yasg import openapi
from django.conf import settings
from django.http import FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from django.utils import timezone as django_timezone
# from chunked_upload.views import ChunkedUploadView
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from datetime import datetime
from datetime import timedelta, timezone
import uuid, time, os, shutil
from queue import Queue
from threading import Thread

import traceback

################################# WORKER #################################

video_processing_queue = Queue()

def video_processing_worker():
    while True:
        print(video_processing_queue)
        video_info = video_processing_queue.get()
        process_type = video_info.get('type')
        video_id = video_info.get('video_id')
        print("[!] 🖼️ Worker processing vidéo...", video_id)
        try:
            if process_type == "THUMBNAILS":
                generate_video_affichage(video_id)
            elif process_type == "CONVERSION":
                process_video_conversion(video_id)
        except Exception as e:
            print("[❌] Erreur dans le worker pour image ID:", video_id, str(e))
        finally:
            video_processing_queue.task_done()
            
processing_worker_thread = Thread(target=video_processing_worker, daemon=True)
processing_worker_thread.start()

################################# WORKER #################################

class TagCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Crée un nouveau tag (en minuscules, sans espaces)",
        tags=["Tags"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description="Nom du tag (converti en minuscules, sans espaces)"),
            },
            required=['name']
        ),
        responses={
            201: TagSerializer(),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request):
        try:
            tag_search = Tag.objects.filter(name=request.data.get('name').lower())
            if tag_search.exists():
                return Response(TagSerializer(tag_search.first()).data, status=200)
            serializer = TagSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)
        except Exception as e:
            return Response({'erreur': str(e)}, status=500)

# Playlist Views

class PlaylistListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste toutes les playlists d'une chaîne",
        manual_parameters=[
            openapi.Parameter('chaine_id', openapi.IN_QUERY, description="ID de la chaîne", type=openapi.TYPE_INTEGER, required=True),
        ],
        responses={
            200: PlaylistSerializer(many=True),
            400: openapi.Response(
                description="Requête invalide",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, chaine_id):
        try:
            playlists = Playlist.objects.filter(chaine__id=chaine_id)
            serializer = PlaylistSerializer(playlists, many=True, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class UserPlaylistListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste toutes les playlists temporaires d'un utilisateur",
        responses={
            200: PlaylistSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            playlists = Playlist.objects.filter(user=request.user)
            serializer = PlaylistSerializer(playlists, many=True, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class PlaylistDetailView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Récupère les détails d'une playlist spécifique",
        responses={
            200: PlaylistSerializer(),
            404: openapi.Response(
                description="Playlist non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, playlist_id):
        try:
            playlist = Playlist.objects.get(id=playlist_id)
            serializer = PlaylistSerializer(playlist, context={'request': request})
            return Response(serializer.data)
        except Playlist.DoesNotExist:
            return Response({'error': 'Playlist non trouvée'}, status=404)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class PlaylistCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Crée une nouvelle playlist (associée à une chaîne ou un utilisateur)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'titre': openapi.Schema(type=openapi.TYPE_STRING, description="Titre de la playlist", nullable=True),
                'chaine': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID de la chaîne", nullable=True),
                'video_ids': openapi.Schema(type=openapi.TYPE_ARRAY, description="Liste des IDs des vidéos", items=openapi.Items(type=openapi.TYPE_INTEGER), nullable=True),
            },
            required=[]
        ),
        responses={
            201: PlaylistSerializer(),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request):
        try:
            data = request.data.copy()
            data["user"] = request.user
            serializer = PlaylistSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class PlaylistUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Met à jour une playlist existante",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'titre': openapi.Schema(type=openapi.TYPE_STRING, description="Titre de la playlist", nullable=True),
                'video_ids': openapi.Schema(type=openapi.TYPE_ARRAY, description="Liste des IDs des vidéos", items=openapi.Items(type=openapi.TYPE_INTEGER), nullable=True),
            }
        ),
        responses={
            200: PlaylistSerializer(),
            403: openapi.Response(
                description="Permission refusée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Playlist non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def put(self, request, playlist_id):
        try:
            playlist = Playlist.objects.get(id=playlist_id)
            if playlist.user and playlist.user != request.user:
                return Response({"error": "Vous n'êtes pas autorisé à modifier cette playlist"}, status=403)
            serializer = PlaylistSerializer(playlist, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors(), status=400)
        except Playlist.DoesNotExist:
            return Response({'error': 'Playlist non trouvée'}, status=404)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class PlaylistDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Supprime une playlist",
        responses={
            204: openapi.Response(description="Playlist supprimée"),
            403: openapi.Response(
                description="Permission refusée",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Playlist non trouvée",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def delete(self, request, playlist_id):
        try:
            playlist = Playlist.objects.get(id=playlist_id)
            if playlist.user and playlist.user != request.user:
                return Response({'error': 'Vous n\'êtes pas autorisé à supprimer cette playlist'}, status=403)
            playlist.delete()
            return Response(status=204)
        except Playlist.DoesNotExist:
            return Response({'error': 'Playlist non trouvée'}, status=404)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

# Video Views

class VideoListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste toutes les vidéos avec filtres optionnels",
        manual_parameters=[
            openapi.Parameter('tags', openapi.IN_QUERY, description="Tags séparés par des virgules", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('categorie', openapi.IN_QUERY, description="Catégorie de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('date_filter', openapi.IN_QUERY, description="Filtre de date (recent, today, week, month, year)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Date de début (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="Date de fin (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('order_by', openapi.IN_QUERY, description="Trier par (likes, dislikes, comments, date)", type=openapi.TYPE_STRING, required=False),
        ],
        responses={
            200: VideoSerializer(many=True),
            400: openapi.Response(
                description="Requête invalide",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        videos = Video.objects.all()
        
        search_term = request.query_params.get('search_term')
        if search_term:
            videos = videos.filter(titre__icontains=search_term)

        tags = request.query_params.get('tags')
        if tags:
            videos = videos.filter(tags__name__in=tags.split(','))

        categorie = request.query_params.get('categorie')
        if categorie:
            videos = videos.filter(categorie=categorie)

        date_filter = request.query_params.get('date_filter')
        now = django_timezone.now()
        if date_filter == 'today':
            videos = videos.filter(uploaded_at__date=now.date())
        elif date_filter == 'week':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=7))
        elif date_filter == 'month':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=30))
        elif date_filter == 'year':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=365))
        elif date_filter == 'recent':
            videos = videos.order_by('-uploaded_at')

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            videos = videos.filter(uploaded_at__range=[start_date, end_date])

        order_by = request.query_params.get('order_by')
        if order_by == 'likes':
            videos = videos.annotate(like_count=Count('likes')).order_by('-like_count')
        elif order_by == 'dislikes':
            videos = videos.annotate(dislike_count=Count('dislikes')).order_by('-dislike_count')
        elif order_by == 'comments':
            videos = videos.annotate(comment_count=Count('commentaires')).order_by('-comment_count')
        elif order_by == 'date':
            videos = videos.order_by('-uploaded_at')

        serializer = VideoSerializer(videos, many=True, context={'request': request, "with_suggestion": False})
        return Response(serializer.data)

class MyVideoListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste toutes les vidéos avec filtres optionnels",
        manual_parameters=[
            openapi.Parameter('tags', openapi.IN_QUERY, description="Tags séparés par des virgules", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('categorie', openapi.IN_QUERY, description="Catégorie de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('date_filter', openapi.IN_QUERY, description="Filtre de date (recent, today, week, month, year)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Date de début (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="Date de fin (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('order_by', openapi.IN_QUERY, description="Trier par (likes, dislikes, comments, date)", type=openapi.TYPE_STRING, required=False),
        ],
        responses={
            200: VideoSerializer(many=True),
            400: openapi.Response(
                description="Requête invalide",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            videos = Video.objects.filter(envoyeur=request.user)

            tags = request.query_params.get('tags')
            if tags:
                videos = videos.filter(tags__name__in=tags.split(','))

            categorie = request.query_params.get('categorie')
            if categorie:
                videos = videos.filter(categorie=categorie)

            date_filter = request.query_params.get('date_filter')
            now = django_timezone.now()
            if date_filter == 'today':
                videos = videos.filter(uploaded_at__date=now.date())
            elif date_filter == 'week':
                videos = videos.filter(uploaded_at__gte=now - timedelta(days=7))
            elif date_filter == 'month':
                videos = videos.filter(uploaded_at__gte=now - timedelta(days=30))
            elif date_filter == 'year':
                videos = videos.filter(uploaded_at__gte=now - timedelta(days=365))
            elif date_filter == 'recent':
                videos = videos.order_by('-uploaded_at')

            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            if start_date and end_date:
                videos = videos.filter(uploaded_at__range=[start_date, end_date])

            order_by = request.query_params.get('order_by')
            if order_by == 'likes':
                videos = videos.annotate(like_count=Count('likes')).order_by('-like_count')
            elif order_by == 'dislikes':
                videos = videos.annotate(dislike_count=Count('dislikes')).order_by('-dislike_count')
            elif order_by == 'comments':
                videos = videos.annotate(comment_count=Count('commentaires')).order_by('-comment_count')
            elif order_by == 'date':
                videos = videos.order_by('-uploaded_at')

            serializer = VideoSerializer(videos, many=True, context={'request': request, "with_suggestion": False})
            return Response(serializer.data)
        except Exception as e:
            return Response({"erreur":str(e)},status=500)

class VideoDetailView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Récupère les détails d'une vidéo spécifique",
        responses={
            200: VideoSerializer(),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            serializer = VideoSerializer(video, context={'request': request})
            return Response(serializer.data)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
        
class VideoDetailByCodeIdView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Récupère les détails d'une vidéo spécifique",
        responses={
            200: VideoSerializer(),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, code_id):
        try:
            video = Video.objects.get(code_id=code_id)
            serializer = VideoSerializer(video, context={'request': request})
            return Response(serializer.data)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_description="Crée une nouvelle vidéo avec fichiers joints",
        manual_parameters=[
            openapi.Parameter('titre', openapi.IN_FORM, description="Titre de la vidéo", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter('description', openapi.IN_FORM, description="Description de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('fichier', openapi.IN_FORM, description="Fichier vidéo", type=openapi.TYPE_FILE, required=True),
            openapi.Parameter('affichage', openapi.IN_FORM, description="Image d'affichage", type=openapi.TYPE_FILE, required=False),
            openapi.Parameter('categorie', openapi.IN_FORM, description="Catégorie de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('tags', openapi.IN_FORM, description="Tags séparés par des virgules", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('visibilite', openapi.IN_FORM, description="Visibilité (PUBLIC ou PRIVATE)", type=openapi.TYPE_STRING, enum=['PUBLIC', 'PRIVATE'], required=False),
            openapi.Parameter('autoriser_commentaire', openapi.IN_FORM, description="Autoriser les commentaires", type=openapi.TYPE_BOOLEAN, required=False),
            openapi.Parameter('ordre_de_commentaire', openapi.IN_FORM, description="Ordre des commentaires (TOP ou NOUVEAUTE)", type=openapi.TYPE_STRING, enum=['TOP', 'NOUVEAUTE'], required=False),
        ],
        responses={
            201: VideoSerializer(),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request):
        tags_str = request.data.get('tags', '')
        tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        request.data._mutable = True
        request.data['tags_names'] = tags_list
        request.data._mutable = False
        serializer = VideoSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            video = serializer.save()
            fichier = request.FILES.get('fichier', None)
            if fichier:
                video.fichier = fichier
            video.save()
            video_processing_queue.put(
                {
                    "type":"THUMBNAILS",
                    "video_id":video.id
                }
            )            
            video_processing_queue.put(
                {
                    "type":"CONVERSION",
                    "video_id":video.id
                }
            )
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "video_updates",
                {
                    "type": "video_created",
                    "video_id": video.id,
                    "video_data": VideoSerializer(video, context={'request': request}).data
                }
            )
            
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

class ManualVideoChunkUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            user = request.user

            start_time = datetime.now(timezone.utc)
            chunk = request.FILES.get('fichier')
            upload_id = request.POST.get('upload_id', str(uuid.uuid4()))
            chunk_number = int(request.POST.get('chunk_number', 0))
            total_chunks = int(request.POST.get('total_chunks', 0))
            total_size = int(request.POST.get('total_size', 0))

            if not chunk or not total_chunks or not total_size:
                return Response({"error": "Données manquantes (fichier, total_chunks, total_size)"}, status=400)

            if chunk_number == 0:
                video_upload_data = {
                    'upload_id': upload_id,
                    'user': user,
                    'titre': request.POST.get('titre', ''),
                    'description': request.POST.get('description', ''),
                    'categorie': request.POST.get('categorie', ''),
                    'visibilite': request.POST.get('visibilite', 'PUBLIC'),
                    'tags': request.POST.get('tags', ''),
                    'total_size': total_size,
                    'total_chunks': total_chunks
                }
                video_upload = VideoUpload.objects.create(**video_upload_data)
            else:
                try:
                    video_upload = VideoUpload.objects.get(upload_id=upload_id)
                except VideoUpload.DoesNotExist:
                    return Response({"error": "Upload ID invalide ou métadonnées manquantes"}, status=400)

            chunk_instance = VideoChunk.objects.create(
                video_upload=video_upload,
                chunk_number=chunk_number,
                chunk_file=chunk
            )

            elapsed_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            speed = chunk.size / elapsed_time if elapsed_time > 0 else 0
            uploaded_bytes = sum(c.chunk_file.size for c in video_upload.chunks.all())
            progress = (uploaded_bytes / total_size) * 100
            total_duration = total_size / speed if speed > 0 else 0
            remaining_duration = total_duration * (1 - progress / 100)
            remaining_size = total_size - uploaded_bytes

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"upload_{user.id}_{upload_id}",
                {
                    'type': 'upload_progress',
                    'progress': round(progress, 2),
                    'speed': format_file_size(speed) + "/s",
                    'total_duration': format_duration(int(total_duration)),
                    'remaining_duration': format_duration(int(remaining_duration)),
                    'remaining_size': format_file_size(remaining_size),
                    'uploaded_bytes': uploaded_bytes,
                    'total_bytes': total_size,
                    'status': 'uploading'
                }
            )

            if video_upload.chunks.count() == int(total_chunks):
                try:
                    final_file_path = os.path.join(settings.MEDIA_ROOT, 'videos', f"{upload_id}.mp4")
                    os.makedirs(os.path.dirname(final_file_path), exist_ok=True)
                    with open(final_file_path, 'wb') as final_file:
                        for i in range(total_chunks):
                            chunk_instance = video_upload.chunks.get(chunk_number=i)
                            with open(chunk_instance.chunk_file.path, 'rb') as chunk_file:
                                final_file.write(chunk_file.read())
                            os.remove(chunk_instance.chunk_file.path)
                            chunk_instance.delete()

                    if not os.path.exists(final_file_path):
                        return Response({"error": "Le fichier final n'a pas été créé correctement"}, status=500)

                    with open(final_file_path, 'rb') as final_file:
                        django_file = File(final_file, name=f"{upload_id}.mp4")

                        video_data = {
                            'envoyeur': user,
                            'titre': video_upload.titre,
                            'description': video_upload.description,
                            'categorie': video_upload.categorie,
                            'visibilite': video_upload.visibilite,
                            'tags_names': [tag.strip() for tag in video_upload.tags.split(',') if tag.strip()]
                        }

                        serializer = VideoSerializer(data=video_data, context={'request': request})
                        if serializer.is_valid(raise_exception=True):
                            video = serializer.save(fichier=django_file)
                            video_upload.delete()
                            async_to_sync(channel_layer.group_send)(
                                f"upload_{user.id}_{upload_id}",
                                {
                                    'type': 'upload_progress',
                                    'progress': 100,
                                    'speed': format_file_size(0) + "/s",
                                    'total_duration': format_duration(0),
                                    'remaining_duration': format_duration(0),
                                    'remaining_size': format_file_size(0),
                                    'uploaded_bytes': total_size,
                                    'total_bytes': total_size,
                                    'video_id': video.id,
                                    'status': 'completed'
                                }
                            )
                            video_processing_queue.put(
                                {
                                    "type":"THUMBNAILS",
                                    "video_id":video.id
                                }
                            )        
                            video_processing_queue.put(
                                {
                                    "type":"CONVERSION",
                                    "video_id":video.id
                                }
                            )
                            
                            # Diffusion via WebSocket pour la création de la vidéo
                            async_to_sync(channel_layer.group_send)(
                                "video_updates",
                                {
                                    "type": "video_created",
                                    "video_id": video.id,
                                    "video_data": VideoSerializer(video, context={'request': request}).data
                                }
                            )
                            
                            return Response(serializer.data, status=201)
                        else:
                            return Response(serializer.errors, status=400)
                except Exception as e:
                    print(f"Erreur lors de la recombinaison: {str(e)}")
                    return Response({"error": f"Erreur lors de la recombinaison: {str(e)}"}, status=500)

            return Response({
                "upload_id": upload_id,
                "chunk_number": chunk_number,
                "progress": round(progress, 2)
            }, status=200)

        except Exception as e:
            print(f"Erreur dans ManualVideoChunkUploadView: {str(e)}")
            return Response({"error": str(e)}, status=500)

# class VideoChunkedUploadView(ChunkedUploadView):
#     model = VideoChunkedUpload
#     field_name = 'fichier'

#     def post(self, request, *args, **kwargs):
#         try:
#             request.user = get_user(get_token_from_request(request))
#             return super().post(request, *args, **kwargs)
#         except Exception  as e:
#             print(traceback.format_exc())
#             LOGGER.error(f"Upload error: {str(traceback.format_exc())}")
#             return Response({"erreur":str(e)},status=500)

#     @csrf_exempt
#     def dispatch(self, *args, **kwargs):
#         print("❌ Dispatch..")
#         print("Headers reçus :", dict(self.request.headers))
#         try:
#             return super().dispatch(*args, **kwargs)
#         except Exception as e:
#             print("Erreur dans dispatch :", str(e))
#             return Response({"detail": f"Error in request headers: {str(e)}"}, status=400)

#     def get_extra_attrs_plus(self):
#         if not hasattr(self, '_upload_id'):
#             self._upload_id = str(uuid.uuid4())
#         return {
#             'user': self.request.user,
#             'upload_id': self._upload_id,
#         }

#     def on_completion(self, uploaded_file, request):
#         try:
#             data = request.POST.copy()
#             print(data)
#             data['fichier'] = uploaded_file
#             tags_str = data.get('tags', '')
#             tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
#             data['tags_names'] = tags_list
#             serializer = VideoSerializer(data=data, context={'request': request})
#             if serializer.is_valid():
#                 video = serializer.save()
#                 channel_layer = get_channel_layer()
#                 async_to_sync(channel_layer.group_send)(
#                     f"upload_{request.user.id}_{self.get_extra_attrs_plus()['upload_id']}",
#                     {
#                         'type': 'upload_progress',
#                         'progress': 100,
#                         'speed': 0,
#                         'total_duration': 0,
#                         'remaining_duration': 0,
#                         'remaining_size': 0,
#                         'video_id': video.id,
#                         'status': 'completed'
#                     }
#                 )
#                 return Response(serializer.data, status=201)
#             return Response(serializer.errors, status=400)
#         except Exception as e:
#             print(traceback.format_exc())
#             return Response({"erreur":str(e)},status=500)

#     def get_response_data(self, chunked_upload, request):
#         start_time = chunked_upload.start_time
#         if start_time.tzinfo is None:
#             start_time = start_time.replace(tzinfo=timezone.utc)
#         now = datetime.now(timezone.utc)
#         elapsed_time = (now - start_time).total_seconds()
#         progress = (chunked_upload.offset / chunked_upload.file.size) * 100
#         speed = chunked_upload.offset / elapsed_time if elapsed_time > 0 else 0
#         total_duration = chunked_upload.file.size / speed if speed > 0 else 0
#         remaining_duration = total_duration * (1 - progress / 100)
#         remaining_size = chunked_upload.file.size - chunked_upload.offset
#         channel_layer = get_channel_layer()
#         async_to_sync(channel_layer.group_send)(
#             f"upload_{request.user.id}_{chunked_upload.upload_id}",
#             {
#                 'type': 'upload_progress',
#                 'progress': progress,
#                 'speed': speed,
#                 'total_duration': total_duration,
#                 'remaining_duration': remaining_duration,
#                 'remaining_size': remaining_size,
#                 'status': 'uploading'
#             }
#         )
#         return {'upload_id': chunked_upload.upload_id, 'offset': chunked_upload.offset}


class VideoUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_description="Met à jour une vidéo existante",
        manual_parameters=[
            openapi.Parameter('titre', openapi.IN_FORM, description="Titre de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('description', openapi.IN_FORM, description="Description de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('fichier', openapi.IN_FORM, description="Fichier vidéo", type=openapi.TYPE_FILE, required=False),
            openapi.Parameter('affichage', openapi.IN_FORM, description="Image d'affichage", type=openapi.TYPE_FILE, required=False),
            openapi.Parameter('categorie', openapi.IN_FORM, description="Catégorie de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('tags', openapi.IN_FORM, description="Tags séparés par des virgules", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('visibilite', openapi.IN_FORM, description="Visibilité (PUBLIC ou PRIVATE)", type=openapi.TYPE_STRING, enum=['PUBLIC', 'PRIVATE'], required=False),
            openapi.Parameter('autoriser_commentaire', openapi.IN_FORM, description="Autoriser les commentaires", type=openapi.TYPE_BOOLEAN, required=False),
            openapi.Parameter('ordre_de_commentaire', openapi.IN_FORM, description="Ordre des commentaires (TOP ou NOUVEAUTE)", type=openapi.TYPE_STRING, enum=['TOP', 'NOUVEAUTE'], required=False),
        ],
        responses={
            200: VideoSerializer(),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def put(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            tags_str = request.data.get('tags', '')
            tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            request.data._mutable = True
            request.data['tags_names'] = tags_list
            request.data._mutable = False
            serializer = VideoSerializer(video, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_updated",
                        "video_id": video.id,
                        "video_data": VideoSerializer(video, context={'request': request}).data
                    }
                )
                
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Supprime une vidéo",
        responses={
            204: openapi.Response(
                description="Vidéo supprimée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def delete(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            video_dir = os.path.join(settings.MEDIA_ROOT, "videos", str(video.id))
            original_file_path = os.path.join(settings.MEDIA_ROOT, "videos", os.path.basename(video.fichier.name))

            if hasattr(video, 'video_playlist'):
                video.video_playlist.all().delete()
            if os.path.exists(video.fichier.path):
                os.remove(video.fichier.path)
            if os.path.exists(video.affichage.path):
                os.remove(video.affichage.path)
            video.delete()
            if os.path.exists(video_dir):
                shutil.rmtree(video_dir)
            if os.path.exists(original_file_path) and original_file_path != video.fichier.path:
                os.remove(original_file_path)
                
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "video_updates",
                {
                    "type": "video_deleted",
                    "video_id": video_id
                }
            )
            
            return Response({"message": "Vidéo supprimée"}, status=204)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
        except Exception as e:
            print(f"Erreur lors de la suppression des fichiers : {e}")
            return Response({"error": "Erreur lors de la suppression des fichiers"}, status=500)

# Chaine Views

class ChaineListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste toutes les chaines",
        responses={
            200: ChaineSerializer(many=True),
            400: openapi.Response(
                description="Requête invalide",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        chaines = Chaine.objects.all()
        serializer = ChaineSerializer(chaines, many=True, context={'request': request})
        return Response(serializer.data)

class ChaineDetailView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Récupère les détails d'une chaine spécifique",
        responses={
            200: ChaineSerializer(),
            404: openapi.Response(
                description="Chaine non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, chaine_id):
        try:
            chaine = Chaine.objects.get(id=chaine_id)
            serializer = ChaineSerializer(chaine, context={'request': request})
            return Response(serializer.data)
        except Chaine.DoesNotExist:
            return Response({'error': 'Chaine non trouvée'}, status=404)

class ChaineCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Crée une nouvelle chaine",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'titre': openapi.Schema(type=openapi.TYPE_STRING, description="Titre de la chaine"),
                'description': openapi.Schema(type=openapi.TYPE_STRING, description="Description de la chaine", nullable=True),
            },
            required=['titre']
        ),
        responses={
            201: ChaineSerializer(),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request):
        serializer = ChaineSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

class ChaineUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Met à jour une chaine existante",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'titre': openapi.Schema(type=openapi.TYPE_STRING, description="Titre de la chaine"),
                'description': openapi.Schema(type=openapi.TYPE_STRING, description="Description de la chaine", nullable=True),
            }
        ),
        responses={
            200: ChaineSerializer(),
            404: openapi.Response(
                description="Chaine non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def put(self, request, chaine_id):
        try:
            chaine = Chaine.objects.get(id=chaine_id)
            serializer = ChaineSerializer(chaine, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)
        except Chaine.DoesNotExist:
            return Response({'error': 'Chaine non trouvée'}, status=404)

class ChaineDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Supprime une chaine",
        responses={
            204: openapi.Response(description="Chaine supprimée"),
            404: openapi.Response(
                description="Chaine non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def delete(self, request, chaine_id):
        try:
            chaine = Chaine.objects.get(id=chaine_id)
            chaine.delete()
            return Response(status=204)
        except Chaine.DoesNotExist:
            return Response({'error': 'Chaine non trouvée'}, status=404)

# Comment Views

class CommentListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste des commentaires pour une vidéo, triés par TOP ou NOUVEAUTE",
        responses={
            200: CommentaireSerializer(many=True),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            comments = video.commentaires.all()
            if video.ordre_de_commentaire == 'TOP':
                comments = comments.annotate(message_count=Count('messages')).order_by('-message_count')
            else:
                comments = comments.order_by('-created_at')
            serializer = CommentaireSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class CommentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Crée un commentaire pour une vidéo",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'video': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID de la vidéo"),
                'contenu': openapi.Schema(type=openapi.TYPE_STRING, description="Contenu de message"),
            },
            required=['video']
        ),
        responses={
            201: CommentaireSerializer(),
            403: openapi.Response(
                description="Commentaires désactivés",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            if not video.autoriser_commentaire:
                return Response({'error': 'Les commentaires sont désactivés pour cette vidéo'}, status=403)
            new_commentaire = Commentaire.objects.create(video=video)
            new_commentaire.membres.add(request.user)
            Message.objects.create(commentaire=new_commentaire, envoyeur=request.user, contenu=request.data.get('contenu', ''))
            
            # Diffusion via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "video_updates",
                {
                    "type": "comment_created",
                    "video_id": video_id,
                    "comment_id": new_commentaire.id,
                    "comment_data": CommentaireSerializer(new_commentaire).data,
                    "commentaires": CommentaireSerializer(Commentaire.objects.filter(video=video), many=True, context={"request":request}).data
                }
            )
            
            return Response(CommentaireSerializer(new_commentaire).data, status=201)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
        except Exception as e:
            return Response({'erreur': str(e)}, status=500)

# Message Views

class MessageListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste des messages pour un commentaire, triés par date (plus récent en premier)",
        responses={
            200: MessageSerializer(many=True),
            404: openapi.Response(
                description="Commentaire non trouvé",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, comment_id):
        try:
            comment = Commentaire.objects.get(id=comment_id)
            messages = comment.messages.all().order_by('-created_at')
            serializer = MessageSerializer(messages, many=True, context={'request': request})
            return Response(serializer.data)
        except Commentaire.DoesNotExist:
            return Response({'error': 'Commentaire non trouvé'}, status=404)

class MessageCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Crée un message (réponse) pour un commentaire",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'comment_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID de la commentaire"),
                'contenu': openapi.Schema(type=openapi.TYPE_STRING, description="Contenu du message", nullable=True),
            }
        ),
        responses={
            201: MessageSerializer(),
            404: openapi.Response(
                description="Commentaire non trouvé",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            400: openapi.Response(
                description="Données invalides",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request):
        try:
            comment = Commentaire.objects.get(id=request.data.get('comment_id'))
            serializer = MessageSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save(commentaire=comment, envoyeur=request.user)
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)
        except Commentaire.DoesNotExist:
            return Response({'error': 'Commentaire non trouvé'}, status=404)

# Search and Other Views

class VideoSearchView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Recherche de vidéos par critères",
        manual_parameters=[
            openapi.Parameter('search_term', openapi.IN_QUERY, description="Terme de recherche (titre/description)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('tags', openapi.IN_QUERY, description="Tags séparés par des virgules", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('categorie', openapi.IN_QUERY, description="Catégorie de la vidéo", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('date_filter', openapi.IN_QUERY, description="Filtre de date (recent, today, week, month, year)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Date de début (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="Date de fin (format: YYYY-MM-DD)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('order_by', openapi.IN_QUERY, description="Trier par (likes, dislikes, comments, date)", type=openapi.TYPE_STRING, required=False),
        ],
        responses={
            200: VideoSerializer(many=True),
            400: openapi.Response(
                description="Requête invalide",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        videos = Video.objects.all()

        search_term = request.query_params.get('search_term')
        if search_term:
            videos = videos.filter(titre__icontains=search_term) #| videos.filter(description__icontains=search_term)

        tags = request.query_params.get('tags')
        if tags:
            videos = videos.filter(tags__name__in=tags.split(','))

        categorie = request.query_params.get('categorie')
        if categorie:
            videos = videos.filter(categorie=categorie)

        date_filter = request.query_params.get('date_filter')
        now = django_timezone.now()
        if date_filter == 'today':
            videos = videos.filter(uploaded_at__date=now.date())
        elif date_filter == 'week':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=7))
        elif date_filter == 'month':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=30))
        elif date_filter == 'year':
            videos = videos.filter(uploaded_at__gte=now - timedelta(days=365))
        elif date_filter == 'recent':
            videos = videos.order_by('-uploaded_at')

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            videos = videos.filter(uploaded_at__range=[start_date, end_date])

        order_by = request.query_params.get('order_by')
        if order_by == 'likes':
            videos = videos.annotate(like_count=Count('likes')).order_by('-like_count')
        elif order_by == 'dislikes':
            videos = videos.annotate(dislike_count=Count('dislikes')).order_by('-dislike_count')
        elif order_by == 'comments':
            videos = videos.annotate(comment_count=Count('commentaires')).order_by('-comment_count')
        elif order_by == 'date':
            videos = videos.order_by('-uploaded_at')

        serializer = VideoSerializer(videos, many=True, context={'request': request})
        return Response(serializer.data)

class HistoriqueVuesView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste les vidéos vues par l'utilisateur authentifié, triées par date de vue la plus récente",
        tags=["Historique"],
        responses={
            200: VideoSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            vues = VideoVue.objects.filter(user=request.user).order_by('-created_at')
            videos = [vue.video for vue in vues]
            serializer = VideoSerializer(videos, many=True, context={'request': request})
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class LikedVideosView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste les vidéos aimées par l'utilisateur authentifié, triées par date de like la plus récente",
        tags=["Vidéos"],
        responses={
            200: VideoSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            likes = VideoLike.objects.filter(user=request.user).order_by('-created_at')
            videos = [like.video for like in likes]
            serializer = VideoSerializer(videos, many=True, context={'request': request})
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class DislikedVideosView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste les vidéos dislikées par l'utilisateur authentifié, triées par date de dislike la plus récente",
        tags=["Vidéos"],
        responses={
            200: VideoSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            dislikes = VideoDislike.objects.filter(user=request.user).order_by('-created_at')
            videos = [dislike.video for dislike in dislikes]
            serializer = VideoSerializer(videos, many=True, context={'request': request})
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class RegarderPlusTardListView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste les vidéos marquées 'à regarder plus tard' par l'utilisateur authentifié, triées par date d'ajout la plus récente",
        tags=["Vidéos"],
        responses={
            200: VideoSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            regarder_plus_tard = VideoRegarderPlusTard.objects.filter(user=request.user).order_by('-created_at')
            videos = [rpt.video for rpt in regarder_plus_tard]
            serializer = VideoSerializer(videos, many=True, context={'request': request})
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class RegarderPlusTardMarquerView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Marquer une vidéo 'à regarder plus tard' par l'utilisateur authentifié",
        tags=["Vidéos"],
        responses={
            200: openapi.Response(
                description="Réussi",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def put(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            VideoRegarderPlusTard.objects.create(user=request.user, video=video)
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "video_updates",
                {
                    "type": "watch_later_added",
                    "video_id": video_id,
                    "user_id": request.user.id
                }
            )
            
            return Response({"message": "✅ Vidéo marquée pour regarder plus tard"}, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class SubscribedChainesView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Liste toutes les chaînes auxquelles l'utilisateur authentifié est abonné",
        tags=["Chaînes"],
        responses={
            200: ChaineSerializer(many=True),
            401: openapi.Response(
                description="Non authentifié",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            500: openapi.Response(
                description="Erreur serveur",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"erreur": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request):
        try:
            chaines = Chaine.objects.filter(abonnees=request.user)
            serializer = ChaineSerializer(chaines, many=True, context={'request': request})
            return Response(serializer.data, status=200)
        except Exception as e:
            return Response({"erreur": str(e)}, status=500)

class VideoManifestView(APIView):
    @swagger_auto_schema(
        operation_description="Récupère le fichier manifeste HLS (.m3u8) pour une vidéo spécifique",
        tags=["Streaming"],
        responses={
            200: openapi.Response(
                description="Fichier manifeste HLS",
                content={'application/vnd.apple.mpegurl': {}}
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            return FileResponse(open(os.path.join(settings.MEDIA_ROOT, video.master_manifest_file), 'rb'), content_type='application/vnd.apple.mpegurl')
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoSegmentView(APIView):
    @swagger_auto_schema(
        operation_description="Récupère un segment vidéo spécifique (.ts) pour une vidéo",
        tags=["Streaming"],
        responses={
            200: openapi.Response(
                description="Segment vidéo",
                content={'video/mp4': {}}
            ),
            404: openapi.Response(
                description="Segment ou vidéo non trouvé",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, video_id, segment_name):
        try:
            video = Video.objects.get(id=video_id)
            segment_path = os.path.join(settings.MEDIA_ROOT, "videos", str(video.id), "segments", segment_name)
            if os.path.exists(segment_path):
                return FileResponse(open(segment_path, 'rb'), content_type='video/mp4')
            else:
                return Response({'error': 'Segment non trouvé'}, status=404)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoLikeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Like ou Unlike une vidéo",
        responses={
            200: openapi.Response(
                description="Action réussie",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            user = request.user
            if VideoLike.objects.filter(video=video, user=user).exists():
                VideoLike.objects.filter(video=video, user=user).delete()
                video.likes.remove(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_liked",
                        "video_id": video_id,
                        "user_id": user.id,
                        "action": "Like retiré"
                    }
                )
                
                return Response({"message": "Like retiré"}, status=200)
            else:
                VideoLike.objects.create(video=video, user=user)
                video.likes.add(user)
                VideoDislike.objects.filter(video=video, user=user).delete()
                video.dislikes.remove(user)
                
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_liked",
                        "video_id": video_id,
                        "user_id": user.id,
                        "action": "Like ajouté",
                        "video": VideoSerializer(video, context={"request":request}).data
                    }
                )
                
                return Response({"message": "Like ajouté"}, status=200)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoDislikeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Dislike ou Undislike une vidéo",
        responses={
            200: openapi.Response(
                description="Action réussie",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            user = request.user
            if VideoDislike.objects.filter(video=video, user=user).exists():
                VideoDislike.objects.filter(video=video, user=user).delete()
                video.dislikes.remove(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_disliked",
                        "video_id": video_id,
                        "user_id": user.id,
                        "action": "Dislike retiré"
                    }
                )
                
                return Response({"message": "Dislike retiré"}, status=200)
            else:
                VideoDislike.objects.create(video=video, user=user)
                video.dislikes.add(user)
                VideoLike.objects.filter(video=video, user=user).delete()
                video.likes.remove(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_disliked",
                        "video_id": video_id,
                        "user_id": user.id,
                        "action": "Dislike ajouté",
                        "video":VideoSerializer(video, context={"request":request}).data
                    }
                )
                
                return Response({"message": "Dislike ajouté"}, status=200)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class ChaineSubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="S'abonner ou se désabonner d'une chaîne",
        responses={
            200: openapi.Response(
                description="Action réussie",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Chaîne non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, chaine_id):
        try:
            chaine = Chaine.objects.get(id=chaine_id)
            user = request.user
            if chaine.abonnees.filter(id=user.id).exists():
                chaine.abonnees.remove(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "channel_subscribed",
                        "channel_id": chaine_id,
                        "user_id": user.id,
                        "action": "Désabonné"
                    }
                )
                
                return Response({"message": "Désabonné"}, status=200)
            else:
                chaine.abonnees.add(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "channel_subscribed",
                        "channel_id": chaine_id,
                        "user_id": user.id,
                        "action": "Abonné",
                        "chaine":ChaineSerializer(chaine, context={"request":request}).data
                    }
                )
                
                return Response({"message": "Abonné"}, status=200)
        except Chaine.DoesNotExist:
            return Response({'error': 'Chaîne non trouvée'}, status=404)

class VideoViewView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Marquer une vidéo comme vue",
        responses={
            200: openapi.Response(
                description="Vidéo marquée comme vue",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"message": openapi.Schema(type=openapi.TYPE_STRING)})
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def post(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            user = request.user
            if not VideoVue.objects.filter(video=video, user=user).exists():
                VideoVue.objects.create(video=video, user=user)
                video.vues.add(user)
                
                # Diffusion via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "video_updates",
                    {
                        "type": "video_viewed",
                        "video_id": video_id,
                        "user_id": user.id,
                        "video":VideoSerializer(video, context={"request":request}).data,
                        "videos": VideoSerializer(Video.objects.all(),many=True, context={"request":request}).data,
                        "my_videos": VideoSerializer(Video.objects.filter(envoyeur=request.user),many=True, context={"request":request}).data
                    }
                )
                
                return Response({"message": "Vidéo marquée comme vue"}, status=200)
            else:
                return Response({"message": "Vidéo déjà vue"}, status=200)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

class VideoDownloadView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Récupère les informations de téléchargement pour une vidéo spécifique, incluant les qualités disponibles, leurs URLs directes, tailles et durées",
        tags=["Téléchargements"],
        responses={
            200: openapi.Response(
                description="Liste des qualités disponibles pour le téléchargement",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "qualities": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "quality": openapi.Schema(type=openapi.TYPE_STRING, description="Qualité de la vidéo (e.g., 1080p, 720p)"),
                                    "url": openapi.Schema(type=openapi.TYPE_STRING, description="URL directe pour le téléchargement"),
                                    "size": openapi.Schema(type=openapi.TYPE_STRING, description="Taille du fichier formatée"),
                                    "duration": openapi.Schema(type=openapi.TYPE_STRING, description="Durée de la vidéo formatée"),
                                }
                            )
                        )
                    }
                )
            ),
            404: openapi.Response(
                description="Vidéo non trouvée",
                schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={"error": openapi.Schema(type=openapi.TYPE_STRING)})
            )
        }
    )
    def get(self, request, video_id):
        try:
            video = Video.objects.get(id=video_id)
            video_path = video.fichier.path
            video_info = get_available_info(video_path)
            qualities = video_info.get('qualities', [])
            duration = video_info.get('duration_formatted', 'N/A')
            base_url = settings.BASE_URL
            media_url = settings.MEDIA_URL
            original_filename = os.path.basename(video_path)
            qualities_list = []
            for quality in qualities:
                if quality == video_info.get('quality',None):
                    quality_file_path = os.path.join("videos", str(video.id), original_filename)
                else:
                    quality_file_path = os.path.join("videos", str(video.id), "qualities", quality, original_filename)
                quality_url = f"{base_url}{media_url}{quality_file_path}"
                full_path = os.path.join(settings.MEDIA_ROOT, quality_file_path)
                size = format_file_size(os.path.getsize(full_path)) if os.path.exists(full_path) else "N/A"
                qualities_list.append({
                    "quality": quality,
                    "url": quality_url,
                    "taille": size,
                    "duration": duration
                })
            return Response({"qualities": qualities_list}, status=200)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
