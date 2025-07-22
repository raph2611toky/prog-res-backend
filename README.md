# 🛠️ Plan d’architecture du backend Django (Plateforme de streaming)

Ce backend, développé en **Django**, est conçu pour gérer une plateforme de streaming vidéo moderne. Il est découpé logiquement pour répartir les responsabilités entre deux développeurs :

* **Moi-même (Développeur 1 – Responsable principal / architecte backend)**
* **Collaborateur (Développeur 2 – microservices)**

---

## 👤 Développeur 1 (Responsable principal)

### 🎯 Rôle :

Tu es chargé de la **conception, de la structure et du développement des parties critiques du backend**. Tu poses les fondations, la sécurité, l’architecture API REST, la base de données, et les modules complexes (ex : gestion des utilisateurs, flux vidéo, authentification, permissions, sockets, segmentation…).

### ✅ Tâches principales :

---

### 1. **Architecture du backend**

* Structure modulaire Django :

  * apps/

    * users/
    * videos/
    * streaming/
* Utilisation de Django REST Framework pour l’API.
* Mise en place du système de permissions/token JWT avec `SimpleJWT`.
* Configuration du stockage des vidéos (local ou cloud : AWS S3, etc.).

---

### 2. **Gestion des utilisateurs**

* Modèle utilisateur custom avec rôle (admin, user, guest).
* Authentification sécurisée (JWT).
* Système d’inscription/connexion.
* Stockage de l’avatar et informations personnelles.

---

### 3. **Upload de vidéo (avec progression)**

* Endpoint sécurisé POST `/api/videos/upload/`
* Utilisation de `Chunked Upload` ou `django-resumable` pour la progression.
* Affichage en temps réel du taux de chargement.
* Validation automatique de format, taille, durée, type, etc.

---

### 4. **Visualisation des vidéos**

* Endpoint GET `/api/videos/{id}/` :

  * Titre, description, vues, formats disponibles.
* Gestion du flux via **Socket** ou **HTTP progressive streaming** :

  * Support de `Range` headers pour le streaming.
  * Découpage de la vidéo (segmentation `.ts`) si HLS/Adaptive Bitrate.

---

### 5. **Contrôle de flux (WebSockets / SignalR alternatif)**

* Contrôle en direct (lecture/pause, vitesse, saut, langue) via WebSockets :

  * `ws://backend/ws/stream/{video_id}/`
  * Events : play, pause, seek, change\_quality, change\_lang.
* Gestion de la langue (sous-titres multi-langues + audio multilingue si dispo).
* Fallback pour utilisateurs en HTTP-only.

---

### 6. **Système de réaction et commentaire**

* Modèles : `Like`, `Dislike`, `Comment`
* API :

  * POST `/api/videos/{id}/like/`
  * POST `/api/videos/{id}/comment/`
  * GET `/api/videos/{id}/comments/`

---
### 7. **Segmentation des vidéos**

* Découpage des vidéos en chapitres/segments :

  * Stockage des segments HLS `.m3u8` / `.ts`
  * Ajout de métadonnées (timestamps, nom de chapitre)
* API pour récupérer la structure segmentée.

## 👥 Développeur 2 (Collaborateur – microservices)

### 🎯 Rôle :

Tu es responsable du développement **de microservices et tâches spécifiques**, qui interagissent avec le backend principal via des API REST ou des files d’événements (ex: RabbitMQ ou Redis PubSub si utilisé).

### ✅ Microservices confiés :

---

### 1. **Microservice de conversion vidéo**

* Convertir automatiquement les vidéos uploadées en plusieurs résolutions (240p, 480p, 720p, 1080p).
* Ajouter des sous-titres si disponibles.
* Générer les miniatures automatiquement.

> 📦 Stack : Python + `ffmpeg` + Celery pour traitement en tâche de fond.

---

### 2. **Information sur les vidéos**

* Informations utiles sur les videos :

  * taille d'un video en `octets` (K, M, G, T)
  * durré de la video en format `%H:%M:%S`
  * langue disponible dans la video
  * contient de sous titre ou pas ?
* 

---

## 🧠 Exemple de structure Django (backend principal) :

```
backend/
├── apps/
│   ├── users/
│   ├── videos/
│   ├── streaming/
├── media/
├── static/
├── config/
│   ├── settings.py
│   └── urls.py
└── manage.py
```

---

## 🛡️ Sécurité & Auth

* Authentification via JWT (`SimpleJWT`)
* Rôles : utilisateur simple / uploader / modérateur / admin
* Rate-limiting sur l’API
* CSRF & CORS configurés pour le frontend

---
