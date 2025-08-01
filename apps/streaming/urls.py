from django.urls import path
from apps.streaming.views import VideoWatchUpdateView

urlpatterns = [
    path('videowatch/<uuid:code_id>/', VideoWatchUpdateView.as_view(), name='video_watch_update'),
]