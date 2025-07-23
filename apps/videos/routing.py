from django.urls import re_path
from apps.videos import consumers

websocket_urlpatterns = [
    re_path(r'ws/upload/(?P<upload_id>[^/]+)/$', consumers.UploadProgressConsumer.as_asgi()),
]