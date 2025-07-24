from django.urls import re_path
from apps.streaming import consumers

streaming_websocket_urlpatterns = [
    re_path(r'ws/videowatch/(?P<video_id>[^/]+)/$', consumers.VideoWatchConsumer.as_asgi()),
]