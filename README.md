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

Ce projet vise à automatiser le traitement des documents PDF pour Grottocenter :

1. **Division automatique** : Séparer les revues PDF en articles individuels
2. **Extraction de métadonnées** : Récupérer automatiquement les informations (titre, auteur, date, etc.)
3. **Intégration Grottocenter** : Créer/mettre à jour les documents via l'API Grottocenter
4. **Interface utilisateur** : Simplifier les opérations pour les utilisateurs finaux

## 🏗️ Architecture

```
┌─────────────────┐    HTTP/JSON    ┌──────────────────┐
│   Streamlit     │ ◄──────────────► │   FastAPI        │
│   Frontend      │                 │   Backend        │
│   (Port 8501)   │                 │   (Port 8000)    │
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
                                    │  API Integration │
                                    └──────────────────┘
```

### Structure du projet

```
AI-serveur-for-Grottocenter-documents/
├── backend/                    # Serveur FastAPI
│   ├── api/                   # Routes API
│   │   └── pdf_routes.py      # Endpoints PDF
│   ├── models/                # Modèles Pydantic
│   │   └── pdf_models.py      # Modèles de données PDF
│   ├── services/              # Logique métier
│   │   └── pdf_service.py     # Service de traitement PDF
│   ├── utils/                 # Utilitaires
│   │   └── exceptions.py      # Exceptions personnalisées
│   └── main.py               # Point d'entrée FastAPI
├── frontend/                  # Interface Streamlit
│   └── streamlit_app.py      # Application principale
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

# Grottocenter API (pour intégration future)
GROTTOCENTER_API_URL=https://api.grottocenter.org
GROTTOCENTER_API_KEY=your_api_key_here
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
2. Glisser-déposer un fichier PDF (max 50MB)
3. Cliquer sur "Uploader le PDF"
4. Vérifier le statut et les détails du fichier

#### ✅ Validations automatiques
- **Format** : Vérification extension .pdf
- **Taille** : Limite à 50MB configurable
- **Intégrité** : Validation de la structure PDF
- **Sécurité** : Nom de fichier unique avec timestamp

## 📚 API Documentation

### Endpoints disponibles

#### `POST /pdf/upload`
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

**Réponse erreur (400/413) :**
```json
{
  "success": false,
  "error": "Le fichier dépasse la taille maximale autorisée de 50 MB",
  "error_code": "PDF_ERROR"
}
```

#### `GET /health`
Vérification de l'état de l'API.

**Réponse :**
```json
{
  "status": "ok",
  "message": "API is running"
}
```

#### `GET /pdf/health`
Vérification spécifique du service PDF.

**Réponse :**
```json
{
  "status": "ok",
  "service": "pdf"
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

### Phase 2 : IA Processing 🚧
- [ ] Division automatique PDF en articles
- [ ] Extraction métadonnées (titre, auteur, date)
- [ ] Prévisualisation et validation manuelle
- [ ] Traitement par lots

### Phase 3 : Intégration Grottocenter 🔮
- [ ] Connexion API Grottocenter
- [ ] Mapping automatique des métadonnées
- [ ] Création/mise à jour documents
- [ ] Gestion des collections et hiérarchies

### Phase 4 : Production 🔮
- [ ] Authentification utilisateurs
- [ ] Interface d'administration
- [ ] Monitoring et logs avancés
- [ ] Déploiement Docker
- [ ] Tests automatisés complets

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