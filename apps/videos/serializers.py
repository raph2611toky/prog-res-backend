from rest_framework import serializers
from .models import Tag, Video, Chaine, Commentaire, Message, VideoChaine
from apps.users.serializers import UserSerializer
from django.utils.text import slugify
from django.conf import settings
from helpers.helper import calcule_de_similarite_de_phrase, get_available_info, format_file_size, format_duration, format_views, format_elapsed_time
from django.db.models import Count
from django.db.models import Max

import os

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

class VideoChaineSerializer(serializers.ModelSerializer):
    video = serializers.PrimaryKeyRelatedField(queryset=Video.objects.all())
    chaine = serializers.PrimaryKeyRelatedField(queryset=Chaine.objects.all())

    class Meta:
        model = VideoChaine
        fields = ['id', 'chaine', 'video', 'ordre']

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
            'dans_un_chaine', 'categorie', 'tags', 'visibilite',
            'autoriser_commentaire', 'ordre_de_commentaire', 'likes_count', 'dislikes_count',
            'vues_count', 'uploaded_at', 'updated_at'
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

class VideoSerializer(serializers.ModelSerializer):
    envoyeur = UserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    chaine_id = serializers.IntegerField(write_only=True, required=False)
    chaine = serializers.SerializerMethodField()
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
            'dans_un_chaine', 'categorie', 'tags', 'tag_ids', 'chaine_id', 'chaine', 'visibilite',
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

    def get_chaine(self, obj):
        if obj.dans_un_chaine and hasattr(obj, 'videos_chaine'):
            video_chaine = obj.videos_chaine
            return ChaineSerializer(video_chaine.chaine).data
        return None

    def get_suggested_videos(self, obj):
        suggested = []
        
        if obj.dans_un_chaine and hasattr(obj, 'videos_chaine'):
            video_chaine = obj.videos_chaine
            chaine = video_chaine.chaine
            next_videos = VideoChaine.objects.filter(
                chaine=chaine, ordre__gt=video_chaine.ordre
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
        chaine_id = validated_data.pop('chaine_id', None)
        validated_data['envoyeur'] = self.context['request'].user
        video = Video.objects.create(**validated_data)

        if tag_ids:
            video.tags.set(tag_ids)
        if chaine_id:
            chaine = Chaine.objects.get(id=chaine_id)
            max_ordre = VideoChaine.objects.filter(chaine=chaine).aggregate(Max('ordre'))['ordre__max'] or 0
            VideoChaine.objects.create(chaine=chaine, video=video, ordre=max_ordre + 1)
            video.dans_un_chaine = True
            video.save()
        
        return video

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        chaine_id = validated_data.pop('chaine_id', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tag_ids:
            instance.tags.set(tag_ids)
        if chaine_id:
            chaine = Chaine.objects.get(id=chaine_id)
            if not hasattr(instance, 'videos_chaine') or instance.videos_chaine.chaine != chaine:
                if hasattr(instance, 'videos_chaine'):
                    instance.videos_chaine.delete()
                max_ordre = VideoChaine.objects.filter(chaine=chaine).aggregate(Max('ordre'))['ordre__max'] or 0
                VideoChaine.objects.create(chaine=chaine, video=instance, ordre=max_ordre + 1)
                instance.dans_un_chaine = True
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

class ChaineSerializer(serializers.ModelSerializer):
    videos = serializers.SerializerMethodField()
    abonnees = UserSerializer(many=True)
    video_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Chaine
        fields = ['id', 'titre', 'description', 'visibilite', 'videos', 'video_ids', 'abonnees', 'created_at']

    def get_videos(self, obj):
        video_chaines = VideoChaine.objects.filter(chaine=obj).order_by('ordre')
        return VideoSerializer([vp.video for vp in video_chaines], many=True, context=self.context).data

    def create(self, validated_data):
        video_ids = validated_data.pop('video_ids', None)
        chaine = Chaine.objects.create(**validated_data)
        
        if video_ids:
            for index, video_id in enumerate(video_ids):
                video = Video.objects.get(id=video_id)
                VideoChaine.objects.create(chaine=chaine, video=video, ordre=index + 1)
                video.dans_un_chaine = True
                video.save()
        
        return chaine

    def update(self, instance, validated_data):
        video_ids = validated_data.pop('video_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if video_ids is not None:
            VideoChaine.objects.filter(chaine=instance).delete()
            for index, video_id in enumerate(video_ids):
                video = Video.objects.get(id=video_id)
                VideoChaine.objects.create(chaine=instance, video=video, ordre=index + 1)
                video.dans_un_chaine = True
                video.save()
        
        return instance
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request", None)
        if request is not None:
            user = request.user
            representation['is_subscribed_by_me'] = user.id in [u.id for u in instance.abonnees.all()]
        return representation