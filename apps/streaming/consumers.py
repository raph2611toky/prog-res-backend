from channels.generic.websocket import AsyncWebsocketConsumer
import json
from apps.streaming.models import VideoWatch

class VideoWatchConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.video_id = self.scope['url_route']['kwargs']['video_id']
        self.user = self.scope['user']
        if self.user.is_authenticated:
            self.group_name = f"videowatch_{self.user.id}_{self.video_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        video_watch, _ = VideoWatch.objects.get_or_create(
            video_id=self.video_id,
            user=self.user,
            defaults={'last_position': 0.0, 'quality': 'auto', 'playback_speed': 1.0}
        )
        video_watch.last_position = data.get('position', video_watch.last_position)
        video_watch.quality = data.get('quality', video_watch.quality)
        video_watch.playback_speed = data.get('speed', video_watch.playback_speed)
        video_watch.save()

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'watch_update',
                'position': video_watch.last_position,
                'quality': video_watch.quality,
                'speed': video_watch.playback_speed
            }
        )

    async def watch_update(self, event):
        await self.send(text_data=json.dumps({
            'position': event['position'],
            'quality': event['quality'],
            'speed': event['speed']
        }))