"""
Page Streamlit pour le traitement des PDF
"""

import streamlit as st
import requests
from typing import Dict, Any
import os
import time

def show_pdf_processing_page(api_base_url: str):
    """Page principale de traitement PDF"""
    
    # Vérifier la santé du service PDF
    try:
        health_response = requests.get(f"{api_base_url}/pdf/health")
        service_healthy = health_response.status_code == 200
    except requests.exceptions.RequestException:
        service_healthy = False
    
    # Afficher l'état de connexion
    if service_healthy:
        st.success("✅ Service PDF disponible")
    else:
        st.error("❌ Service PDF non disponible")
        st.error("Vérifiez que le backend est démarré et accessible.")
        return
    
    # Tabs principales
    tab1, tab2, tab3 = st.tabs([
        "📤 Upload PDF", 
        "🤖 Traitement IA (à venir)", 
        "📊 Historique"
    ])
    
    with tab1:
        show_pdf_upload_tab(api_base_url)
    
    with tab2:
        show_ai_processing_tab(api_base_url)
    
    with tab3:
        show_pdf_history_tab(api_base_url)


def show_pdf_upload_tab(api_base_url: str):
    """Tab pour l'upload de PDF"""
    st.subheader("📤 Upload et validation PDF")
    
    # Informations sur les limitations
    st.info("""
    **Limitations actuelles:**
    - Taille maximale: 50 MB
    - Format: PDF uniquement
    - Validation: Structure et intégrité du fichier
    """)
    
    # Upload du fichier
    uploaded_file = st.file_uploader(
        "Choisir un fichier PDF",
        type=['pdf'],
        help="Sélectionnez un document PDF à traiter (max 50MB)"
    )
    
    if uploaded_file is not None:
        # Afficher les informations du fichier
        file_size_mb = uploaded_file.size / (1024 * 1024)
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📄 **Fichier:** {uploaded_file.name}")
            st.info(f"📊 **Taille:** {file_size_mb:.2f} MB")
        
        with col2:
            if file_size_mb > 50:
                st.error("❌ Fichier trop volumineux (> 50 MB)")
                return
            else:
                st.success("✅ Taille acceptable")
        
        # Section options d'upload
        st.markdown("---")
        st.subheader("⚙️ Options de traitement")
        
        # Options futures (pour préparation)
        col1, col2 = st.columns(2)
        
        with col1:
            validate_structure = st.checkbox(
                "🔍 Validation approfondie",
                value=True,
                help="Vérifier la structure interne du PDF"
            )
        
        with col2:
            extract_metadata = st.checkbox(
                "📋 Extraction métadonnées",
                value=False,
                disabled=True,
                help="🚧 Fonctionnalité à venir"
            )
        
        # Bouton d'upload
        st.markdown("---")
        
        col_upload, col_info = st.columns([1, 2])
        
        with col_upload:
            if st.button("🚀 Uploader le PDF", type="primary", use_container_width=True):
                upload_pdf_file(api_base_url, uploaded_file, validate_structure)
        
        with col_info:
            st.markdown("""
            **Après l'upload:**
            1. ✅ Validation du fichier
            2. 📁 Stockage sécurisé  
            3. 🔍 Analyse de structure
            4. 📊 Rapport de validation
            """)


