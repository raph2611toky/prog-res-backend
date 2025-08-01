from rest_framework import serializers
from apps.streaming.models import VideoWatch

class VideoWatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoWatch
        fields = ['video', 'user', 'last_position', 'quality', 'playback_speed', 'volume', 'last_watch']