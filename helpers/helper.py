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

from apps.users.models import User

import os, jwt, logging
import random, re, traceback
from helpers.constantes import *
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
    try:
        access_token = AccessToken(token)
        if "user_id" in access_token:
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        return None
    except (TokenError, User.DoesNotExist):
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