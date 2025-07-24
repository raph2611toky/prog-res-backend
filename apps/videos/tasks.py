from apps.videos.models import Video

from helpers.helper import get_available_info, convert_video_quality, extract_random_frame
import os, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

def generate_video_segments(video_id, quality=None):
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path if quality is None else f"{os.path.splitext(video.fichier.path)[0]}_{quality}.mp4"
        base_dir = os.path.dirname(video_path)
        segments_dir = os.path.join(base_dir, f"segments_{video.id}", quality or "original")
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
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        qualities = get_available_info(video_path)['qualities']
        base_dir = os.path.dirname(video_path)
        qualities_dir = os.path.join(base_dir, f"qualities_{video.id}")
        os.makedirs(qualities_dir, exist_ok=True)
        variant_manifests = []
        
        manifest, segments_dir = generate_video_segments(video_id)
        if manifest:
            video.manifest_file = manifest
            video.segments_dir = segments_dir
            variant_manifests.append(("original", manifest, "8000000", "1920x1080"))  
        for q in qualities[1:]:
            converted_path = convert_video_quality(video_path, q)
            manifest, segments_dir = generate_video_segments(video_id, q)
            if manifest:
                bandwidth = {
                    "2160p": "16000000",  # 16 Mbps pour 4K
                    "1440p": "8000000",   # 8 Mbps pour 2K
                    "1080p": "5000000",   # 5 Mbps pour Full HD
                    "720p": "2800000",    # 2.8 Mbps pour HD
                    "480p": "1400000",    # 1.4 Mbps
                    "360p": "800000",     # 800 Kbps
                    "240p": "400000",     # 400 Kbps
                    "144p": "200000"      # 200 Kbps
                }.get(q, "1000000")

                resolution = {
                    "2160p": "3840x2160", # 4K
                    "1440p": "2560x1440", # 2K
                    "1080p": "1920x1080", # Full HD
                    "720p": "1280x720",   # HD
                    "480p": "842x480",    # SD
                    "360p": "640x360",    # Basse qualité
                    "240p": "426x240",    # Très basse qualité
                    "144p": "256x144"
                }.get(q, "640x360")
                variant_manifests.append((q, manifest, bandwidth, resolution))

        master_manifest_path = os.path.join(qualities_dir, "master.m3u8")
        with open(master_manifest_path, 'w') as f:
            f.write("#EXTM3U\n")
            for q, manifest, bandwidth, resolution in variant_manifests:
                relative_path = os.path.relpath(manifest, qualities_dir)
                f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution}\n")
                f.write(f"{relative_path}\n")

        video.master_manifest_file = master_manifest_path
        video.save()
        print("✅ Conversion et segmentation terminées.")
    except Exception as e:
        print(f"Erreur : {e}")

def generate_video_affichage(video_id):
    try:
        print(MEDIA_ROOT)
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        output_dir = os.path.join(os.path.dirname(video_path), "affichages")
        os.makedirs(output_dir, exist_ok=True)
        affichage_path = extract_random_frame(video_path, output_dir)
        if affichage_path:
            video.affichage = os.path.relpath(affichage_path, MEDIA_ROOT)
            video.save()
        print("✅ Image d'affichage générée.")
    except Exception as e:
        print(f"Erreur lors de la génération de l'image d'affichage : {e}")