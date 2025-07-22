from django.urls import path
from apps.videos.views import (
    VideoListView, VideoDetailView, VideoCreateView, VideoUpdateView, VideoDeleteView,TagCreateView,
    PlaylistListView, PlaylistDetailView, PlaylistCreateView, PlaylistUpdateView, PlaylistDeleteView,
    CommentListView, CommentCreateView, MessageListView, MessageCreateView, VideoSearchView,
)

urlpatterns = [
    path('videos/', VideoListView.as_view(), name='video-list'),
    path('videos/<int:video_id>/', VideoDetailView.as_view(), name='video-detail'),
    path('videos/create/', VideoCreateView.as_view(), name='video-create'),
    path('tags/create/', TagCreateView.as_view(), name='tags-create'),
    path('videos/<int:video_id>/update/', VideoUpdateView.as_view(), name='video-update'),
    path('videos/<int:video_id>/delete/', VideoDeleteView.as_view(), name='video-delete'),
    path('videos/search/', VideoSearchView.as_view(), name='video-search'),

    path('playlists/', PlaylistListView.as_view(), name='playlist-list'),
    path('playlists/<int:playlist_id>/', PlaylistDetailView.as_view(), name='playlist-detail'),
    path('playlists/create/', PlaylistCreateView.as_view(), name='playlist-create'),
    path('playlists/<int:playlist_id>/update/', PlaylistUpdateView.as_view(), name='playlist-update'),
    path('playlists/<int:playlist_id>/delete/', PlaylistDeleteView.as_view(), name='playlist-delete'),

    path('videos/<int:video_id>/comments/', CommentListView.as_view(), name='comment-list'),
    path('videos/<int:video_id>/comments/create/', CommentCreateView.as_view(), name='comment-create'),

    path('comments/<int:comment_id>/messages/', MessageListView.as_view(), name='message-list'),
    path('comments/<int:comment_id>/messages/create/', MessageCreateView.as_view(), name='message-create'),
]