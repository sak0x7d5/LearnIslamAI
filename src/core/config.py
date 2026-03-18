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
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# -------------------------------------------------------------------
# Path Configuration
# -------------------------------------------------------------------
BASE_DIR = Path.cwd()
SRC_DIR = BASE_DIR / "src"
DATA_DIR = SRC_DIR / "data"

# -------------------------------------------------------------------
# Embedding Configuration
# -------------------------------------------------------------------
DEFAULT_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_KWARGS: Dict[str, Any] = {"device": "cpu"}
DEFAULT_ENCODE_KWARGS: Dict[str, Any] = {"normalize_embeddings": True}
DEFAULT_CACHE_DIR: Path = BASE_DIR / "embeddingModels"

# -------------------------------------------------------------------
# Manifest Configuration
# -------------------------------------------------------------------
DEFAULT_MANIFEST = DATA_DIR / "manifest.json"
