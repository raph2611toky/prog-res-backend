from django.urls import path
from apps.videos.views import (
    VideoListView, VideoDetailView, VideoCreateView, VideoUpdateView, VideoDeleteView, TagCreateView,
    ChaineListView, ChaineDetailView, ChaineCreateView, ChaineUpdateView, ChaineDeleteView,
    CommentListView, CommentCreateView, MessageListView, MessageCreateView, VideoSearchView, VideoChunkedUploadView,
    LikedVideosView, SubscribedChainesView, HistoriqueVuesView, DislikedVideosView, RegarderPlusTardListView,
    RegarderPlusTardMarquerView,
)

urlpatterns = [
    path('videos/', VideoListView.as_view(), name='video-list'),
    path('videos/<int:video_id>/', VideoDetailView.as_view(), name='video-detail'),
    path('videos/create/', VideoCreateView.as_view(), name='video-create'),
    path('videos/upload/', VideoChunkedUploadView.as_view(), name='video-upload'),
    path('tags/create/', TagCreateView.as_view(), name='tags-create'),
    path('videos/<int:video_id>/update/', VideoUpdateView.as_view(), name='video-update'),
    path('videos/<int:video_id>/delete/', VideoDeleteView.as_view(), name='video-delete'),
    path('videos/search/', VideoSearchView.as_view(), name='video-search'),

    path('chaines/', ChaineListView.as_view(), name='chaine-list'),
    path('chaines/<int:chaine_id>/', ChaineDetailView.as_view(), name='chaine-detail'),
    path('chaines/create/', ChaineCreateView.as_view(), name='chaine-create'),
    path('chaines/<int:chaine_id>/update/', ChaineUpdateView.as_view(), name='chaine-update'),
    path('chaines/<int:chaine_id>/delete/', ChaineDeleteView.as_view(), name='chaine-delete'),

    path('videos/<int:video_id>/comments/', CommentListView.as_view(), name='comment-list'),
    path('videos/<int:video_id>/comments/create/', CommentCreateView.as_view(), name='comment-create'),

    path('comments/<int:comment_id>/messages/', MessageListView.as_view(), name='message-list'),
    path('comments/<int:comment_id>/messages/create/', MessageCreateView.as_view(), name='message-create'),
    
    path('historique/vues/', HistoriqueVuesView.as_view(), name='historique-vues'),
    path('videos/liked/', LikedVideosView.as_view(), name='liked-videos'),
    path('videos/disliked/', DislikedVideosView.as_view(), name='disliked-videos'),
    path('videos/regarder-plus-tard/list/', RegarderPlusTardListView.as_view(), name='regarder-plus-tard-list'),
    path('videos/regarder-plus-tard/marquer/', RegarderPlusTardMarquerView.as_view(), name='marquer-un-video-a-regarder-plus-tard'),
    path('chaines/subscribed/', SubscribedChainesView.as_view(), name='subscribed-chaines'),
]