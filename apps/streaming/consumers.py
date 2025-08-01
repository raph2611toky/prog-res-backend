from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
import json
import os
from django.conf import settings
from apps.streaming.models import VideoWatch
from apps.videos.models import Video
from helpers.helper import get_available_info
import math

@database_sync_to_async
def get_video_info_available(video_id):
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        video_info = get_available_info(video_path)
        return video_info
    except Video.DoesNotExist:
        return None
    except Exception as e:
        print(f"Error in get_video_info_available: {str(e)}")
        return None

class VideoWatchConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("[!] Trying to connect....")
        self.video_id = self.scope['url_route']['kwargs']['video_id']
        self.user = self.scope['user']
        if not isinstance(self.user, AnonymousUser) and self.user.is_authenticated:
            self.group_name = f"videowatch_{self.user.id}_{self.video_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print("✅ Connected...")
        else:
            self.user = None
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print("❌ Disconnected...")

    async def receive(self, text_data):
        try:
            data_info = json.loads(text_data)
            type_data = data_info.get('type')
            data = data_info.get('data', {})
            print(f"📥 Received: {data_info}")

            if type_data == 'update':
                # Update viewing information
                video_watch, _ = await database_sync_to_async(VideoWatch.objects.get_or_create)(
                    video_id=self.video_id,
                    user=self.user,
                    defaults={'last_position': 0.0, 'quality': 'auto', 'playback_speed': 1.0, 'volume': 1.0}
                )
                video_watch.last_position = data.get('position', video_watch.last_position)
                video_watch.quality = data.get('quality', video_watch.quality)
                video_watch.playback_speed = data.get('speed', video_watch.playback_speed)
                video_watch.volume = data.get('volume', video_watch.volume)
                await database_sync_to_async(video_watch.save)()

                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'watch_update',
                        'position': video_watch.last_position,
                        'quality': video_watch.quality,
                        'speed': video_watch.playback_speed,
                        'volume': video_watch.volume,
                        'video_id': self.video_id
                    }
                )

            elif type_data == 'get_segments':
                video_info = await get_video_info_available(self.video_id)
                if not video_info:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Vidéo non trouvée ou informations indisponibles'
                    }))
                    return

                position = data.get('position', 0.0)
                quality = data.get('quality', 'auto')
                segment_index = math.floor(position / 10)
                print(f"[!] Get segments for position {position}, quality {quality}...")

                if quality not in video_info['qualities']:
                    quality = video_info["quality"]

                try:
                    video = await database_sync_to_async(Video.objects.get)(id=self.video_id)
                    segments_dir = os.path.join(settings.MEDIA_ROOT, "videos", str(self.video_id), "segments", quality if quality != video_info['quality'] else "original")
                    manifest_path = os.path.join(segments_dir, "manifest.m3u8")
                    print(f"Checking manifest at: {manifest_path}")

                    # Wrap file system access in a sync_to_async call
                    @database_sync_to_async
                    def check_manifest_and_read():
                        if not os.path.exists(manifest_path):
                            return None
                        with open(manifest_path, 'r') as f:
                            return f.readlines()

                    manifest_lines = await check_manifest_and_read()
                    if not manifest_lines:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Manifeste HLS non trouvé'
                        }))
                        return

                    segment_files = [line.strip() for line in manifest_lines if line.strip().endswith('.ts')]
                    if segment_index >= len(segment_files):
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Position demandée hors de la portée de la vidéo'
                        }))
                        return

                    base_url = settings.BASE_URL + settings.MEDIA_URL
                    segment_urls = [
                        f"{base_url}videos/{self.video_id}/segments/{quality if quality != video_info['quality'] else "original"}/{segment_files[i]}"
                        for i in range(segment_index, len(segment_files))
                    ]

                    segment_start_time = segment_index * 10.0
                    offset_in_segment = position - segment_start_time

                    await self.send(text_data=json.dumps({
                        'type': 'segment_info',
                        'segments': segment_urls,
                        'start_offset': offset_in_segment,
                        'quality': quality,
                        'video_id': self.video_id
                    }))
                except Video.DoesNotExist:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Vidéo non trouvée'
                    }))

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data received'
            }))
        except Exception as e:
            print(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Erreur serveur: {str(e)}'
            }))

    async def watch_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'watch_update',
            'position': event['position'],
            'quality': event['quality'],
            'speed': event['speed'],
            'volume': event['volume'],
            'video_id': event['video_id']
        }))
