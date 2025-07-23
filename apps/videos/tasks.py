from apps.videos.models import Video

from helpers.helper import get_available_info, convert_video_quality

def process_video_conversion(video_id):
    try:
        video = Video.objects.get(id=video_id)
        video_path = video.fichier.path
        print(f"Chemin du fichier vidéo : {video_path}")
        qualites = get_available_info(video_path)['qualities']
        print(qualites)
        for q in qualites[1:]:
            convert_video_quality(video_path, q)
        print("✅ Tous les videos sont converties..")
    except Exception as e:
        print(e)