"""CacheIQ configuration — reads from environment."""

import os
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://cacheiq:cacheiq@localhost:5432/cacheiq")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "changeme")
MOCK_LLM_LATENCY_MS: int = int(os.getenv("MOCK_LLM_LATENCY_MS", "1500"))
T_HIT: float = float(os.getenv("T_HIT", "0.85"))
T_LOW: float = float(os.getenv("T_LOW", "0.75"))
PRICE_IN: float = float(os.getenv("PRICE_IN", "0.00000015"))
PRICE_OUT: float = float(os.getenv("PRICE_OUT", "0.0000006"))
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
MOCK_API: bool = os.getenv("MOCK_API", "0") == "1"
