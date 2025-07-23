from django.db import models
from apps.users.models import User, default_created_at

class Tag(models.Model):
    name = models.CharField(max_length=255)
    
    def __str__(self) -> str:
        return self.name
    
    class Meta:
        db_table = "tag"
        
class Chaine(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    visibilite = models.CharField(max_length=200, choices=[(x,x) for x in ['PUBLIC', 'PRIVATE']], default='PUBLIC')
    
    abonnees = models.ManyToManyField(User, related_name="chaines_abonnes")
    
    created_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "chaine"

class Video(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField()
    fichier = models.FileField(upload_to="videos/")
    affichage = models.ImageField(upload_to="videos/affichages/", null=True, blank=True)
    envoyeur = models.ForeignKey(User, on_delete=models.CASCADE, related_name="videos_envoyees")
    
    dans_un_chaine = models.BooleanField(default=False)
    
    categorie = models.CharField(max_length=200, blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name="videos")
    visibilite = models.CharField(max_length=200, choices=[(x,x) for x in ['PUBLIC', 'PRIVATE']], default='PUBLIC')
    autoriser_commentaire = models.BooleanField(default=True)
    ordre_de_commentaire = models.CharField(max_length=200, choices=[(x,x) for x in ['TOP', 'NOUVEAUTE']])
    
    likes = models.ManyToManyField(User, related_name="videos_liked")
    dislikes = models.ManyToManyField(User, related_name="videos_disliked")
    vues = models.ManyToManyField(User, related_name="videos_vues")
    
    uploaded_at = models.DateTimeField(default=default_created_at)
    updated_at = models.DateTimeField(default=default_created_at)
    
    def __str__(self):
        return self.titre
    
    class Meta:
        db_table = "video"

class VideoVue(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="vues_detaillees")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vues_detaillees")
    created_at = models.DateTimeField(default=default_created_at)

    class Meta:
        db_table = "videovue"
        unique_together = ('video', 'user')  # Une seule vue par utilisateur et vidéo

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

class VideoChaine(models.Model):
    chaine = models.ForeignKey(Chaine, on_delete=models.CASCADE, related_name='videos_chaine')
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name="videos_chaine")
    ordre = models.IntegerField(default=0)
    
    class Meta:
        db_table = "videochaine"

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