from apps.videos.models import Video
from helpers.helper import get_available_info, convert_video_quality, extract_random_frame
import os, subprocess, shutil
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
            video_path = os.path.join(video_dir, "qualities", quality, f"{original_filename}")
        
        segments_dir = os.path.join(video_dir, "segments", quality or "original")
        os.makedirs(segments_dir, exist_ok=True)
        manifest_file = os.path.join(segments_dir, "manifest.m3u8")
        
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-profile:v", "baseline",
            "-level", "3.0",
            "-start_number", "0",
            "-hls_time", "10",
            "-hls_list_size", "0",
            "-f", "hls",
            manifest_file
        ]
        subprocess.run(cmd, check=True)
        
        return manifest_file, segments_dir
    except Exception as e:
        print(f"Erreur lors de la génération des segments : {e}")
        return None, None

def process_video_conversion(video_id):
    print("🎊 Process video conversion...")
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        video_info = get_available_info(video_path)
        qualities = video_info['qualities']
        
        video_dir = os.path.join(settings.MEDIA_ROOT, "videos", str(video.id))
        os.makedirs(video_dir, exist_ok=True)
        
        original_filename = os.path.basename(video_path)
        new_path = os.path.join(video_dir, original_filename)
        shutil.copy2(video_path, new_path)
        video.fichier.name = os.path.relpath(new_path, settings.MEDIA_ROOT)
        video.save()
        
        qualities_base_dir = os.path.join(video_dir, "qualities")
        segments_base_dir = os.path.join(video_dir, "segments")
        os.makedirs(qualities_base_dir, exist_ok=True)
        os.makedirs(segments_base_dir, exist_ok=True)
        
        variant_manifests = []
        manifest, segments_dir = generate_video_segments(video_id, "original")
        if manifest:
            variant_manifests.append(("original", manifest, "8000000", "1920x1080"))
        for q in qualities[1:]:
            quality_dir = os.path.join(qualities_base_dir, q)
            os.makedirs(quality_dir, exist_ok=True)
            converted_path = convert_video_quality(new_path, q)
            quality_file_path = os.path.join(quality_dir, original_filename)
            os.rename(converted_path, quality_file_path)
            
            manifest, segments_dir = generate_video_segments(video_id, q)
            if manifest:
                bandwidth = {
                    "2160p": "16000000",
                    "1440p": "8000000",
                    "1080p": "5000000",
                    "720p": "2800000",
                    "480p": "1400000",
                    "360p": "800000",
                    "240p": "400000",
                    "144p": "200000"
                }.get(q, "1000000")
                resolution = {
                    "2160p": "3840x2160",
                    "1440p": "2560x1440",
                    "1080p": "1920x1080",
                    "720p": "1280x720",
                    "480p": "842x480",
                    "360p": "640x360",
                    "240p": "426x240",
                    "144p": "256x144"
                }.get(q, "640x360")
                variant_manifests.append((q, manifest, bandwidth, resolution))
        master_manifest_path = os.path.join(video_dir, "master.m3u8")
        with open(master_manifest_path, 'w') as f:
            f.write("#EXTM3U\n")
            for q, manifest, bandwidth, resolution in variant_manifests:
                relative_path = os.path.relpath(manifest, video_dir)
                f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}\n")
                f.write(f"{relative_path}\n")
        
        video.master_manifest_file = os.path.relpath(master_manifest_path, settings.MEDIA_ROOT)
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