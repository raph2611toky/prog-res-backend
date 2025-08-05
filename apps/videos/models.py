from django.db import models
from apps.users.models import User, default_created_at
import uuid

class Tag(models.Model):
    name = models.CharField(max_length=255)
    
    def __str__(self) -> str:
        return self.name
    
    class Meta:
        db_table = "tag"
        
class Chaine(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    abonnees = models.ManyToManyField(User, related_name="chaines_abonnes")
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "chaine"

class Playlist(models.Model):
    titre = models.CharField(max_length=200, blank=True)
    chaine = models.ForeignKey(Chaine, on_delete=models.CASCADE, related_name="playlists", null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="playlists", null=True, blank=True)
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre or f"Playlist {self.id}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if (self.chaine is None and self.user is None) or (self.chaine is not None and self.user is not None):
            raise ValidationError("Une playlist doit être associée à une chaîne ou un utilisateur, mais pas aux deux.")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = "playlist"
        
class VideoUpload(models.Model):
    upload_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="video_uploads")
    titre = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    categorie = models.CharField(max_length=200, blank=True, null=True)
    visibilite = models.CharField(max_length=200, choices=[(x, x) for x in ['PUBLIC', 'PRIVATE']], default='PUBLIC')
    tags = models.CharField(max_length=500, blank=True)
    total_size = models.PositiveBigIntegerField()
    total_chunks = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "video_upload"
        app_label = 'videos'

    def __str__(self):
        return f"Upload {self.upload_id} by {self.user}"

class VideoChunk(models.Model):
    video_upload = models.ForeignKey(VideoUpload, on_delete=models.CASCADE, related_name="chunks")
    chunk_number = models.PositiveIntegerField()
    chunk_file = models.FileField(upload_to="video_chunks/")

    class Meta:
        db_table = "video_chunk"
        app_label = 'videos'
        unique_together = ('video_upload', 'chunk_number')

    def __str__(self):
        return f"Chunk {self.chunk_number} for upload {self.video_upload.upload_id}"

class Video(models.Model):
    code_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    titre = models.CharField(max_length=200)
    description = models.TextField()
    fichier = models.FileField(upload_to="videos/")
    affichage = models.ImageField(upload_to="videos/affichages/", null=True, blank=True)
    envoyeur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="videos_envoyees")
    
    categorie = models.CharField(max_length=200, blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name="videos")
    visibilite = models.CharField(max_length=200, choices=[(x,x) for x in ['PUBLIC', 'PRIVATE', 'UNLISTED']], default='PUBLIC')
    autoriser_commentaire = models.BooleanField(default=True)
    ordre_de_commentaire = models.CharField(max_length=200, choices=[(x,x) for x in ['TOP', 'NOUVEAUTE']], default="NOUVEAUTE")
    
    likes = models.ManyToManyField(User, related_name="videos_liked")
    dislikes = models.ManyToManyField(User, related_name="videos_disliked")
    vues = models.ManyToManyField(User, related_name="videos_vues")
    
    master_manifest_file = models.FileField(upload_to="videos/manifests/", null=True, blank=True)
    segments_dir = models.CharField(max_length=255, null=True, blank=True)
    
    uploaded_at = models.DateTimeField(default=default_created_at)
    updated_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "video"
        app_label = 'videos'
        
class VideoInfo(models.Model):
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name="info")
    qualities = models.JSONField()
    audio_languages = models.JSONField()
    subtitle_languages = models.JSONField() 
    fps = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()
    duration = models.FloatField()
    size = models.IntegerField()

    class Meta:
        db_table = "videoinfo"

class VideoVue(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="vues_detaillees")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vues_detaillees")
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "videovue"
        unique_together = ('video', 'user')

class VideoLike(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="likes_detaillees")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="likes_detaillees")
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "videolike"
        unique_together = ('video', 'user')

class VideoDislike(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="dislikes_detaillees")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dislikes_detaillees")
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "videodislike"
        unique_together = ('video', 'user')

class VideoRegarderPlusTard(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="regarder_plus_tard")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="regarder_plus_tard")
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "videoregarderplustard"
        unique_together = ('video', 'user')

class VideoPlaylist(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='videos_playlist')
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="video_playlist")
    ordre = models.IntegerField(default=0)
    
    class Meta:
        db_table = "videoplaylist"
        unique_together = ('playlist', 'video')

class Commentaire(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="commentaires")
    membres = models.ManyToManyField(User, related_name="commentaires")
    
    created_at = models.DateTimeField(default=default_created_at)
    
    class Meta:
        db_table = "commentaire"
        
class Message(models.Model):
    commentaire = models.ForeignKey(Commentaire, on_delete=models.CASCADE, related_name="messages")
    envoyeur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messages_envoyees")
    contenu = models.TextField(blank=True, null=True)
    likes = models.ManyToManyField(User, related_name="messages_liked")
    dislikes = models.ManyToManyField(User, related_name="messages_disliked")
    
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return f"{self.envoyeur} → {self.contenu}"
    
    class Meta:
        db_table = "message"

class VideoProcessingTask(models.Model):
    TASK_TYPES = (
        ('THUMBNAILS', 'Generate Thumbnails'),
        ('CONVERSION', 'Convert Video'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )

    video_id = models.IntegerField()
    task_type = models.CharField(max_length=20, choices=TASK_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'video_processing_tasks'