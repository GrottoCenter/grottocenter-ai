#!/usr/bin/env python3
"""
Unified application runner for both backend and frontend
"""

import os
import subprocess
import signal
import sys
import time
from dotenv import load_dotenv

load_dotenv()

def start_services():
    """Start both backend and frontend services"""
    
    # Get configuration from environment
    api_host = os.getenv("API_HOST", "127.0.0.1")
    api_port = int(os.getenv("API_PORT", "8000"))
    streamlit_port = int(os.getenv("STREAMLIT_PORT", "8501"))
    
    print(f"🚀 Starting Grottocenter AI Application")
    print(f"   Backend API: http://{api_host}:{api_port}")
    print(f"   Frontend UI: http://localhost:{streamlit_port}")
    print("=" * 50)
    
    processes = []
    
    try:
        # Start backend
        print("🔧 Starting backend server...")
        backend_process = subprocess.Popen([
            sys.executable, "run_backend.py"
        ])
        processes.append(backend_process)
        
        # Wait a moment for backend to start
        time.sleep(3)
        
        # Start frontend
        print("🎨 Starting frontend server...")
        frontend_process = subprocess.Popen([
            sys.executable, "run_frontend.py"
        ])
        processes.append(frontend_process)
        
        print("✅ Both services started successfully!")
        print("   Press Ctrl+C to stop all services")
        
        # Wait for processes to complete or be interrupted
        for process in processes:
            process.wait()
            
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal...")
        
    finally:
        # Clean up processes
        print("🔄 Shutting down services...")
        for process in processes:
            if process.poll() is None:  # Process is still running
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        print("✅ All services stopped.")

if __name__ == "__main__":
    start_services()