from rest_framework import serializers
from .models import Tag, Video, Playlist, Commentaire, Message, VideoPlaylist
from apps.users.serializers import UserSerializer
from django.utils.text import slugify
from django.conf import settings
from helpers.helper import calcule_de_similarite_de_phrase
from django.db.models import Count
from django.db.models import Max

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']
    
    def validate_name(self, value):
        return slugify(value).replace('-', '')

class MessageSerializer(serializers.ModelSerializer):
    envoyeur = UserSerializer(read_only=True)
    likes_count = serializers.SerializerMethodField()
    dislikes_count = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'commentaire', 'envoyeur', 'contenu', 'likes_count',
            'dislikes_count', 'created_at'
        ]

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_dislikes_count(self, obj):
        return obj.dislikes.count()

class CommentaireSerializer(serializers.ModelSerializer):
    membres = UserSerializer(many=True, read_only=True)
    membre_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    message = serializers.SerializerMethodField()
    reponses = serializers.SerializerMethodField()
    reponses_count = serializers.SerializerMethodField()

    class Meta:
        model = Commentaire
        fields = ['id', 'video', 'membres', 'membre_ids', 'created_at', 'message', 'reponses', 'reponses_count']
        
    def get_message(self, obj):
        if obj.messages.exists():
            return MessageSerializer(obj.messages.first()).data
        return None
    
    def get_reponses(self, obj):
        if obj.messages.count() > 1:
            return MessageSerializer(obj.messages.all()[1:], many=True).data
        return []
    
    def get_reponses_count(self, obj):
        return max(0, obj.messages.count() - 1)

    def create(self, validated_data):
        membre_ids = validated_data.pop('membre_ids', None)
        commentaire = Commentaire.objects.create(**validated_data)
        
        if membre_ids:
            commentaire.membres.set(membre_ids)
        
        return commentaire

class VideoPlaylistSerializer(serializers.ModelSerializer):
    video = serializers.PrimaryKeyRelatedField(queryset=Video.objects.all())
    playlist = serializers.PrimaryKeyRelatedField(queryset=Playlist.objects.all())

    class Meta:
        model = VideoPlaylist
        fields = ['id', 'playlist', 'video', 'ordre']

