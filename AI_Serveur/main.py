"""
Application FastAPI principale
"""

from application import configure_logging, create_app
from config.settings import settings

configure_logging(settings.log_level)

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
