from django.db import models
from apps.videos.models import Video
from apps.users.models import User

class VideoWatch(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="watches")
    user = models.ForeignKey(User,on_delete=models.CASCADE, related_name="watches")
    
