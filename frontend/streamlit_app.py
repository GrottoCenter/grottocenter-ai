import streamlit as st
import requests
import os
from dotenv import load_dotenv
from typing import Optional

# Charger les variables d'environnement
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

class APIClient:
    """Client pour communiquer avec l'API FastAPI"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def upload_pdf(self, file) -> dict:
        """Upload un fichier PDF via l'API"""
        try:
            files = {"file": (file.name, file, "application/pdf")}
            response = requests.post(
                f"{self.base_url}/pdf/upload",
                files=files,
                timeout=30
            )
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Erreur de connexion: {str(e)}"}, 500
    
    def health_check(self) -> bool:
        """Vérifie si l'API est accessible"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

def main():
    """Application Streamlit principale"""
    
    # Configuration de la page
    st.set_page_config(
        page_title="Grottocenter AI Tools",
        page_icon="🕳️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Titre principal
    st.title("🕳️ Grottocenter AI Tools")
    st.markdown("---")
    
    # Initialiser le client API
    api_client = APIClient(API_BASE_URL)
    
    # Vérification de la connexion API
    with st.sidebar:
        st.header("🔧 Status")
        if api_client.health_check():
            st.success("✅ API connectée")
        else:
            st.error("❌ API non accessible")
            st.warning(f"Vérifiez que l'API est démarrée sur {API_BASE_URL}")
    
    # Interface principale
    st.header("📄 Upload de PDF")
    
    # Upload de fichier
    uploaded_file = st.file_uploader(
        "Déposez votre fichier PDF ici",
        type=["pdf"],
        help="Taille maximale: 50MB"
    )
    
    if uploaded_file is not None:
        # Affichage des informations du fichier
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"📁 **Fichier:** {uploaded_file.name}")
        
        with col2:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.info(f"📊 **Taille:** {file_size_mb:.2f} MB")
        
        # Bouton d'upload
        if st.button("🚀 Uploader le PDF", type="primary"):
            if not api_client.health_check():
                st.error("❌ Impossible de se connecter à l'API")
                return
            
            # Barre de progression
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("⏳ Upload en cours...")
                progress_bar.progress(50)
                
                # Upload via API
                result, status_code = api_client.upload_pdf(uploaded_file)
                progress_bar.progress(100)
                
                # Traitement de la réponse
                if status_code == 200 and result.get("success"):
                    st.success("✅ PDF uploadé avec succès !")
                    
                    # Affichage des détails
                    with st.expander("📋 Détails", expanded=True):
                        st.write(f"**Nom du fichier:** {result.get('filename')}")
                        st.write(f"**Taille:** {result.get('file_size')} bytes")
                        st.write(f"**Date d'upload:** {result.get('upload_time')}")
                        
                else:
                    # Gestion des erreurs
                    error_msg = result.get("error", "Erreur inconnue")
                    st.error(f"❌ Erreur lors de l'upload: {error_msg}")
                    
            except Exception as e:
                st.error(f"❌ Erreur inattendue: {str(e)}")
            
            finally:
                progress_bar.empty()
                status_text.empty()
    
    # Informations dans la sidebar
    with st.sidebar:
        st.header("ℹ️ Informations")
        st.markdown("""
        **Formats acceptés:** PDF uniquement
        
        **Taille max:** 50 MB
        
        **API:** FastAPI
        """)
        
        st.header("🔗 Liens utiles")
        st.markdown(f"[📚 Documentation API]({API_BASE_URL}/docs)")

if __name__ == "__main__":
    main()