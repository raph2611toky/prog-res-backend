from django.db import models
from apps.users.models import User, default_created_at

class Tag(models.Model):
    name = models.CharField(max_length=255)
    
    def __str__(self) -> str:
        return self.name
    
    class Meta:
        db_table = "tag"
        

class Playlist(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    visibilite = models.CharField(max_length=200, choices=[(x,x)for x in ['PUBLIC', 'PRIVATE']], default='PUBLIC')
    
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "playlist"

class Video(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField()
    fichier = models.FileField(upload_to="videos/")
    affichage = models.ImageField(upload_to="videos/affichages/", null=True, blank=True)
    envoyeur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="videos_envoyees")
    
    dans_un_playlist = models.BooleanField(default=False)
    
    categorie = models.CharField(max_length=200, blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name="videos")
    visibilite = models.CharField(max_length=200, choices=[(x,x)for x in ['PUBLIC', 'PRIVATE']], default='PUBLIC')
    autoriser_commentaire = models.BooleanField(default=True)
    ordre_de_commentaire = models.CharField(max_length=200, choices=[(x,x)for x in ['TOP', 'NOUVEAUTE']])
    
    likes = models.ManyToManyField(User, related_name="videos_liked")
    dislikes = models.ManyToManyField(User, related_name="videos_disliked")
    vues = models.ManyToManyField(User, related_name="videos_vues")
    
    uploaded_at = models.DateTimeField(default=default_created_at)
    updated_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "video"
        
class VideoPlaylist(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='videos_playlist')
    video = models.OneToOneField(Video, on_delete=models.CASCADE,related_name="videos_playlist")
    ordre = models.IntegerField(default=0)
    
    class Meta:
        db_table = "videoplaylist"

class Commentaire(models.Model):
    video = models.ForeignKey(Video,on_delete=models.CASCADE, related_name="commentaires")
    membres = models.ManyToManyField(User,related_name="commentaires")
    
    created_at = models.DateTimeField(default=default_created_at)
    
    class Meta:
        db_table = "commentaire"
        
class Message(models.Model):
    commentaire = models.ForeignKey(Commentaire,on_delete=models.CASCADE, related_name="messages")
    envoyeur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="messages_envoyees")
    contenu = models.TextField(blank=True, null=True)
    likes = models.ManyToManyField(User,related_name="messages_liked")
    dislikes = models.ManyToManyField(User,related_name="messages_disliked")
    
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return f"{self.envoyeur} → {self.contenu}"
    
    class Meta:
        db_table = "message"

