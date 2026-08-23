import streamlit as st
import requests
import time

def show_simple_pdf_upload(api_base_url: str):
    st.header("📤 Envoi de PDF (Nouvelle Page)")
    st.markdown("Cette page permet d'envoyer un PDF vers le serveur et d'attendre son traitement complet.")

    # Composant pour uploader le fichier
    uploaded_file = st.file_uploader("Choisissez un document PDF", type=["pdf"])

    if uploaded_file is not None:
        st.info(f"Fichier sélectionné : {uploaded_file.name} ({uploaded_file.size / 1024:.2f} KB)")
        
        if st.button("Envoyer le PDF au serveur"):
            try:
                with st.spinner("Envoi du fichier en cours..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                    endpoint_post = f"{api_base_url}/documents/"
                    
                    response_post = requests.post(endpoint_post, files=files)
                    
                if response_post.status_code == 200:
                    post_data = response_post.json()
                    st.success(f"✅ Fichier reçu par le serveur. Message: {post_data.get('message', '')}")
                    
                    task_id = post_data.get("task_id")
                    
                    if task_id:
                        with st.spinner("Traitement du document en cours (cela peut prendre quelques instants)..."):
                            endpoint_get = f"{api_base_url}/documents/{task_id}"
                            
                            max_retries = 60  # Timeout après ~2 minutes (60 * 2 sec)
                            for _ in range(max_retries):
                                response_get = requests.get(endpoint_get)
                                
                                if response_get.status_code == 200:
                                    result_data = response_get.json()
                                    
                                    content = result_data.get("content", {})
                                    status = content.get("status", result_data.get("status"))
                                    
                                    if status == "completed":
                                        st.success("🎉 Traitement terminé !")
                                        st.json(result_data)
                                        break
                                    elif status == "failed":
                                        st.error("❌ Le traitement a échoué côté serveur.")
                                        st.json(result_data)
                                        break
                                    else:
                                        time.sleep(2)
                                else:
                                    st.error(f"❌ Erreur lors de la vérification du statut ({response_get.status_code})")
                                    st.text(response_get.text)
                                    break
                            else:
                                st.warning("⚠️ Le délai d'attente de récupération a été dépassé. Le document est peut-être très volumineux ou toujours dans la file d'attente.")
                    else:
                        st.warning("⚠️ Aucun 'task_id' n'a été renvoyé par le serveur.")
                        st.json(post_data)
                else:
                    st.error(f"❌ Erreur du serveur lors de l'envoi ({response_post.status_code})")
                    st.text(response_post.text)
                        
            except Exception as e:
                st.error(f"❌ Une erreur réseau est survenue : {e}")