def upload_pdf_file(api_base_url: str, uploaded_file, validate_structure: bool):
    """Upload et traitement d'un fichier PDF"""
    
    # Créer la barre de progression
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Étape 1: Préparation
        status_text.text("📋 Préparation de l'upload...")
        progress_bar.progress(0.2)
        time.sleep(0.5)
        
        # Étape 2: Upload
        status_text.text("📤 Upload du fichier...")
        progress_bar.progress(0.4)
        
        # Préparer les données
        files = {"file": (uploaded_file.name, uploaded_file.read(), "application/pdf")}
        
        # Effectuer l'upload
        response = requests.post(f"{api_base_url}/pdf/upload", files=files, timeout=60)
        
        # Étape 3: Traitement
        status_text.text("🔍 Validation en cours...")
        progress_bar.progress(0.7)
        time.sleep(0.5)
        
        # Étape 4: Finalisation
        status_text.text("✅ Finalisation...")
        progress_bar.progress(0.9)
        
        if response.status_code == 200:
            result = response.json()
            progress_bar.progress(1.0)
            status_text.text("🎉 Upload terminé avec succès!")
            
            # Afficher les résultats
            st.success("✅ PDF uploadé et validé avec succès!")
            
            # Stocker dans la session pour référence
            st.session_state.last_uploaded_pdf = result
            
            # Afficher les détails
            show_upload_results(result)
            
        else:
            # Gérer les erreurs
            progress_bar.empty()
            status_text.empty()
            
            try:
                error_data = response.json()
                error_message = error_data.get("error", "Erreur inconnue")
            except:
                error_message = response.text
            
            st.error(f"❌ Erreur lors de l'upload: {error_message}")
            
            # Suggestions basées sur le code d'erreur
            if response.status_code == 413:
                st.error("📊 Le fichier est trop volumineux. Réduisez la taille ou divisez le document.")
            elif response.status_code == 400:
                st.error("📄 Format de fichier invalide. Vérifiez qu'il s'agit bien d'un PDF.")
            
    except requests.exceptions.Timeout:
        progress_bar.empty()
        status_text.empty()
        st.error("⏱️ Timeout lors de l'upload. Le fichier est peut-être trop volumineux.")
        
    except requests.exceptions.ConnectionError:
        progress_bar.empty()
        status_text.empty()
        st.error("🔌 Erreur de connexion. Vérifiez que le serveur backend est accessible.")
        
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Erreur inattendue: {e}")


def show_upload_results(result: Dict[str, Any]):
    """Afficher les résultats d'upload"""
    
    st.markdown("---")
    st.subheader("📊 Résultats de l'upload")
    
    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Statut", "✅ Validé" if result.get("success") else "❌ Erreur")
    
    with col2:
        file_size_mb = result.get("file_size", 0) / (1024 * 1024)
        st.metric("Taille", f"{file_size_mb:.2f} MB")
    
    with col3:
        st.metric("Nom de fichier", result.get("filename", "N/A"))
    
    with col4:
        upload_time = result.get("upload_time", "N/A")
        if upload_time != "N/A":
            # Formater la date si possible
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                upload_time = dt.strftime("%H:%M:%S")
            except:
                pass
        st.metric("Heure", upload_time)
    
    # Détails techniques (expandable)
    with st.expander("🔧 Détails techniques"):
        st.json(result)
    
    # Actions possibles
    st.markdown("---")
    st.subheader("🎯 Actions disponibles")
    
    col_actions1, col_actions2, col_actions3 = st.columns(3)
    
    with col_actions1:
        if st.button("📋 Extraire métadonnées", disabled=True):
            st.info("🚧 Fonctionnalité à venir avec l'IA")
    
    with col_actions2:
        if st.button("✂️ Diviser en articles", disabled=True):
            st.info("🚧 Fonctionnalité à venir avec l'IA")
    
    with col_actions3:
        if st.button("🔗 Créer collection", disabled=True):
            st.info("🚧 Fonctionnalité à venir")


