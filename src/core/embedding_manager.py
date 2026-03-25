from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import SentenceTransformersTokenTextSplitter
from pathlib import Path
from typing import Any, Dict, Optional
from core.config import (
    logger, 
    DEFAULT_MODEL_NAME, 
    DEFAULT_MODEL_KWARGS, 
    DEFAULT_ENCODE_KWARGS, 
    DEFAULT_CACHE_DIR
)

class EmbeddingManager:
    """
    Responsible for loading tokenizer & embedding model and providing token-aware helpers.
    Does NOT contain retrieval or storage logic. It isolates HuggingFace initialization.
    """
    def __init__(
        self,
        model_name: str | None = None,
        model_kwargs: Optional[Dict[str, Any]] = None,
        encode_kwargs: Optional[Dict[str, Any]] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.model_name = model_name or DEFAULT_MODEL_NAME
        self.model_kwargs = model_kwargs or DEFAULT_MODEL_KWARGS.copy()
        self.encode_kwargs = encode_kwargs or DEFAULT_ENCODE_KWARGS.copy()
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)

        self._text_splitter = None
        self._embeddings: HuggingFaceEmbeddings | None = None

        # ensure cache directory exists to store downloaded models
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_text_splitter(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> SentenceTransformersTokenTextSplitter:
        """
        Returns a SentenceTransformersTokenTextSplitter corresponding to the selected model. 
        """
        if self._text_splitter is None:
            logger.info("Loading text splitter")
            
            kwargs = {"model_name": self.model_name}
            if chunk_size is not None:
                kwargs["chunk_size"] = chunk_size
            if chunk_overlap is not None:
                kwargs["chunk_overlap"] = chunk_overlap
                
            self._text_splitter = SentenceTransformersTokenTextSplitter(**kwargs)
        return self._text_splitter

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
                cache_folder=str(self.cache_dir), # cache_dir mapping,
            )
        return self._embeddings

    def embed_query(self, text: str) -> list[float]:
        """
        Helper function to embed a single query text (e.g. user question).
        """
        emb = self.load_embedding_model()
        return emb.embed_query(text)