class VideoSerializer(serializers.ModelSerializer):
    envoyeur = UserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    playlist_id = serializers.IntegerField(write_only=True, required=False)
    playlist = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    dislikes_count = serializers.SerializerMethodField()
    vues_count = serializers.SerializerMethodField()
    fichier_url = serializers.SerializerMethodField()
    affichage_url = serializers.SerializerMethodField()
    suggested_videos = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            'id', 'titre', 'description', 'fichier_url', 'affichage_url', 'envoyeur',
            'dans_un_playlist', 'categorie', 'tags', 'tag_ids', 'playlist_id', 'playlist', 'visibilite',
            'autoriser_commentaire', 'ordre_de_commentaire', 'likes_count', 'dislikes_count',
            'vues_count', 'uploaded_at', 'updated_at', 'suggested_videos'
        ]
    
    def get_fichier_url(self, obj):
        return f"{settings.BASE_URL}{obj.fichier.url}" if obj.fichier else None
    
    def get_affichage_url(self, obj):
        return f"{settings.BASE_URL}{obj.affichage.url}" if obj.affichage else None

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_dislikes_count(self, obj):
        return obj.dislikes.count()

    def get_vues_count(self, obj):
        return obj.vues.count()

    def get_playlist(self, obj):
        if obj.dans_un_playlist and hasattr(obj, 'videos_playlist'):
            video_playlist = obj.videos_playlist
            return PlaylistSerializer(video_playlist.playlist).data
        return None

    def get_suggested_videos(self, obj):
        suggested = []
        
        if obj.dans_un_playlist and hasattr(obj, 'videos_playlist'):
            video_playlist = obj.videos_playlist
            playlist = video_playlist.playlist
            next_videos = VideoPlaylist.objects.filter(
                playlist=playlist, ordre__gt=video_playlist.ordre
            ).order_by('ordre')[:3]
            suggested.extend([vp.video for vp in next_videos])

        all_videos = Video.objects.exclude(id=obj.id)
        similarity_scores = [
            (video, calcule_de_similarite_de_phrase(obj.titre + " " + obj.description, video.titre + " " + video.description))
            for video in all_videos
        ]
        similarity_scores.sort(key=lambda x: x[1], reverse=True)
        suggested.extend([video for video, score in similarity_scores[:3]])

        tag_related = Video.objects.filter(tags__in=obj.tags.all()).exclude(id=obj.id).distinct()[:3]
        suggested.extend(tag_related)

        category_related = Video.objects.filter(categorie=obj.categorie).exclude(id=obj.id)[:3]
        suggested.extend(category_related)

        suggested = list(dict.fromkeys(suggested))[:5]
        return VideoSerializer(suggested, many=True, context=self.context).data

    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        playlist_id = validated_data.pop('playlist_id', None)
        validated_data['envoyeur'] = self.context['request'].user
        video = Video.objects.create(**validated_data)

        if tag_ids:
            video.tags.set(tag_ids)
        if playlist_id:
            playlist = Playlist.objects.get(id=playlist_id)
            max_ordre = VideoPlaylist.objects.filter(playlist=playlist).aggregate(Max('ordre'))['ordre__max'] or 0
            VideoPlaylist.objects.create(playlist=playlist, video=video, ordre=max_ordre + 1)
            video.dans_un_playlist = True
            video.save()
        
        return video

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        playlist_id = validated_data.pop('playlist_id', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tag_ids:
            instance.tags.set(tag_ids)
        if playlist_id:
            playlist = Playlist.objects.get(id=playlist_id)
            if not hasattr(instance, 'videos_playlist') or instance.videos_playlist.playlist != playlist:
                if hasattr(instance, 'videos_playlist'):
                    instance.videos_playlist.delete()
                max_ordre = VideoPlaylist.objects.filter(playlist=playlist).aggregate(Max('ordre'))['ordre__max'] or 0
                VideoPlaylist.objects.create(playlist=playlist, video=instance, ordre=max_ordre + 1)
                instance.dans_un_playlist = True
                instance.save()
        
        return instance
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request", None)
        if request is not None:
            user = request.user
            representation['is_liked_by_me'] = user.id in [u.id for u in instance.likes.all()]
            representation['is_disliked_by_me'] = user.id in [u.id for u in instance.dislikes.all()]
            representation['is_view_by_me'] = user.id in [u.id for u in instance.vues.all()]
        if instance.autoriser_commentaire:
            commentaires = instance.commentaires.all()
            if instance.ordre_de_commentaire == 'TOP':
                commentaires = commentaires.annotate(message_count=Count('messages')).order_by('-message_count')
            else:
                commentaires = commentaires.order_by('-created_at')
            representation["commentaires"] = CommentaireSerializer(commentaires, many=True).data
        return representation

class PlaylistSerializer(serializers.ModelSerializer):
    videos = serializers.SerializerMethodField()
    video_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Playlist
        fields = ['id', 'titre', 'description', 'visibilite', 'videos', 'video_ids', 'created_at']

    def get_videos(self, obj):
        video_playlists = VideoPlaylist.objects.filter(playlist=obj).order_by('ordre')
        return VideoSerializer([vp.video for vp in video_playlists], many=True, context=self.context).data

    def create(self, validated_data):
        video_ids = validated_data.pop('video_ids', None)
        playlist = Playlist.objects.create(**validated_data)
        
        if video_ids:
            for index, video_id in enumerate(video_ids):
                video = Video.objects.get(id=video_id)
                VideoPlaylist.objects.create(playlist=playlist, video=video, ordre=index + 1)
                video.dans_un_playlist = True
                video.save()
        
        return playlist

    def update(self, instance, validated_data):
        video_ids = validated_data.pop('video_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if video_ids is not None:
            VideoPlaylist.objects.filter(playlist=instance).delete()
            for index, video_id in enumerate(video_ids):
                video = Video.objects.get(id=video_id)
                VideoPlaylist.objects.create(playlist=instance, video=video, ordre=index + 1)
                video.dans_un_playlist = True
                video.save()
        
        return instance