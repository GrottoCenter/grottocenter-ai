import os


class settings:
    greenpt_api_url = os.getenv("GREENPT_API_URL", "https://api.greenpt.ai/v1")
    api_key = os.getenv("GREENPT_API_KEY", "").strip()