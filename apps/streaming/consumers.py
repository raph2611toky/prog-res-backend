from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
import json
from django.conf import settings
from apps.streaming.models import VideoWatch
from apps.videos.models import Video, VideoInfo
from apps.videos.serializers import VideoInfoSerializer
from helpers.helper import get_available_info
import os

@database_sync_to_async
def get_video_info_available(video_id):
    try:
        video = Video.objects.get(id=video_id)
        video_info = VideoInfo.objects.get(video=video)
        video_path = video.fichier.path
        probe_info = get_available_info(video_path)
        # print(VideoInfoSerializer(video_info).data, probe_info)
        
        qualities = []
        base_url = settings.BASE_URL + settings.MEDIA_URL
        video_dir = os.path.join("videos", str(video.id))
        for quality in video_info.qualities:
            manifest_path = os.path.join(video_dir, "segments", quality if quality != video_info.qualities[0] else "original", "video.m3u8")
            qualities.append({
                "name": quality,
                "url": f"{base_url}{manifest_path}",
                "resolution": {
                    "2160p": "3840x2160",
                    "2160p (4K)": "3840x2160",
                    "1440p": "2560x1440",
                    "1440p (2K)": "2560x1440",
                    "1080p": "1920x1080",
                    "1080p (Full HD)": "1920x1080",
                    "720p": "1280x720",
                    "720p (HD)": "1280x720",
                    "480p": "842x480",
                    "360p": "640x360",
                    "240p": "426x240",
                    "144p": "256x144"
                }.get(quality, "1920x1080"),
                "bandwidth": {
                    "2160p": "3840x2160",
                    "2160p (4K)": "3840x2160",
                    "1440p": "2560x1440",
                    "1440p (2K)": "2560x1440",
                    "1080p": "1920x1080",
                    "1080p (Full HD)": "1920x1080",
                    "720p": "1280x720",
                    "720p (HD)": "1280x720",
                    "480p": "842x480",
                    "360p": "640x360",
                    "240p": "426x240",
                    "144p": "256x144"
                }.get(quality, "5000000")
            })
        audio_tracks = []
        for lang in video_info.audio_languages:
            audio_manifest = os.path.join(video_dir, "segments", "original", f"audio_{lang}.m3u8")
            audio_tracks.append({
                "language": lang,
                "url": f"{base_url}{audio_manifest}"
            })
        subtitle_tracks = []
        for lang in video_info.subtitle_languages:
            subtitle_manifest = os.path.join(video_dir, "segments", "original", f"subs_{lang}.m3u8")
            subtitle_tracks.append({
                "language": lang,
                "url": f"{base_url}{subtitle_manifest}"
            })

        return {
            "qualities": qualities,
            "audio_tracks": audio_tracks,
            "subtitle_tracks": subtitle_tracks,
            "fps": video_info.fps,
            "width": video_info.width,
            "height": video_info.height,
            "duration": video_info.duration,
            "size": video_info.size,
            "master_manifest": os.path.join(base_url, video.master_manifest_file.name),
            "quality": probe_info["quality"]
        }
    except Video.DoesNotExist:
        return None
    except VideoInfo.DoesNotExist:
        return None
    except Exception as e:
        print(f"Error in get_video_info_available: {str(e)}")
        return None

@database_sync_to_async
def get_video_watch(video_id, user):
    try:
        return VideoWatch.objects.get(video_id=video_id, user=user)
    except VideoWatch.DoesNotExist:
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
            await self.send_manifest_url()
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

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data received'
            }))
        except Exception as e:
            print(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Server error: {str(e)}'
            }))

    async def send_manifest_url(self):
        try:
            video = await database_sync_to_async(Video.objects.get)(id=self.video_id)
            video_info = await get_video_info_available(self.video_id)
            if not video_info:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Video or information not found'
                }))
                return

            video_watch = await get_video_watch(self.video_id, self.user)
            last_position = video_watch.last_position if video_watch else 0.0
            last_volume = video_watch.volume if video_watch else 1
            last_playback_speed = video_watch.playback_speed if video_watch else 1
            last_quality = video_watch.quality if video_watch else video_info["quality"]

            await self.send(text_data=json.dumps({
                'type': 'segment_info',
                'manifest_url': video_info['master_manifest'],
                'last_position': last_position,
                'last_volume': last_volume,
                'last_playback_speed': last_playback_speed,
                'last_quality': last_quality,
                'qualities': video_info['qualities'],
                'audio_tracks': video_info['audio_tracks'],
                'subtitle_tracks': video_info['subtitle_tracks'],
                'metadata': {
                    'fps': video_info['fps'],
                    'width': video_info['width'],
                    'height': video_info['height'],
                    'duration': video_info['duration'],
                    'size': video_info['size']
                }
            }))
        except Video.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Video not found'
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