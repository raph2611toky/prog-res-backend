from django.db import models
from apps.videos.models import Video
from apps.users.models import User, default_created_at

class VideoWatch(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="watches")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="watches")
    last_position = models.FloatField(default=0.0)
    quality = models.CharField(max_length=10, default="auto") 
    volume = models.FloatField(default=1.0)
    playback_speed = models.FloatField(default=1.0)
    last_watch = models.DateTimeField(default=default_created_at) 

    class Meta:
        unique_together = ('video', 'user')
        db_table = "videowatch"

    def __str__(self):
        return f"{self.user} watching {self.video} at {self.last_position}s"
    
    class Meta:
        db_table = "video_watch"