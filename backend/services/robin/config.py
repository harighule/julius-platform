import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve()
    while _env_file.parent != _env_file:
        _env_file = _env_file.parent
        if (_env_file / ".env").exists():
            load_dotenv(_env_file / ".env")
            break
except ImportError:
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLAMA_CPP_BASE_URL = os.getenv("LLAMA_CPP_BASE_URL")