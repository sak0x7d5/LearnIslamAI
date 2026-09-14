from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import colorlog
from platformdirs import user_data_path


handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s%(reset)s - "
        "%(blue)s%(name)s%(reset)s - %(levelname)s - %(message)s",
        datefmt="%I:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
)

logger = colorlog.getLogger("IslamAI")
logger.propagate = False
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# Immutable application files live in the repository. Mutable state must not.
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"
BUNDLED_DATA_DIR = SRC_DIR / "data"
DATA_DIR = BUNDLED_DATA_DIR  # Backwards-compatible name for bundled source data.


def default_app_home() -> Path:
    """Return the IslamAI directory directly below LocalAppData on Windows."""

    return Path(user_data_path(appname="IslamAI", appauthor=False, roaming=False))


def resolve_app_home(configured: str | os.PathLike[str] | None = None) -> Path:
    """Validate an explicit mutable-data root before any directory is created."""

    raw_value = configured if configured is not None else os.environ.get("ISLAMAI_HOME")
    if raw_value is None or not str(raw_value).strip():
        return default_app_home().resolve()
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        raise RuntimeError("ISLAMAI_HOME must be an absolute path")
    resolved = candidate.resolve()
    if resolved == Path(resolved.anchor):
        raise RuntimeError("ISLAMAI_HOME cannot be the root of a drive")
    return resolved


APP_HOME = resolve_app_home()
STATE_DIR = APP_HOME / "state"
MODELS_DIR = APP_HOME / "models"
DEFAULT_CACHE_DIR = MODELS_DIR / "embedding_models"
DEFAULT_INDEX_DIR = APP_HOME / "vector_indices"
CORPUS_VERSIONS_DIR = APP_HOME / "corpus" / "versions"
UPDATE_STAGING_DIR = APP_HOME / "corpus" / "staging"

QURAN_ENG_DIR = BUNDLED_DATA_DIR / "quran" / "english"
HADITH_ENG_DIR = BUNDLED_DATA_DIR / "hadith" / "english"
QURAN_SURAH_METADATA = BUNDLED_DATA_DIR / "quran" / "metadata" / "surah.json"
CORPUS_MANIFEST_PATH = BUNDLED_DATA_DIR / "corpus-manifest.json"

DB_PATH = APP_HOME / "chat_history.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
CHAINLIT_FILES_DIR = APP_HOME / "runtime_files"
DEFAULT_MANIFEST = STATE_DIR / "processing-manifest.json"
UPDATE_STATE_PATH = STATE_DIR / "update-state.json"

QURAN_INDEX_PATH = DEFAULT_INDEX_DIR / "quran"
HADITH_INDEX_PATH = DEFAULT_INDEX_DIR / "hadith"

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DEFAULT_MODEL_KWARGS: dict[str, Any] = {"device": "cpu"}
DEFAULT_ENCODE_KWARGS: dict[str, Any] = {"normalize_embeddings": True}
DEFAULT_MODEL_INSTRUCTION = "Represent this sentence for searching relevant passages: "
DEFAULT_EMBEDDING_DIMENSION = 384
DEFAULT_GOOGLE_MODEL = "gemini-3.1-flash-lite"
# OpenRouter's free lineup rotates. This default is a starting point, not a
# guarantee; the model must support tool calling or IslamAI cannot search.
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
LLM_PROVIDER_ID = os.environ.get("ISLAMAI_LLM_PROVIDER", "").strip().lower()
# Any OpenAI-compatible endpoint works here, including native OpenAI at
# https://api.openai.com/v1. HTTPS is enforced before a key is ever sent.
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
CORPUS_UPDATE_MANIFEST_URL = os.environ.get("ISLAMAI_CORPUS_MANIFEST_URL", "").strip()
