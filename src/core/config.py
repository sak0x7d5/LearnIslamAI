from pathlib import Path
import os
import logging
import colorlog
from typing import Dict, Any

# -------------------------------------------------------------------
# Logging Configuration
# -------------------------------------------------------------------
handler = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s%(reset)s - "
    "%(blue)s%(name)s%(reset)s - "
    "%(levelname)s - "
    "%(message)s",
    datefmt="%I:%M:%S",
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }
)

handler.setFormatter(formatter)
logger = colorlog.getLogger("IslamAI")
logger.propagate = False
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# -------------------------------------------------------------------
# Path Configuration
# -------------------------------------------------------------------
# Project Root is two levels up from src/core/config.py
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"

# Data directory for raw sources and the chat database
DATA_DIR = SRC_DIR / "data"
QURAN_ENG_DIR = DATA_DIR / "quran" / "english"
HADITH_ENG_DIR = DATA_DIR / "hadith" / "english"
QURAN_METADATA_SURAH_NAME = DATA_DIR / "quran" / "quran-metadata-surah-name.json"

# Database & Manifest
DB_PATH = DATA_DIR / "chat_history.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
DEFAULT_MANIFEST = DATA_DIR / "manifest.json"

# -------------------------------------------------------------------
# Models / Index Configuration
# -------------------------------------------------------------------
MODELS_DIR = ROOT_DIR / "models"
DEFAULT_CACHE_DIR: Path = MODELS_DIR / "embedding_models"
DEFAULT_INDEX_DIR = MODELS_DIR / "vector_indices"

# Specific indices
QURAN_INDEX_PATH = DEFAULT_INDEX_DIR / "quran"
HADITH_INDEX_PATH = DEFAULT_INDEX_DIR / "hadith"

# -------------------------------------------------------------------
# Embedding Configuration
# -------------------------------------------------------------------
DEFAULT_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_KWARGS: Dict[str, Any] = {"device": "cpu"}
DEFAULT_ENCODE_KWARGS: Dict[str, Any] = {"normalize_embeddings": True}
DEFAULT_MODEL_INSTRUCTION: str = "Represent this sentence for searching relevant passages: "
