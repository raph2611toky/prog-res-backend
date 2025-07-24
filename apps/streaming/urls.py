from django.urls import path
from apps.streaming.views import VideoWatchUpdateView

urlpatterns = [
    path('videos/<int:video_id>/watch/', VideoWatchUpdateView.as_view(), name='video_watch_update'),
]