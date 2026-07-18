from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import SentenceTransformersTokenTextSplitter
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional
from core.config import (
    logger,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_KWARGS,
    DEFAULT_ENCODE_KWARGS,
    DEFAULT_CACHE_DIR,
    DEFAULT_MODEL_INSTRUCTION,
)


class EmbeddingManager:
    """
    Responsible for loading tokenizer & embedding model and providing token-aware helpers.
    Does NOT contain retrieval or storage logic. It isolates HuggingFace initialization.
    """

    def __init__(
        self,
        model_name: str | None = None,
        model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        embedding_dimension: int = 384,
        splitter_chunk_size: int = 384,
        splitter_chunk_overlap: int = 32,
        model_kwargs: Optional[Dict[str, Any]] = None,
        encode_kwargs: Optional[Dict[str, Any]] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.model_kwargs = model_kwargs or DEFAULT_MODEL_KWARGS.copy()
        self.model_revision = model_revision
        self.model_kwargs.setdefault("revision", self.model_revision)
        self.encode_kwargs = encode_kwargs or DEFAULT_ENCODE_KWARGS.copy()
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.embedding_dimension = embedding_dimension
        self.splitter_chunk_size = splitter_chunk_size
        self.splitter_chunk_overlap = splitter_chunk_overlap

        self._text_splitter = None
        self._embeddings: HuggingFaceEmbeddings | None = None

        # ensure cache directory exists to store downloaded models
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_text_splitter(
        self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None
    ) -> SentenceTransformersTokenTextSplitter:
        """
        Returns a SentenceTransformersTokenTextSplitter corresponding to the selected model.
        """
        if self._text_splitter is None:
            logger.info("Loading text splitter")

            effective_chunk_size = (
                chunk_size if chunk_size is not None else self.splitter_chunk_size
            )
            effective_overlap = (
                chunk_overlap if chunk_overlap is not None else self.splitter_chunk_overlap
            )
            splitter_model_kwargs = self.model_kwargs.copy()
            splitter_model_kwargs["revision"] = self.model_revision
            splitter_model_kwargs["cache_folder"] = str(self.cache_dir)
            kwargs = {
                "model_name": self.model_name,
                "tokens_per_chunk": effective_chunk_size,
                "chunk_overlap": effective_overlap,
                "model_kwargs": splitter_model_kwargs,
            }

            self._text_splitter = SentenceTransformersTokenTextSplitter(**kwargs)
        return self._text_splitter

    def get_index_fingerprint(self) -> Dict[str, Any]:
        """Return every setting that can make a persisted index incompatible."""

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "model_id": self.model_name,
            "model_revision": self.model_revision,
            "dimension": self.embedding_dimension,
            "normalize_embeddings": bool(self.encode_kwargs.get("normalize_embeddings", False)),
            "query_instruction": DEFAULT_MODEL_INSTRUCTION,
            "splitter": {
                "class": "SentenceTransformersTokenTextSplitter",
                "tokens_per_chunk": self.splitter_chunk_size,
                "chunk_overlap": self.splitter_chunk_overlap,
            },
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["digest"] = hashlib.sha256(canonical).hexdigest()
        return payload

    def load_embedding_model(self):
        """
        Loads the HuggingFace bge-small (or specified) representation model.
        It runs locally (CPU or GPU based on `self.model_kwargs`).
        """
        if self._embeddings is None:
            logger.info("Loading embedding model: %s", self.model_name)

            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs=self.model_kwargs,
                encode_kwargs=self.encode_kwargs,
                cache_folder=str(self.cache_dir),  # cache_dir mapping,
            )
        return self._embeddings

    def embed_query(self, text: str) -> list[float]:
        """
        Helper function to embed a single query text (e.g. user question).
        """
        emb = self.load_embedding_model()
        return emb.embed_query(text)
