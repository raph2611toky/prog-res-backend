from django.urls import re_path
from apps.videos import consumers

video_websocket_urlpatterns = [
    re_path(r'ws/upload/(?P<upload_id>[^/]+)/$', consumers.UploadProgressConsumer.as_asgi()),
    re_path(r'ws/videos/$', consumers.VideoConsumer.as_asgi()),
]