from channels.generic.websocket import AsyncWebsocketConsumer
import json
from asgiref.sync import sync_to_async
from django.http import HttpRequest
from django.utils import timezone as django_timezone
from django.db.models import Count
from datetime import timedelta
from apps.videos.models import Video
from apps.videos.serializers import VideoSerializer
from helpers.helper import format_file_size, format_duration
from django.contrib.auth.models import AnonymousUser

class UploadProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        upload_id = self.scope['url_route']['kwargs']['upload_id']
        user = self.scope['user']

        if user is not None and not isinstance(user, AnonymousUser) and user.is_authenticated:
            self.group_name = f"upload_{user.id}_{upload_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"✅ Connected to {self.group_name}")
        else:
            await self.close()
            print("❌ Connection rejected: User not authenticated")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            print(f"Disconnected from {self.group_name}")

    async def upload_progress(self, event):
        await self.send(text_data=json.dumps({
            'progress': round(event['progress'], 2),
            'speed': event['speed'],
            'total_duration': event['total_duration'],
            'remaining_duration': event['remaining_duration'],
            'remaining_size': event['remaining_size'],
            'uploaded_bytes': event['uploaded_bytes'], 
            'total_bytes': event['total_bytes'], 
            'status': event['status'],
            'video_id': event.get('video_id', None)
        }))

class VideoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("ℹ️ Connecté video consumers ....")

    async def disconnect(self, close_code):
        print("[❗] Deconnecté video consumers ....")
        pass

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
            return

        if message_type == "list_videos":
            await self.handle_list_videos(data)
        elif message_type == "list_my_videos":
            await self.handle_list_my_videos(data)
        elif message_type == "get_video_by_id":
            await self.handle_get_video_by_id(data)
        elif message_type == "get_video_by_code":
            await self.handle_get_video_by_code(data)
        else:
            await self.send_error("Invalid message type")

    async def handle_list_videos(self, data):
        params = data.get('params', {})
        user = self.scope['user']
        video_data = await get_video_list(params, user)
        await self.send_success(video_data)

    async def handle_list_my_videos(self, data):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.send_error("Authentication required")
            return
        params = data.get('params', {})
        video_data = await get_my_video_list(params, user)
        await self.send_success(video_data)

    async def handle_get_video_by_id(self, data):
        video_id = data.get('video_id')
        if not video_id:
            await self.send_error("Video ID required")
            return
        video_data = await get_video_detail_by_id(video_id, self.scope['user'])
        if video_data:
            await self.send_success(video_data)
        else:
            await self.send_error("Video not found")

    async def handle_get_video_by_code(self, data):
        code_id = data.get('code_id')
        if not code_id:
            await self.send_error("Code ID required")
            return
        video_data = await get_video_detail_by_code(code_id, self.scope['user'])
        if video_data:
            await self.send_success(video_data)
        else:
            await self.send_error("Video not found")

    async def send_success(self, data):
        await self.send(text_data=json.dumps({
            "status": "success",
            "data": data
        }))

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            "status": "error",
            "message": message
        }))

@sync_to_async
def get_video_list(params, user):
    videos = Video.objects.all()
    videos = apply_filters(videos, params)
    dummy_request = HttpRequest()
    dummy_request.user = user
    serializer = VideoSerializer(videos, many=True, context={'request': dummy_request, "with_suggestion": False})
    return serializer.data

@sync_to_async
def get_my_video_list(params, user):
    videos = Video.objects.filter(envoyeur=user)
    videos = apply_filters(videos, params)
    dummy_request = HttpRequest()
    dummy_request.user = user
    serializer = VideoSerializer(videos, many=True, context={'request': dummy_request, "with_suggestion": False})
    return serializer.data

@sync_to_async
def get_video_detail_by_id(video_id, user):
    try:
        video = Video.objects.get(id=video_id)
        dummy_request = HttpRequest()
        dummy_request.user = user
        serializer = VideoSerializer(video, context={'request': dummy_request})
        return serializer.data
    except Video.DoesNotExist:
        return None

@sync_to_async
def get_video_detail_by_code(code_id, user):
    try:
        video = Video.objects.get(code_id=code_id)
        dummy_request = HttpRequest()
        dummy_request.user = user
        serializer = VideoSerializer(video, context={'request': dummy_request})
        return serializer.data
    except Video.DoesNotExist:
        return None

def apply_filters(videos, params):
    tags = params.get('tags')
    if tags:
        videos = videos.filter(tags__name__in=tags.split(','))

    categorie = params.get('categorie')
    if categorie:
        videos = videos.filter(categorie=categorie)

    date_filter = params.get('date_filter')
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

    start_date = params.get('start_date')
    end_date = params.get('end_date')
    if start_date and end_date:
        videos = videos.filter(uploaded_at__range=[start_date, end_date])

    order_by = params.get('order_by')
    if order_by == 'likes':
        videos = videos.annotate(like_count=Count('likes')).order_by('-like_count')
    elif order_by == 'dislikes':
        videos = videos.annotate(dislike_count=Count('dislikes')).order_by('-dislike_count')
    elif order_by == 'comments':
        videos = videos.annotate(comment_count=Count('commentaires')).order_by('-comment_count')
    elif order_by == 'date':
        videos = videos.order_by('-uploaded_at')

    return videos