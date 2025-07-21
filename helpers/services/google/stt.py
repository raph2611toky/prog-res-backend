import speech_recognition as sr
from pydub import AudioSegment
import os
from pathlib import Path


MEDIA_ROOT = os.path.join(Path(__file__).resolve().parent.parent.parent.parent,'media')

def speech_to_text_fichier_audio(chemin_audio, langue='fr-FR'):
    recognizer = sr.Recognizer()
    
    chemin_audio = os.path.join(MEDIA_ROOT,chemin_audio)
    
    if not chemin_audio.endswith('.wav'):
        audio_wav = chemin_audio.replace(chemin_audio.split('.')[-1],'.wav')
        son = AudioSegment.from_file(chemin_audio)
        son.export(audio_wav, format="wav")
        chemin_final = audio_wav
    else:
        chemin_final = chemin_audio
    
    with sr.AudioFile(chemin_final) as source:
        audio = recognizer.record(source)
    
    try:
        texte = recognizer.recognize_google(audio, language=langue)
        return texte
    except sr.UnknownValueError:
        return "Impossible de comprendre l'audio."
    except sr.RequestError as e:
        return f"Erreur de service Google : {e}"
    finally:
        if chemin_audio != chemin_final and os.path.exists(chemin_final):
            os.remove(chemin_final)

# print(speech_to_text_fichier_audio("french_test.m4a", langue='fr-FR'))

# Anglais
print(speech_to_text_fichier_audio("english_test.wav", langue='en-US'))
