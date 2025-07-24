from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.videos.models import Video, Chaine, VideoChaine, Commentaire, Message, Tag, VideoVue, VideoLike, VideoDislike, VideoRegarderPlusTard
from apps.videos.serializers import VideoSerializer, ChaineSerializer, CommentaireSerializer, MessageSerializer, TagSerializer
from apps.videos.tasks import process_video_conversion, generate_video_affichage

from drf_yasg.utils import swagger_auto_schema
from chunked_upload.views import ChunkedUploadView
from chunked_upload.models import ChunkedUpload
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from drf_yasg import openapi
from datetime import datetime

from helpers.helper import LOGGER, get_token_from_request, get_user

from django.db.models import Count
from django.db.models import Max
from django.utils import timezone as django_timezone
from django.http import FileResponse
from django.views.decorators.csrf import csrf_exempt

from datetime import timedelta, timezone
import uuid, time, os
from queue import Queue
from threading import Thread

################################# WORKER #################################


video_conversion_queue = Queue()
video_affichage_queue = Queue()

def video_conversion_worker():
    while True:
        video_id = video_conversion_queue.get()
        print("[!] 🎊 [!] 🎊 Video conversion", video_id)
        try:
            print("[!] 🎊 Worker traite vidéo ID: %s", video_id)
            process_video_conversion(video_id)
        except Exception as e:
            print("[❌] Erreur dans le worker pour vidéo ID: %s - %s", video_id, str(e))
        finally:
            video_conversion_queue.task_done()
            
def video_affichage_worker():
    while True:
        video_id = video_affichage_queue.get()
        print("[!] 🖼️ Worker génère image pour vidéo ID:", video_id)
        try:
            generate_video_affichage(video_id)
        except Exception as e:
            print("[❌] Erreur dans le worker pour image ID:", video_id, str(e))
        finally:
            video_affichage_queue.task_done()

worker_thread = Thread(target=video_conversion_worker, daemon=True)
worker_thread.start()

affichage_worker_thread = Thread(target=video_affichage_worker, daemon=True)
affichage_worker_thread.start()

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

# Vues pour les Vidéos

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

        serializer = VideoSerializer(videos, many=True, context={'request': request, "with_suggestion":False})
        return Response(serializer.data)

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
            openapi.Parameter('chaine_id', openapi.IN_FORM, description="ID de la chaine", type=openapi.TYPE_INTEGER, required=False),
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
            video_conversion_queue.put(video.id)
            video_affichage_queue.put(video.id)
            
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

class VideoChunkedUploadView(ChunkedUploadView):
    model = ChunkedUpload
    field_name = 'fichier'

    def post(self, request, *args, **kwargs):
        request.user = get_user(get_token_from_request(request))
        return super().post(request, *args, **kwargs)

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_extra_attrs_plus(self):
        if not hasattr(self, '_upload_id'):
            self._upload_id = str(uuid.uuid4())
        return {
            'user': self.request.user,
            'upload_id': self._upload_id,
        }

    def on_completion(self, uploaded_file, request):
        data = request.POST.copy()
        data['fichier'] = uploaded_file
        tags_str = data.get('tags', '')
        tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        data['tags_names'] = tags_list
        serializer = VideoSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            video = serializer.save()
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"upload_{request.user.id}_{self.get_extra_attrs_plus()['upload_id']}",
                {
                    'type': 'upload_progress',
                    'progress': 100,
                    'speed': 0,
                    'total_duration': 0,
                    'remaining_duration': 0,
                    'remaining_size': 0,
                    'video_id': video.id,
                    'status': 'completed'
                }
            )
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def get_response_data(self, chunked_upload, request):
        start_time = chunked_upload.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        elapsed_time = (now - start_time).total_seconds()
        progress = (chunked_upload.offset / chunked_upload.file.size) * 100
        speed = chunked_upload.offset / elapsed_time if elapsed_time > 0 else 0
        total_duration = chunked_upload.file.size / speed if speed > 0 else 0
        remaining_duration = total_duration * (1 - progress / 100)
        remaining_size = chunked_upload.file.size - chunked_upload.offset
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"upload_{request.user.id}_{chunked_upload.upload_id}",
            {
                'type': 'upload_progress',
                'progress': progress,
                'speed': speed,
                'total_duration': total_duration,
                'remaining_duration': remaining_duration,
                'remaining_size': remaining_size,
                'status': 'uploading'
            }
        )
        return {'upload_id': chunked_upload.upload_id, 'offset': chunked_upload.offset}

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
            openapi.Parameter('chaine_id', openapi.IN_FORM, description="ID de la chaine", type=openapi.TYPE_INTEGER, required=False),
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
            if hasattr(video, 'videos_chaine'):
                video.videos_chaine.delete()
            video.delete()
            return Response({"message": "Video supprimé"}, status=204)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)

# Vues pour les Chaines

class ChaineListView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Liste toutes les chaines",
        manual_parameters=[
            openapi.Parameter('visibilite', openapi.IN_QUERY, description="Filtrage par visibilité (PUBLIC ou PRIVATE)", type=openapi.TYPE_STRING, enum=['PUBLIC', 'PRIVATE'], required=False),
        ],
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
        visibilite = request.query_params.get('visibilite')
        if visibilite:
            chaines = chaines.filter(visibilite=visibilite)
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
                'visibilite': openapi.Schema(type=openapi.TYPE_STRING, description="Visibilité (PUBLIC ou PRIVATE)", enum=['PUBLIC', 'PRIVATE']),
                'video_ids': openapi.Schema(type=openapi.TYPE_ARRAY, description="Liste des IDs des vidéos", items=openapi.Items(type=openapi.TYPE_INTEGER), nullable=True),
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
                'visibilite': openapi.Schema(type=openapi.TYPE_STRING, description="Visibilité (PUBLIC ou PRIVATE)", enum=['PUBLIC', 'PRIVATE']),
                'video_ids': openapi.Schema(type=openapi.TYPE_ARRAY, description="Liste des IDs des vidéos", items=openapi.Items(type=openapi.TYPE_INTEGER), nullable=True),
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
            for vp in VideoChaine.objects.filter(chaine=chaine):
                vp.video.dans_un_chaine = False
                vp.video.save()
            chaine.delete()
            return Response(status=204)
        except Chaine.DoesNotExist:
            return Response({'error': 'Chaine non trouvée'}, status=404)

# Vues pour les Commentaires

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
            return Response(CommentaireSerializer(new_commentaire).data, status=201)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
        except Exception as e:
            return Response({'erreur': str(e)}, status=500)

# Vues pour les Messages

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

# Vue de Recherche

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
            videos = videos.filter(titre__icontains=search_term) | videos.filter(description__icontains=search_term)

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
        operation_description="Marqué un video 'à regarder plus tard' par l'utilisateur authentifié",
        tags=["Vidéos"],
        responses={
            200: openapi.Response(
                description="Reussi",
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
            return Response({"message":"✅Video marqué pour regarder plus tard"}, status=200)
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
            return FileResponse(open(video.master_manifest_file.path, 'rb'), content_type='application/vnd.apple.mpegurl')
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
            segment_path = os.path.join(video.segments_dir, segment_name)
            if os.path.exists(segment_path):
                return FileResponse(open(segment_path, 'rb'), content_type='video/mp4')
            else:
                return Response({'error': 'Segment non trouvé'}, status=404)
        except Video.DoesNotExist:
            return Response({'error': 'Vidéo non trouvée'}, status=404)
