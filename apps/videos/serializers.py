from rest_framework import serializers
from .models import Tag, Video, Chaine, Commentaire, Message, Playlist, VideoPlaylist, VideoProcessingTask
from apps.users.serializers import UserSerializer
from django.utils.text import slugify
from apps.streaming.models import VideoWatch
from apps.streaming.serializers import VideoWatchSerializer
from django.conf import settings
from helpers.helper import (
    calcule_de_similarite_de_phrase, get_available_info, format_file_size, format_duration, format_views, 
    format_elapsed_time
)
from apps.videos.tasks import generate_video_affichage
from django.db.models import Count
from django.contrib.auth.models import AnonymousUser
from queue import Queue
from threading import Thread
import os
import time

################################# WORKER #################################
def video_affichage_worker():
    while True:
        try:
            task = VideoProcessingTask.objects.filter(status='PENDING').order_by('created_at').first()
            if task:
                print(f"[!] 🎊 Worker traite la tâche ID: {task.id} pour vidéo ID: {task.video_id}")
                task.status = 'PROCESSING'
                task.save()
                
                try:
                    if task.task_type == 'THUMBNAILS':
                        generate_video_affichage(task.video_id)
                    task.status = 'COMPLETED'
                    task.save()
                except Exception as e:
                    print(f"[❌] Erreur dans le worker pour tâche ID: {task.id} - {str(e)}")
                    task.status = 'FAILED'
                    task.error_message = str(e)
                    task.save()
        except Exception as e:
            print(f"[❌] Erreur dans le worker: {str(e)}")
        time.sleep(1) 

processing_worker_thread = Thread(target=video_affichage_worker, daemon=True)
processing_worker_thread.start()

################################# WORKER #################################

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

class PlaylistSerializer(serializers.ModelSerializer):
    videos = serializers.SerializerMethodField()
    video_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Playlist
        fields = ['id', 'titre', 'chaine', 'user', 'videos', 'video_ids', 'created_at']
        read_only_fields = ['id', 'created_at', 'videos']

    def validate(self, data):
        video_ids = data.get('video_ids', [])
        titre = data.get('titre', '')
        chaine = data.get('chaine')
        user = data.get('user')
        
        if not titre and not video_ids:
            raise serializers.ValidationError("Le titre et la liste des vidéos ne peuvent pas être vides simultanément.")
        if (chaine is None and user is None) or (chaine is not None and user is not None):
            raise serializers.ValidationError("Une playlist doit être associée à une chaîne ou un utilisateur, mais pas aux deux.")
        return data

    def get_videos(self, obj):
        video_playlists = VideoPlaylist.objects.filter(playlist=obj).order_by('ordre')
        return VideoSerializer([vp.video for vp in video_playlists], many=True, context=self.context).data

    def create(self, validated_data):
        video_ids = validated_data.pop('video_ids', [])
        if not validated_data.get('user') and self.context['request'].user.is_authenticated:
            validated_data['user'] = self.context['request'].user
        playlist = Playlist.objects.create(**validated_data)
        
        for index, video_id in enumerate(video_ids):
            video = Video.objects.get(id=video_id)
            VideoPlaylist.objects.create(playlist=playlist, video=video, ordre=index + 1)
        
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
        
        return instance

class SuggestedVideoSerializer(serializers.ModelSerializer):
    envoyeur = UserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()
    dislikes_count = serializers.SerializerMethodField()
    vues_count = serializers.SerializerMethodField()
    fichier_url = serializers.SerializerMethodField()
    affichage_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            'id', 'titre', 'description', 'fichier_url', 'affichage_url', 'envoyeur',
            'categorie', 'tags', 'visibilite',
            'autoriser_commentaire', 'ordre_de_commentaire', 'likes_count', 'dislikes_count',
            'vues_count', 'uploaded_at', 'updated_at', 'code_id'
        ]

    def get_fichier_url(self, obj):
        return f"{settings.BASE_URL}{obj.fichier.url}" if obj.fichier else None

    def get_affichage_url(self, obj):
        if obj.affichage is None:
            VideoProcessingTask.objects.create(
                video_id=obj.id,
                task_type='THUMBNAILS',
                status='PENDING'
            )
        return f"{settings.BASE_URL}{obj.affichage.url}" if obj.affichage else None

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_dislikes_count(self, obj):
        return obj.dislikes.count()

    def get_vues_count(self, obj):
        return obj.vues.count()
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request", None)
        if request is not None and not isinstance(request.user, AnonymousUser):
            user = request.user
            representation['is_liked_by_me'] = user.id in [u.id for u in instance.likes.all()]
            representation['is_disliked_by_me'] = user.id in [u.id for u in instance.dislikes.all()]
            representation['is_view_by_me'] = user.id in [u.id for u in instance.vues.all()]
            try:
                watch = VideoWatch.objects.get(video=instance, user=user)
                representation["my_watch_video"] = VideoWatchSerializer(watch).data
            except VideoWatch.DoesNotExist:
                pass
        if instance.fichier:
            video_path = os.path.join(settings.MEDIA_ROOT, instance.fichier.name)
            video_info = get_available_info(video_path)
            if video_info and 'error' not in video_info:
                representation["taille"] = format_file_size(video_info.get('size', 0))
                representation["duration"] = format_duration(video_info.get('duration', 0))
                representation["largeur"] = f"{video_info.get('width', 0)}"
                representation["hauteur"] = f"{video_info.get('height', 0)}"
                representation["qualite"] = video_info.get('quality', 'N/A')
                representation["qualites_disponibles"] = video_info.get('qualities', 'N/A')
                representation["fps"] = f"{video_info.get('fps', 0)} images/s"
        representation['vues_formatted'] = format_views(representation['vues_count'])
        representation['elapsed_time'] = format_elapsed_time(instance.uploaded_at)
        return representation

