from dotenv import load_dotenv
from datetime import timedelta, datetime
from django.utils import timezone as django_timezone
from django.conf import settings

from rest_framework.request import Request
from rest_framework_simplejwt.tokens import AccessToken, TokenError

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from base64 import b64decode,b64encode
from cryptography.hazmat.backends import default_backend
from difflib import SequenceMatcher
from moviepy.editor import VideoFileClip
from PIL import Image

from apps.users.models import User, default_created_at

import os, jwt, logging
import random, re
from helpers.constantes import *
import ffmpeg
import traceback

load_dotenv()
LOGGER = logging.getLogger(__name__)

def get_token_from_request(request: Request) -> str:
    authorization_header = request.headers.get('Authorization')
    if authorization_header and authorization_header.startswith('Bearer '):
        return authorization_header.split()[1]
    return None

def get_timezone():
    tz = os.getenv("TIMEZONE_HOURS")
    if '-' in tz:
        return django_timezone.now() - timedelta(hours=int(tz.strip()[1:]))
    return django_timezone.now()+timedelta(hours=int(tz))

def enc_dec(plaintext, type='e'):
    cipher = Cipher(algorithms.AES(os.getenv('AES_KEY').encode()), modes.CFB(os.getenv('AES_IV').encode()), backend=default_backend())
    if type == 'e':
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return b64encode(ciphertext).decode()  
    elif type == 'd':
        decryptor = cipher.decryptor()
        ciphertext = b64decode(plaintext)
        decrypted_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        return decrypted_plaintext.decode()
    else:
        return 'type de cryptage inconnu' 

def generate_jwt_token(payload: dict, expires_in_minutes: int = 1440) -> str:
    expiration = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    payload.update({"exp": expiration})
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.SIMPLE_JWT['ALGORITHM'])
    return token

def decode_jwt_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.SIMPLE_JWT['ALGORITHM']])

def get_user(token):
    if not token:
        LOGGER.error("Aucun token fourni")
        return None
    try:
        access_token = AccessToken(token)
        user_id = access_token.get('user_id')
        if not user_id:
            LOGGER.error("Le token ne contient pas 'user_id'")
            return None
        user = User.objects.get(id=user_id)
        LOGGER.info(f"Utilisateur récupéré : {user}")
        return user
    except TokenError as e:
        LOGGER.error(f"Token invalide : {e}")
        return None
    except User.DoesNotExist:
        LOGGER.error(f"Utilisateur avec id {user_id} n'existe pas")
        return None

def calcule_de_similarite_de_phrase(text1, text2):
    def clean_text(text):
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.strip()
    text1_clean = clean_text(text1)
    text2_clean = clean_text(text2)
    words1 = text1_clean.split()
    words2 = text2_clean.split()
    if not words1 or not words2:
        return 0.0
    total_similarity = 0.0
    for word1 in words1:
        best_similarity = 0.0
        for word2 in words2:
            similarity = SequenceMatcher(None, word1, word2).ratio()
            if similarity > best_similarity:
                best_similarity = similarity
        total_similarity += best_similarity
    final_score = total_similarity / len(words1)
    return final_score

def get_video_info(file_path):
    try:
        clip = VideoFileClip(file_path)
        height = clip.h
        standard_qualities = {
            2160: "2160p (4K)",
            1440: "1440p (2K)",
            1080: "1080p (Full HD)",
            720: "720p (HD)",
            480: "480p",
            360: "360p",
            240: "240p"
        }
        quality = next((q for h, q in standard_qualities.items() if height >= h - 10), f"{height}p")
        info = {
            'size': os.path.getsize(file_path),
            'duration': clip.duration,
            'width': clip.w,
            'height': height,
            'fps': clip.fps,
            'quality': quality
        }
        clip.close()
        return info
    except Exception as e:
        raise Exception(str(e)+str(traceback.format_exc()))
    
