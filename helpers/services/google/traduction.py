from googletrans import Translator

def traduire_texte(texte, source_lang='fr', cible_lang='mg'):
    try:
        traducteur = Translator()
        resultat = traducteur.translate(texte, src=source_lang, dest=cible_lang)
        print(resultat)
        print("✅ Traduction reussie")
        return resultat.text
    except Exception as e:
        return f"Erreur lors de la traduction : {e}"


# print(traduire_texte("Bonjour, peut tu m'aider s'il te plait?? Chaque mois, j'ai des règles très douloureuse avec une odeur bizzare"))