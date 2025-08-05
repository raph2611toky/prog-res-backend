import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.videos.routing import video_websocket_urlpatterns
from apps.streaming.routing import streaming_websocket_urlpatterns
from helpers.middleware import TokenAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": TokenAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(
                video_websocket_urlpatterns + streaming_websocket_urlpatterns
            )
        )
    ),
})