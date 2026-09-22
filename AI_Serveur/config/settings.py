import os


class settings:
    greenpt_api_url = os.getenv("GREENPT_API_URL", "https://api.greenpt.ai/v1")
    api_key = os.getenv("GREENPT_API_KEY", "").strip()
    auth_verify_url = os.getenv("AUTH_VERIFY_URL", "http://localhost:1337/api/v1/auth/check").strip()