def show_ai_processing_tab(api_base_url: str):
    """Tab pour le traitement IA (futur)"""
    st.subheader("🤖 Traitement IA des PDF")
    
    st.info("🚧 Cette section est en cours de développement")
    
    # Aperçu des fonctionnalités futures
    st.markdown("""
    ### 🎯 Fonctionnalités prévues
    
    #### 1. 📄 Division automatique des PDF
    - **Détection des articles** : Identification automatique des sections et articles dans les revues
    - **Séparation intelligente** : Division des PDF multi-articles en fichiers individuels
    - **Préservation de la qualité** : Maintien de la résolution et du formatage original
    
    #### 2. 🔍 Extraction de métadonnées
    - **Titres et auteurs** : Reconnaissance automatique des informations bibliographiques
    - **Dates et références** : Extraction des dates de publication et références croisées
    - **Mots-clés** : Identification des termes et concepts importants
    - **Géolocalisation** : Détection des lieux mentionnés (grottes, régions, etc.)
    
    #### 3. 🏷️ Classification automatique
    - **Type de document** : Article, rapport, thèse, etc.
    - **Domaine de spécialité** : Spéléologie, géologie, hydrogéologie, etc.
    - **Niveau de complexité** : Vulgarisation, technique, recherche
    
    #### 4. 🔗 Intégration Grottocenter
    - **Création automatique** : Génération de notices Grottocenter à partir des métadonnées
    - **Liaison hiérarchique** : Association automatique aux collections parentes
    - **Validation assistée** : Vérification et correction des données extraites
    """)
    
    # Mockup d'interface future
    st.markdown("---")
    st.subheader("🎨 Aperçu de l'interface future")
    
    if hasattr(st.session_state, 'last_uploaded_pdf') and st.session_state.last_uploaded_pdf:
        st.success("📄 PDF disponible pour traitement IA")
        
        # Simuler les options de traitement IA
        with st.form("ai_processing_form"):
            st.markdown("**Options de traitement IA:**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                divide_articles = st.checkbox("✂️ Diviser en articles", disabled=True)
                extract_metadata = st.checkbox("📋 Extraire métadonnées", disabled=True)
            
            with col2:
                classify_content = st.checkbox("🏷️ Classifier le contenu", disabled=True)
                create_notices = st.checkbox("🔗 Créer notices Grottocenter", disabled=True)
            
            st.markdown("**Paramètres avancés:**")
            confidence_threshold = st.slider(
                "Seuil de confiance",
                min_value=0.5,
                max_value=1.0,
                value=0.8,
                disabled=True
            )
            
            if st.form_submit_button("🚀 Lancer le traitement IA", disabled=True):
                st.info("🚧 Fonctionnalité en développement")
    else:
        st.info("📤 Uploadez d'abord un PDF dans l'onglet 'Upload PDF' pour activer le traitement IA")


def show_pdf_history_tab(api_base_url: str):
    """Tab pour l'historique des PDF"""
    st.subheader("📊 Historique des PDF traités")
    
    st.info("🚧 Cette section sera implémentée dans une version future")
    
    # Simulation de données d'historique
    st.markdown("""
    **Fonctionnalités prévues:**
    - 📋 Liste des PDF traités avec statuts
    - 🔍 Recherche et filtrage par date, nom, statut
    - 📊 Statistiques de traitement et performance
    - 📁 Gestion des fichiers (suppression, re-traitement)
    - 📈 Graphiques d'utilisation
    """)
    
    # Données mockées pour l'aperçu
    if st.checkbox("🎨 Aperçu des données futures"):
        import pandas as pd
        from datetime import datetime, timedelta
        import random
        
        # Générer des données fictives
        mock_data = []
        for i in range(10):
            mock_data.append({
                "Fichier": f"document_{i+1}.pdf",
                "Taille (MB)": round(random.uniform(1, 45), 2),
                "Date upload": (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M"),
                "Statut": random.choice(["✅ Validé", "🔄 En cours", "❌ Erreur", "⏳ En attente"]),
                "Articles détectés": random.randint(1, 15) if random.random() > 0.3 else 0,
                "Métadonnées extraites": "✅" if random.random() > 0.4 else "❌"
            })
        
        df = pd.DataFrame(mock_data)
        st.dataframe(df, use_container_width=True)
        
        # Statistiques mockées
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("PDF traités", len(mock_data))
        
        with col2:
            validated_count = len([d for d in mock_data if "✅" in d["Statut"]])
            st.metric("Validés", validated_count)
        
        with col3:
            total_size = sum(d["Taille (MB)"] for d in mock_data)
            st.metric("Volume total", f"{total_size:.1f} MB")
        
        with col4:
            total_articles = sum(d["Articles détectés"] for d in mock_data)
            st.metric("Articles détectés", total_articles)


def show_processing_status(status: str, progress: float = 0):
    """Afficher le statut de traitement en temps réel"""
    status_icons = {
        "upload": "📤",
        "validation": "🔍", 
        "processing": "⚙️",
        "extraction": "📋",
        "division": "✂️",
        "completion": "✅",
        "error": "❌"
    }
    
    icon = status_icons.get(status, "🔄")
    st.info(f"{icon} {status.title()}...")
    
    if progress > 0:
        st.progress(progress)