from apps.videos.models import Video, VideoInfo
from helpers.helper import get_available_info, convert_video_quality, extract_random_frame
import os
import subprocess
import shutil
import ffmpeg
from pathlib import Path
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

def generate_video_segments(video_id, quality=None):
    try:
        video = Video.objects.get(id=video_id)
        video_dir = os.path.join(settings.MEDIA_ROOT, "videos", str(video.id))
        original_filename = os.path.basename(video.fichier.path)
        if quality == "original":
            video_path = os.path.join(video_dir, original_filename)
        else:
            video_path = os.path.join(video_dir, "qualities", quality, original_filename)
        
        segments_dir = os.path.join(video_dir, "segments", quality or "original")
        os.makedirs(segments_dir, exist_ok=True)

        probe = ffmpeg.probe(video_path)
        audio_streams = [s for s in probe['streams'] if s['codec_type'] == 'audio']
        subtitle_streams = [s for s in probe['streams'] if s['codec_type'] == 'subtitle']

        # Générer le manifeste vidéo
        video_manifest = os.path.join(segments_dir, "video.m3u8")
        cmd_video = [
            "ffmpeg", "-i", video_path,
            "-map", "0:v", "-c:v", "copy",
            "-f", "hls", "-hls_time", "10", "-hls_list_size", "0",
            "-hls_segment_filename", os.path.join(segments_dir, "video_%03d.ts"),
            video_manifest
        ]
        subprocess.run(cmd_video, check=True)

        # Générer les manifestes audio (uniquement pour la qualité "original")
        audio_manifests = []
        if quality == "original":  # Audio uniquement pour "original" car identique pour toutes les qualités
            for idx, stream in enumerate(audio_streams):
                lang = stream.get('tags', {}).get('language', f"lang{idx}")
                audio_manifest = os.path.join(segments_dir, f"audio_{lang}.m3u8")
                cmd_audio = [
                    "ffmpeg", "-i", video_path,
                    "-map", f"0:a:{idx}", "-c:a", "aac",
                    "-f", "hls", "-hls_time", "10", "-hls_list_size", "0",
                    "-hls_segment_filename", os.path.join(segments_dir, f"audio_{lang}_%03d.ts"),
                    audio_manifest
                ]
                subprocess.run(cmd_audio, check=True)
                audio_manifests.append((lang, audio_manifest))

        # Générer les manifestes de sous-titres (uniquement pour "original")
        subtitle_manifests = []
        if quality == "original":
            for idx, stream in enumerate(subtitle_streams):
                lang = stream.get('tags', {}).get('language', f"sub{idx}")
                subtitle_vtt = os.path.join(segments_dir, f"subs_{lang}.vtt")
                cmd_subtitle = [
                    "ffmpeg", "-i", video_path,
                    "-map", f"0:s:{idx}", "-c:s", "webvtt",
                    subtitle_vtt
                ]
                subprocess.run(cmd_subtitle, check=True)
                subtitle_manifest = os.path.join(segments_dir, f"subs_{lang}.m3u8")
                duration = probe['format']['duration']
                with open(subtitle_manifest, 'w') as f:
                    f.write("#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-VERSION:3\n")
                    f.write("#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
                    f.write(f"#EXTINF:{duration},\n{os.path.basename(subtitle_vtt)}\n")
                    f.write("#EXT-X-ENDLIST\n")
                subtitle_manifests.append((lang, subtitle_manifest))

        # Retourner les informations nécessaires pour le manifeste maître
        bandwidth = {
            "original": "8000000",
            "2160p": "16000000",
            "1440p": "8000000",
            "1080p": "5000000",
            "720p": "2800000",
            "480p": "1400000",
            "360p": "800000",
            "240p": "400000",
            "144p": "200000"
        }.get(quality or "original", "5000000")
        resolution = {
            "original": "1920x1080",
            "2160p": "3840x2160",
            "1440p": "2560x1440",
            "1080p": "1920x1080",
            "720p": "1280x720",
            "480p": "842x480",
            "360p": "640x360",
            "240p": "426x240",
            "144p": "256x144"
        }.get(quality or "original", "1920x1080")

        return video_manifest, segments_dir, bandwidth, resolution, audio_manifests, subtitle_manifests
    except Exception as e:
        print(f"Erreur lors de la génération des segments : {e}")
        return None, None, None, None, [], []

def process_video_conversion(video_id):
    print("🎊 Process video conversion...")
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        video_info = get_available_info(video_path)
        qualities = video_info['qualities']

        VideoInfo.objects.get_or_create(
            video=video,
            defaults={
                "qualities": video_info['qualities'],
                "audio_languages": video_info.get('audio_tracks', []),
                "subtitle_languages": video_info.get('subtitle_languages', []),
                "fps": video_info['fps'],
                "width": video_info['width'],
                "height": video_info['height'],
                "duration": video_info['duration'],
                "size": video_info['size']
            }
        )
        
        video_dir = os.path.join(settings.MEDIA_ROOT, "videos", str(video.id))
        os.makedirs(video_dir, exist_ok=True)
        
        original_filename = os.path.basename(video_path)
        new_path = os.path.join(video_dir, original_filename)
        shutil.copy2(video_path, new_path)
        os.remove(video.fichier.path)
        video.fichier.name = os.path.relpath(new_path, settings.MEDIA_ROOT)
        video.save()
        
        qualities_base_dir = os.path.join(video_dir, "qualities")
        segments_base_dir = os.path.join(video_dir, "segments")
        os.makedirs(qualities_base_dir, exist_ok=True)
        os.makedirs(segments_base_dir, exist_ok=True)
        
        variant_manifests = []
        audio_manifests = []
        subtitle_manifests = []

        manifest, segments_dir, bandwidth, resolution, audio_m, subtitle_m = generate_video_segments(video_id, "original")
        if manifest:
            variant_manifests.append(("original", manifest, bandwidth, resolution))
            audio_manifests = audio_m
            subtitle_manifests = subtitle_m
            master_manifest_path = os.path.join(video_dir, "master.m3u8")
            with open(master_manifest_path, 'w') as f:
                f.write("#EXTM3U\n#EXT-X-VERSION:3\n")
                for lang, audio_manifest in audio_manifests:
                    relative_audio_path = os.path.relpath(audio_manifest, video_dir)
                    f.write(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{lang}",LANGUAGE="{lang}",URI="{relative_audio_path}"\n')
                for lang, subtitle_manifest in subtitle_manifests:
                    relative_subtitle_path = os.path.relpath(subtitle_manifest, video_dir)
                    f.write(f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{lang}",LANGUAGE="{lang}",URI="{relative_subtitle_path}"\n')
                for q, manifest, bandwidth, resolution in variant_manifests:
                    relative_video_path = os.path.relpath(manifest, video_dir)
                    f.write(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution},AUDIO="audio",SUBTITLES="subs",NAME="{q}"\n')
                    f.write(f"{relative_video_path}\n")
            video.master_manifest_file = os.path.relpath(master_manifest_path, settings.MEDIA_ROOT)
            video.segments_dir = os.path.relpath(segments_dir, settings.MEDIA_ROOT)
            video.save()
        for q in qualities[1:]:
            quality_dir = os.path.join(qualities_base_dir, q)
            os.makedirs(quality_dir, exist_ok=True)
            converted_path = convert_video_quality(new_path, q)
            quality_file_path = os.path.join(quality_dir, original_filename)
            os.rename(converted_path, quality_file_path)
            
            manifest, segments_dir, bandwidth, resolution, _, _ = generate_video_segments(video_id, q)
            if manifest:
                variant_manifests.append((q, manifest, bandwidth, resolution))
                with open(master_manifest_path, 'w') as f:
                    f.write("#EXTM3U\n#EXT-X-VERSION:3\n")
                    for lang, audio_manifest in audio_manifests:
                        relative_audio_path = os.path.relpath(audio_manifest, video_dir)
                        f.write(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="{lang}",LANGUAGE="{lang}",URI="{relative_audio_path}"\n')
                    for lang, subtitle_manifest in subtitle_manifests:
                        relative_subtitle_path = os.path.relpath(subtitle_manifest, video_dir)
                        f.write(f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{lang}",LANGUAGE="{lang}",URI="{relative_subtitle_path}"\n')
                    for q, manifest, bandwidth, resolution in variant_manifests:
                        relative_video_path = os.path.relpath(manifest, video_dir)
                        f.write(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution},AUDIO="audio",SUBTITLES="subs",NAME="{q}"\n')
                        f.write(f"{relative_video_path}\n")
                video.master_manifest_file = os.path.relpath(master_manifest_path, settings.MEDIA_ROOT)
                video.segments_dir = os.path.relpath(segments_dir, settings.MEDIA_ROOT)
                video.save()
        
        video.master_manifest_file = os.path.relpath(master_manifest_path, settings.MEDIA_ROOT)
        video.segments_dir = os.path.relpath(segments_dir, settings.MEDIA_ROOT)
        video.save()
        print("✅ Conversion et segmentation terminée.")
    except Exception as e:
        print(f"Erreur : {e}")

def generate_video_affichage(video_id):
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        output_dir = os.path.join(os.path.dirname(video_path), "affichages")
        os.makedirs(output_dir, exist_ok=True)
        affichage_path = extract_random_frame(video_path, output_dir)
        if affichage_path:
            video.affichage = os.path.relpath(affichage_path, MEDIA_ROOT)
            video.save()
            print("✅ Image d'affichage générée...")
        print("[!] Génération d'affichage finie...")
    except Exception as e:
        print(f"Erreur lors de la génération de l'image d'affichage : {e}")