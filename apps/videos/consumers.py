from channels.generic.websocket import AsyncWebsocketConsumer
import json
from helpers.helper import format_file_size, format_duration

class UploadProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        upload_id = self.scope['url_route']['kwargs']['upload_id']
        user_id = self.scope['user'].id
        self.group_name = f"upload_{user_id}_{upload_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def upload_progress(self, event):
        await self.send(text_data=json.dumps({
            'progress': round(event['progress'], 2), 
            'speed': format_file_size(event['speed']) + "/s", 
            'total_duration': format_duration(event['total_duration']), 
            'remaining_duration': format_duration(event['remaining_duration']),
            'remaining_size': format_file_size(event['remaining_size']),
            'status': event['status'], 
            'video_id': event.get('video_id', None) 
        }))