class VideoSerializer(serializers.ModelSerializer):
    envoyeur = UserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
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
            'categorie', 'tags', 'tag_ids', 'visibilite',
            'autoriser_commentaire', 'ordre_de_commentaire', 'likes_count', 'dislikes_count',
            'vues_count', 'uploaded_at', 'updated_at', 'suggested_videos', 'code_id'
        ]
        
    def get_fichier_url(self, obj):
        return f"{settings.BASE_URL}{obj.fichier.url}" if obj.fichier else None
    
    def get_affichage_url(self, obj):
        if not obj.affichage:
            VideoProcessingTask.objects.create(
            video_id=obj.id,
            task_type='THUMBNAILS',
            status='PENDING'
        )
        return f"{settings.BASE_URL}{obj.affichage.url}" if obj.affichage else None

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_dislikes_count(self, obj):
        return obj.dislikes.count()

    def get_vues_count(self, obj):
        return obj.vues.count()

    def get_suggested_videos(self, obj):
        suggested = []
        
        # Suggest videos from the same playlist
        playlists = Playlist.objects.filter(videos_playlist__video=obj)
        for playlist in playlists:
            next_videos = VideoPlaylist.objects.filter(
                playlist=playlist, ordre__gt=VideoPlaylist.objects.get(playlist=playlist, video=obj).ordre
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

        suggested = list(dict.fromkeys(suggested))[:25]
        return SuggestedVideoSerializer(suggested, many=True, context=self.context).data

    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        validated_data['envoyeur'] = self.context['request'].user
        video = Video.objects.create(**validated_data)

        if tag_ids:
            video.tags.set(tag_ids)
        
        return video

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tag_ids:
            instance.tags.set(tag_ids)
        
        return instance
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request", None)
        with_suggestion = self.context.get("with_suggestion", True)
        if request is not None and not isinstance(request.user, AnonymousUser):
            user = request.user
            representation['is_liked_by_me'] = user.id in [u.id for u in instance.likes.all()]
            representation['is_disliked_by_me'] = user.id in [u.id for u in instance.dislikes.all()]
            representation['is_view_by_me'] = user.id in [u.id for u in instance.vues.all()]
            try:
                watch = VideoWatch.objects.get(video=instance, user=user)
                representation["my_watch_video"] = VideoWatchSerializer(watch).data
            except VideoWatch.DoesNotExist:
                pass
        
        if instance.autoriser_commentaire:
            commentaires = instance.commentaires.all()
            if instance.ordre_de_commentaire == 'TOP':
                commentaires = commentaires.annotate(message_count=Count('messages')).order_by('-message_count')
            else:
                commentaires = commentaires.order_by('-created_at')
            representation["commentaires"] = CommentaireSerializer(commentaires, many=True).data
        if instance.fichier:
            video_path = os.path.join(settings.MEDIA_ROOT, instance.fichier.name)
            video_info = get_available_info(instance.fichier.path)
            if video_info and 'error' not in video_info:
                representation["taille"] = format_file_size(video_info.get('size', 0))
                representation["duration"] = format_duration(video_info.get('duration', 0))
                representation["largeur"] = f"{video_info.get('width', 0)}"
                representation["hauteur"] = f"{video_info.get('height', 0)}"
                representation["qualite"] = video_info.get('quality', 'N/A')
                representation["qualites_disponibles"] = video_info.get('qualities', 'N/A')
                representation["fps"] = f"{video_info.get('fps', 0)} images/s"
        if not with_suggestion:
            representation.pop("suggested_videos", None)
        
        representation['vues_formatted'] = format_views(representation['vues_count'])
        representation['elapsed_time'] = format_elapsed_time(instance.uploaded_at)
        return representation

class ChaineSerializer(serializers.ModelSerializer):
    playlists = serializers.SerializerMethodField()

    class Meta:
        model = Chaine
        fields = ['id', 'titre', 'description', 'playlists', 'abonnees', 'created_at']
        read_only_fields = ['id', 'abonnees', 'created_at', 'playlists']

    def get_playlists(self, obj):
        playlists = Playlist.objects.filter(chaine=obj)
        return PlaylistSerializer(playlists, many=True, context=self.context).data

    def create(self, validated_data):
        chaine = Chaine.objects.create(**validated_data)
        return chaine

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request", None)
        if request is not None:
            user = request.user
            representation['is_subscribed_by_me'] = user.id in [u.id for u in instance.abonnees.all()]
        return representation