def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 octets"
    units = ["octets", "Ko", "Mo", "Go", "To"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def format_duration(seconds):
    if seconds <= 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def get_available_info(file_path):
    print("[❕] Getting available info....")
    if not os.path.exists(file_path):
        raise Exception(f"[❗]le chemin de fichier {file_path} est introuvable, veuillez verifiez...")
    try:
        clip = VideoFileClip(file_path)
        height = clip.h
        
        standard_qualities = [
            (2160, "2160p (4K)"),
            (1440, "1440p (2K)"),
            (1080, "1080p (Full HD)"),
            (720, "720p (HD)"),
            (480, "480p"),
            (360, "360p"),
            (240, "240p"),
            (144, "144p")
        ]
        
        available_qualities = [quality for threshold, quality in standard_qualities if height >= threshold]
        quality = next((q for h, q in {
            2160: "2160p (4K)",
            1440: "1440p (2K)",
            1080: "1080p (Full HD)",
            720: "720p (HD)",
            480: "480p",
            360: "360p",
            240: "240p"
        }.items() if height >= h - 10), f"{height}p")
        probe = ffmpeg.probe(file_path)
        video_info = {
            'qualities': available_qualities,
            'size': os.path.getsize(file_path),
            'size_formatted': format_file_size(os.path.getsize(file_path)),
            'duration': clip.duration,
            'duration_formatted': format_duration(clip.duration),
            'width': clip.w,
            'height': clip.h,
            'fps': clip.fps,
            'has_subtitles': False,
            'subtitle_languages': [],
            'audio_tracks': [],
            'has_multiple_languages': False,
            'quality': quality
        }
        
        subtitle_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'subtitle']
        if subtitle_streams:
            video_info['has_subtitles'] = True
            video_info['subtitle_languages'] = [
                stream.get('tags', {}).get('language', 'unknown') for stream in subtitle_streams
            ]
        
        audio_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
        audio_tracks = []
        for stream in audio_streams:
            language = stream.get('tags', {}).get('language', 'unknown')
            title = stream.get('tags', {}).get('title', '')
            if title:
                audio_tracks.append(f"{language} ({title})")
            elif language not in audio_tracks:
                audio_tracks.append(language)
        video_info['audio_tracks'] = audio_tracks
        video_info['has_multiple_languages'] = len(set(audio_tracks)) > 1
        
        clip.close()
        return video_info
    
    except Exception as e:
        if 'clip' in locals():
            clip.close()
        print(traceback.format_exc())
        raise Exception(f"Erreur lors de l'obtention des informations vidéo: {str(e)}")

def custom_resize(clip, newsize, resample=Image.Resampling.LANCZOS):
    return clip.resize(newsize, resample=resample)

def convert_video_quality(file_path, target_quality):
    try:
        clip = VideoFileClip(file_path)
        
        quality_heights = {
            "2160p": 2160,
            "1440p": 1440,
            "1080p": 1080,
            "720p": 720,
            "480p": 480,
            "360p": 360,
            "240p": 240,
            "144p": 144
        }
        
        target_height = None
        for quality, height in quality_heights.items():
            if target_quality.startswith(quality):
                target_height = height
                break
                
        if not target_height:
            clip.close()
            raise ValueError(f"Qualité cible '{target_quality}' non supportée")
            
        if clip.h < target_height:
            clip.close()
            raise ValueError(f"La vidéo source ({clip.h}p) est de qualité inférieure à la qualité cible ({target_quality})")
        
        aspect_ratio = clip.w / clip.h
        target_width = int(target_height * aspect_ratio)
        target_width = target_width if target_width % 2 == 0 else target_width + 1
        
        file_name, file_ext = os.path.splitext(file_path)
        output_path = f"{file_name}_{target_quality}{file_ext}"
        
        resized_clip = clip.resize(height=target_height, width=target_width)
        
        resized_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            threads=4
        )
        
        clip.close()
        resized_clip.close()
        
        return output_path
    
    except Exception as e:
        if 'clip' in locals():
            clip.close()
        if 'resized_clip' in locals():
            resized_clip.close()
        print(traceback.format_exc())
        raise Exception(f"Erreur lors de la conversion de la vidéo: {str(e)}")

def format_views(views):
    if views >= 1000000:
        return f"{views / 1000000:.1f}M"
    elif views >= 1000:
        return f"{views / 1000:.1f}K"
    else:
        return str(views)

def format_elapsed_time(uploaded_at):
    now = default_created_at()
    delta = now - uploaded_at

    if delta.total_seconds() < 60:
        seconds = int(delta.total_seconds())
        return "maintenant" if seconds < 10 else f"{seconds} s"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes} min"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours} h"
    elif uploaded_at.date() == now.date():
        return "aujourd'hui"
    elif (now - uploaded_at).days <= 7:
        return "cette semaine"
    elif uploaded_at.month == now.month and uploaded_at.year == now.year:
        return "ce mois"
    elif uploaded_at.year == now.year:
        return "cette année"
    else:
        years = now.year - uploaded_at.year
        return f"{years} ans"

def extract_random_frame(video_path, output_dir):
    try:
        clip = VideoFileClip(video_path)
        duration = clip.duration
        random_time = random.uniform(0, duration) 
        output_path = os.path.join(output_dir, f"affichage_{os.path.basename(video_path).split('.')[0]}.jpg")
        clip.save_frame(output_path, t=random_time)
        clip.close()
        return output_path
    except Exception as e:
        print(f"Erreur lors de l'extraction de l'image : {e}")
        return None