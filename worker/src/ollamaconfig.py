import os

class OllamaConfig:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    max_input_chars = int(os.getenv("OLLAMA_MAX_INPUT_CHARS")) if os.getenv("OLLAMA_MAX_INPUT_CHARS") else None
    ctx = int(os.getenv("OLLAMA_CTX", "8192"))
    num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "1024"))