from django.urls import path
from apps.videos import views

app_name = 'videos'

urlpatterns = [
    path('tags/', views.TagCreateView.as_view(), name='tag-create'),

    path('playlists/chaine/<int:chaine_id>/', views.PlaylistListView.as_view(), name='playlist-list'),
    path('playlists/user/', views.UserPlaylistListView.as_view(), name='user-playlist-list'),
    path('playlists/<int:playlist_id>/', views.PlaylistDetailView.as_view(), name='playlist-detail'),
    path('playlists/create/', views.PlaylistCreateView.as_view(), name='playlist-create'),
    path('playlists/<int:playlist_id>/update/', views.PlaylistUpdateView.as_view(), name='playlist-update'),
    path('playlists/<int:playlist_id>/delete/', views.PlaylistDeleteView.as_view(), name='playlist-delete'),

    path('videos/', views.VideoListView.as_view(), name='video-list'),
    path('videos/mes/', views.MyVideoListView.as_view(), name='my-video-list'),
    path('videos/<int:video_id>/', views.VideoDetailView.as_view(), name='video-detail'),
    path('videos/<str:code_id>/details/', views.VideoDetailByCodeIdView.as_view(), name='video-detail-by-code'),
    path('videos/create/', views.VideoCreateView.as_view(), name='video-create'),
    path('videos/chunked-upload/', views.ManualVideoChunkUploadView.as_view(), name='video-chunked-upload'),
    # path('videos/chunked-upload/', views.VideoChunkedUploadView.as_view(), name='video-chunked-upload'),
    path('videos/<int:video_id>/update/', views.VideoUpdateView.as_view(), name='video-update'),
    path('videos/<int:video_id>/delete/', views.VideoDeleteView.as_view(), name='video-delete'),
    path('videos/<int:video_id>/like/', views.VideoLikeView.as_view(), name='video-like'),
    path('videos/<int:video_id>/dislike/', views.VideoDislikeView.as_view(), name='video-dislike'),
    path('videos/<int:video_id>/view/', views.VideoViewView.as_view(), name='video-view'),
    path('videos/<int:video_id>/download/', views.VideoDownloadView.as_view(), name='video-download'),
    path('videos/<int:video_id>/manifest/', views.VideoManifestView.as_view(), name='video-manifest'),
    path('videos/<int:video_id>/segments/<str:segment_name>/', views.VideoSegmentView.as_view(), name='video-segment'),

    path('chaines/', views.ChaineListView.as_view(), name='chaine-list'),
    path('chaines/<int:chaine_id>/', views.ChaineDetailView.as_view(), name='chaine-detail'),
    path('chaines/create/', views.ChaineCreateView.as_view(), name='chaine-create'),
    path('chaines/<int:chaine_id>/update/', views.ChaineUpdateView.as_view(), name='chaine-update'),
    path('chaines/<int:chaine_id>/delete/', views.ChaineDeleteView.as_view(), name='chaine-delete'),
    path('chaines/<int:chaine_id>/subscribe/', views.ChaineSubscribeView.as_view(), name='chaine-subscribe'),
    path('chaines/subscribed/', views.SubscribedChainesView.as_view(), name='subscribed-chaines'),

    path('videos/<int:video_id>/comments/', views.CommentListView.as_view(), name='comment-list'),
    path('videos/<int:video_id>/comments/create/', views.CommentCreateView.as_view(), name='comment-create'),

    path('comments/<int:comment_id>/messages/', views.MessageListView.as_view(), name='message-list'),
    path('messages/create/', views.MessageCreateView.as_view(), name='message-create'),

    path('videos/search/', views.VideoSearchView.as_view(), name='video-search'),
    path('historique/vues/', views.HistoriqueVuesView.as_view(), name='historique-vues'),
    path('videos/liked/', views.LikedVideosView.as_view(), name='liked-videos'),
    path('videos/disliked/', views.DislikedVideosView.as_view(), name='disliked-videos'),
    path('videos/watch-later/', views.RegarderPlusTardListView.as_view(), name='watch-later-list'),
    path('videos/<int:video_id>/watch-later/', views.RegarderPlusTardMarquerView.as_view(), name='watch-later-mark'),
]
