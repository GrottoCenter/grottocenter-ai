import os


class settings:
    greenpt_api_url = os.getenv("GREENPT_API_URL", "https://api.greenpt.ai/v1")
    api_key = os.getenv("GREENPT_API_KEY", "").strip()
    sso_salt_documents = os.getenv("SSO_SALT_DOCUMENTS", "").strip()
    mongo_uri = os.getenv("MONGO_URI", "").strip()
    mongo_password = os.getenv("MONGO_APP_PASSWORD", "").strip()
    mongo_username = os.getenv("MONGO_APP_USERNAME", "").strip()
    mongo_db_name = os.getenv("MONGO_DB_NAME", "").strip()