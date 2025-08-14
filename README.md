# 🕳️ Grottocenter AI Tools

Serveur d'outils IA pour automatiser le traitement des documents PDF de Grottocenter (division d'articles, extraction de métadonnées, intégration API).

## 📋 Table des matières

- [🎯 Objectifs](#-objectifs)
- [🏗️ Architecture](#️-architecture)
- [🚀 Installation](#-installation)
- [💻 Utilisation](#-utilisation)
- [📚 API Documentation](#-api-documentation)
- [🛠️ Développement](#️-développement)
- [📦 Technologies](#-technologies)
- [🔮 Roadmap](#-roadmap)

## 🎯 Objectifs

Ce projet vise à automatiser le traitement des documents PDF et la gestion des collections pour Grottocenter :

1. **Division automatique** : Séparer les revues PDF en articles individuels
2. **Extraction de métadonnées** : Récupérer automatiquement les informations (titre, auteur, date, etc.)
3. **Intégration Grottocenter** : Connexion complète à l'API Grottocenter pour créer/mettre à jour les documents
4. **Gestion des collections** : Interface web pour éditer les propriétés des documents et collections
5. **Héritage de propriétés** : Appliquer automatiquement les propriétés d'une collection parent à ses documents descendants
6. **Interface utilisateur** : Interfaces web spécialisées pour simplifier toutes les opérations

## 🏗️ Architecture

```
┌─────────────────┐    HTTP/JSON    ┌──────────────────┐
│   Streamlit     │ ◄──────────────► │   FastAPI        │
│   Frontend      │                 │   Backend        │
│   (Port 8501)   │                 │   (Port 8000)    │
│                 │                 │                  │
│ • PDF Upload    │                 │ • PDF Routes     │
│ • Doc Editor    │                 │ • Doc Routes     │
│ • Inheritance   │                 │ • Services       │
└─────────────────┘                 └──────────────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  Services IA     │
                                    │  - PDF Division  │
                                    │  - Métadonnées   │
                                    │  - Validation    │
                                    └──────────────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  Grottocenter    │
                                    │  API Client      │
                                    │  - CRUD Documents│
                                    │  - Validation    │
                                    │  - Inheritance   │
                                    └──────────────────┘
```

### Structure du projet

```
AI-serveur-for-Grottocenter-documents/
├── backend/                    # Serveur FastAPI
│   ├── api/                   # Routes API
│   │   ├── pdf_routes.py      # Endpoints PDF
│   │   └── document_routes.py # Endpoints documents Grottocenter
│   ├── client/                # Client API Grottocenter
│   │   ├── base_client.py     # Client HTTP asynchrone
│   │   └── exceptions.py      # Exceptions API
│   ├── models/                # Modèles Pydantic
│   │   └── pdf_models.py      # Modèles de données PDF
│   ├── schemas/               # Schémas de données
│   │   └── document_schemas.py # Schémas documents
│   ├── services/              # Logique métier
│   │   ├── pdf_service.py     # Service de traitement PDF
│   │   └── document_service.py # Service documents Grottocenter
│   ├── utils/                 # Utilitaires
│   │   ├── exceptions.py      # Exceptions personnalisées
│   │   └── csv_utils.py       # Utilitaires CSV
│   ├── validators/            # Validateurs
│   └── main.py               # Point d'entrée FastAPI
├── frontend/                  # Interface Streamlit
│   ├── components/            # Composants UI
│   │   ├── collection_editor.py    # Éditeur de documents
│   │   ├── collection_inheritance.py # Héritage de propriétés
│   │   └── pdf_processing.py       # Traitement PDF
│   └── streamlit_app.py      # Application principale
├── config/                    # Configuration
│   └── collection_config.ini  # Config collections
├── uploads/                   # Stockage temporaire PDF
├── run_backend.py            # Script de lancement backend
├── run_frontend.py           # Script de lancement frontend
├── requirements.txt          # Dépendances Python
├── .env                      # Variables d'environnement
└── README.md                # Documentation
```

## 🚀 Installation

### Prérequis par OS

#### 🐧 Linux (Ubuntu/Debian)
- Python 3.8+ (généralement pré-installé)
- pip et venv
- Git
- Accès sudo pour installer les paquets système

#### 🍎 macOS
- macOS 10.15+ (Catalina ou plus récent)
- Python 3.8+ 
- Git (peut être installé via Xcode Command Line Tools)
- Homebrew (recommandé mais optionnel)

#### 🪟 Windows
- Windows 10/11
- Python 3.8+ depuis [python.org](https://www.python.org/downloads/)
- Git depuis [git-scm.com](https://git-scm.com/download/win)
- PowerShell ou Command Prompt
- Droits administrateur pour l'installation initiale

### Installation par OS

#### 🐧 Ubuntu/Debian (Linux)

```bash
# Installer les dépendances système
sudo apt update
sudo apt install python3-pip python3-venv python3-dev git

# Cloner le repository
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt
```

#### 🍎 macOS

**Option 1 : Avec Homebrew (recommandé)**
```bash
# Installer Homebrew si pas déjà fait
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Installer Python et Git
brew install python git

# Cloner le repository
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt
```

**Option 2 : Avec Python natif**
```bash
# Vérifier que Python 3.8+ est installé
python3 --version

# Cloner le repository (installer Git si nécessaire depuis https://git-scm.com/)
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt
```

#### 🪟 Windows

**Option 1 : Avec PowerShell (recommandé)**
```powershell
# Vérifier que Python 3.8+ est installé
python --version
# Si pas installé, télécharger depuis https://www.python.org/downloads/

# Installer Git si nécessaire depuis https://git-scm.com/download/win

# Cloner le repository
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate

# Installer les dépendances Python
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Option 2 : Avec Command Prompt (cmd)**
```cmd
# Vérifier Python
python --version

# Cloner le repository
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate.bat

# Installer les dépendances Python
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Option 3 : Avec Git Bash (si installé)**
```bash
# Cloner le repository
git clone git@github.com:GrottoCenter/AI-serveur-for-Grottocenter-documents.git
cd AI-serveur-for-Grottocenter-documents

# Créer l'environnement virtuel
python -m venv venv
source venv/Scripts/activate

# Installer les dépendances Python
pip install --upgrade pip
pip install -r requirements.txt
```

### Configuration

Copier et modifier le fichier d'environnement :

```bash
cp .env.example .env  # Si disponible
# ou créer directement .env avec :
```

```env
# API Configuration
API_HOST=127.0.0.1
API_PORT=8000
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=50

# Streamlit Configuration  
STREAMLIT_PORT=8501
API_BASE_URL=http://127.0.0.1:8000

# Grottocenter API (configuration active)
GROTTOCENTER_URL=https://api.grottocenter.org
GROTTOCENTER_TOKEN=your_bearer_token_here
```

## 💻 Utilisation

### Démarrage par OS

#### 🐧 Linux / 🍎 macOS

**Terminal 1 - Backend FastAPI :**
```bash
source venv/bin/activate
python run_backend.py
```

**Terminal 2 - Frontend Streamlit :**
```bash
source venv/bin/activate  
python run_frontend.py
```

#### 🪟 Windows

**PowerShell/Command Prompt - Terminal 1 :**
```powershell
venv\Scripts\activate
python run_backend.py
```

**PowerShell/Command Prompt - Terminal 2 :**
```powershell
venv\Scripts\activate
python run_frontend.py
```

**Git Bash - Terminal 1 :**
```bash
source venv/Scripts/activate
python run_backend.py
```

**Git Bash - Terminal 2 :**
```bash
source venv/Scripts/activate
python run_frontend.py
```

### Accès aux interfaces

- **Interface utilisateur** : http://localhost:8501
- **Documentation API** : http://localhost:8000/docs
- **API Health Check** : http://localhost:8000/health

### Fonctionnalités actuelles

#### 📄 Upload de PDF
1. Ouvrir l'interface Streamlit
2. Naviguer vers l'onglet "📄 Traitement PDF"
3. Glisser-déposer un fichier PDF (max 50MB)
4. Cliquer sur "Uploader le PDF"
5. Vérifier le statut et les détails du fichier

#### 🗂️ Édition de documents
1. Naviguer vers l'onglet "🗂️ Éditeur de document"
2. Entrer l'ID du document Grottocenter à modifier
3. Modifier les champs (titre, description, licence, etc.)
4. Enregistrer et valider automatiquement

#### 🏗️ Héritage de propriétés
1. Naviguer vers l'onglet "🏗️ Héritage de collection"
2. Charger une collection parent par son ID
3. Optionnellement modifier les propriétés de la collection
4. Sélectionner les champs à hériter (licence, langue, etc.)
5. Charger automatiquement tous les documents descendants
6. Prévisualiser les changements
7. Appliquer l'héritage en un clic sur tous les descendants

#### ✅ Validations automatiques
- **Format** : Vérification extension .pdf
- **Taille** : Limite à 50MB configurable
- **Intégrité** : Validation de la structure PDF
- **Sécurité** : Nom de fichier unique avec timestamp
- **API Grottocenter** : Validation automatique des documents modifiés

## 📚 API Documentation

### Endpoints disponibles

#### Routes PDF

##### `POST /pdf/upload`
Upload d'un fichier PDF avec validation complète.

**Paramètres :**
- `file` (multipart/form-data) : Fichier PDF à uploader

**Réponse succès (200) :**
```json
{
  "success": true,
  "message": "PDF uploadé avec succès",
  "filename": "20241128_143022_document.pdf",
  "file_size": 2048576,
  "upload_time": "2024-11-28T14:30:22.123456"
}
```

##### `GET /pdf/health`
Vérification spécifique du service PDF.

#### Routes Documents Grottocenter

##### `GET /documents/{doc_id}`
Récupérer un document Grottocenter par son ID.

**Réponse :**
```json
{
  "id": 12345,
  "title": "Titre du document",
  "description": "Description...",
  "license": {"id": 1, "name": "CC-BY-SA"},
  "mainLanguage": "fr",
  "...": "autres champs"
}
```

##### `PUT /documents/{doc_id}`
Mettre à jour un document Grottocenter.

**Payload :**
```json
{
  "title": "Nouveau titre",
  "description": "Nouvelle description",
  "license": {"id": 2}
}
```

##### `PUT /documents/{doc_id}/validate`
Valider un document Grottocenter.

##### `PUT /documents/{doc_id}/update-and-validate`
Mettre à jour et valider un document en une seule opération.

##### `GET /documents/{doc_id}/children`
Récupérer les enfants directs d'un document.

##### `GET /documents/{doc_id}/descendants`
Récupérer tous les descendants (enfants + petits-enfants) d'un document.

**Réponse :**
```json
{
  "documents": [{"id": 123, "title": "...", "type": "..."}],
  "total": 42
}
```

##### `POST /documents/{doc_id}/apply-inheritance`
Appliquer l'héritage des propriétés sur les documents descendants.

**Payload :**
```json
{
  "heritable_fields": {
    "license": {"id": 1},
    "mainLanguage": "fr"
  },
  "child_ids": [123, 124, 125]
}
```

**Réponse :**
```json
{
  "success": [
    {"id": 123, "title": "Document 1", "changes": {...}}
  ],
  "errors": [],
  "total": 3
}
```

#### Routes générales

##### `GET /health`
Vérification de l'état de l'API.

**Réponse :**
```json
{
  "status": "ok",
  "message": "API is running"
}
```

## 🛠️ Développement

### Structure modulaire

**Backend FastAPI :**
- **Models** : Définition des structures de données avec Pydantic
- **Services** : Logique métier (traitement PDF, validation)
- **Routes** : Définition des endpoints API
- **Exceptions** : Gestion centralisée des erreurs

**Frontend Streamlit :**
- Interface utilisateur intuitive
- Communication API via requests
- Gestion d'état et feedback temps réel

### Ajout de nouvelles fonctionnalités

1. **Nouveau service** : Créer dans `backend/services/`
2. **Nouveau modèle** : Ajouter dans `backend/models/`
3. **Nouvelle route** : Définir dans `backend/api/`
4. **Interface** : Étendre `frontend/streamlit_app.py`

### Tests

```bash
# Installation des dépendances de test
pip install pytest pytest-asyncio httpx

# Lancement des tests (quand implémentés)
pytest tests/
```

### Debugging

**Backend :**
- Logs automatiques FastAPI
- Mode reload activé en développement
- Documentation interactive sur /docs

**Frontend :**
- Debugging Streamlit avec `st.write()` 
- Logs de connexion API dans la sidebar
- Mode développement Streamlit

### Troubleshooting

#### 🐧 Linux (Ubuntu/Debian)
```bash
# Si erreur "ensurepip is not available"
sudo apt install python3.10-venv python3-pip

# Si problème de permissions
sudo chown -R $USER:$USER ./uploads

# Si port déjà utilisé
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:8501 | xargs kill -9  # Frontend
```

#### 🍎 macOS
```bash
# Si problème avec Python
brew reinstall python

# Si erreur SSL/certificat
/Applications/Python\ 3.x/Install\ Certificates.command

# Si port déjà utilisé
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:8501 | xargs kill -9  # Frontend
```

#### 🪟 Windows
```powershell
# Si Python non reconnu
# Réinstaller Python depuis python.org avec "Add to PATH" coché

# Si problème d'exécution de scripts
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Si port déjà utilisé
netstat -ano | findstr :8000  # Trouver le PID
taskkill /PID <PID> /F        # Tuer le processus

# Si problème avec venv
python -m pip install --upgrade pip setuptools wheel
```

**Problèmes communs à tous les OS :**
```bash
# Si erreur de dépendances
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall

# Si problème de cache pip
pip cache purge

# Si erreur de modules
python -m pip install --editable .
```

## 📦 Technologies

### Backend
- **[FastAPI](https://fastapi.tiangolo.com/)** (0.104.1) : Framework web moderne et rapide
- **[Uvicorn](https://www.uvicorn.org/)** (0.24.0) : Serveur ASGI haute performance
- **[Pydantic](https://pydantic-docs.helpmanual.io/)** : Validation et sérialisation des données
- **[Python-multipart](https://github.com/andrew-d/python-multipart)** : Gestion des uploads multipart
- **[PyPDF2](https://pypdf2.readthedocs.io/)** (3.0.1) : Manipulation et validation PDF
- **[HTTPX](https://www.python-httpx.org/)** : Client HTTP asynchrone moderne pour l'API Grottocenter

### Frontend  
- **[Streamlit](https://streamlit.io/)** (1.28.1) : Framework d'applications web Python
- **[Requests](https://requests.readthedocs.io/)** (2.31.0) : Client HTTP simple

### Utilitaires
- **[Python-dotenv](https://github.com/theskumar/python-dotenv)** (1.0.0) : Gestion variables d'environnement

### Futures intégrations
- **Modèles IA** : Pour division PDF et extraction métadonnées
- **Base de données** : PostgreSQL ou SQLite pour persistance
- **Celery/Redis** : Traitement asynchrone des tâches lourdes
- **Docker** : Containerisation pour déploiement

## 🔮 Roadmap

### Phase 1 : Foundation ✅
- [x] Architecture FastAPI + Streamlit
- [x] Upload et validation PDF
- [x] Gestion d'erreurs robuste
- [x] Interface utilisateur intuitive

### Phase 2 : Intégration Grottocenter ✅
- [x] Connexion API Grottocenter (client HTTPX asynchrone)
- [x] CRUD complet des documents
- [x] Validation automatique des documents
- [x] Interface web pour édition des documents
- [x] Gestion des collections et hiérarchies
- [x] Héritage automatique des propriétés parent-enfant
- [x] Interface web spécialisée pour l'héritage
- [x] Gestion des descendants (récursive)

### Phase 3 : IA Processing 🚧
- [ ] Division automatique PDF en articles
- [ ] Extraction métadonnées (titre, auteur, date)
- [ ] Prévisualisation et validation manuelle
- [ ] Traitement par lots
- [ ] Intégration IA avec workflow de collections

### Phase 4 : Production 🔮
- [ ] Authentification utilisateurs
- [ ] Interface d'administration
- [ ] Monitoring et logs avancés
- [ ] Déploiement Docker
- [ ] Tests automatisés complets
- [ ] Optimisation performances (mise en cache, pagination)
- [ ] Gestion des erreurs avancée (retry, circuit breaker)

## 🤝 Contribution

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/amazing-feature`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing-feature`)
5. Ouvrir une Pull Request

## 📝 License

Ce projet est sous licence AGPL-3.0. Voir le fichier `LICENSE` pour plus de détails.

## 🙋‍♂️ Support

Pour toute question ou problème :
- Ouvrir une [issue GitHub](https://github.com/GrottoCenter/AI-serveur-for-Grottocenter-documents/issues)
- Contacter l'équipe Grottocenter

---

**Status du projet :** 🚧 En développement actif

**Version :** 0.1.0 (Architecture initiale)