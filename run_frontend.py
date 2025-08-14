#!/usr/bin/env python3
import os

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("STREAMLIT_PORT", "8501"))
    os.system(f"streamlit run backend/frontend/streamlit_app.py --server.port {port}")
