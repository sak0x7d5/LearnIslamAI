import numpy as np
from typing import Any, Dict, List, Protocol
from langchain_community.vectorstores import FAISS
from core.config import logger, DEFAULT_MODEL_INSTRUCTION
from core.embedding_manager import EmbeddingManager


class VectorIndexProtocol(Protocol):
    def add(self, vector: np.ndarray, metadata: Dict[str, Any]) -> None: ...
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Dict[str, Any]]: ...


class VectorStoreManager:
    """
    Manages the FAISS vector store, handling initialization,
    saving/loading from disk, and similarity search.
    """

    def __init__(self, embedding_manager: EmbeddingManager, index_path: str = "faiss_index"):
        self.embed_mgr = embedding_manager
        self.index_path = index_path
        self.vector_store: FAISS = None

    def load_index(self):
        """Loads the FAISS index from disk if it exists."""
        try:
            embeddings = self.embed_mgr.load_embedding_model()
            self.vector_store = FAISS.load_local(
                self.index_path, embeddings, allow_dangerous_deserialization=True
            )
            logger.info(f"Loaded FAISS index from {self.index_path}")
        except Exception as e:
            logger.warning(f"Could not load index: {e}. Starting fresh.")
            self.vector_store = None

    def save_index(self):
        """Saves current vector store to disk."""
        if self.vector_store:
            self.vector_store.save_local(self.index_path)
            logger.info(f"Saved FAISS index to {self.index_path}")

    def clear_index(self):
        """Deletes the vector store from memory and disk."""
        import shutil
        from pathlib import Path

        self.vector_store = None
        path = Path(self.index_path)
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
                logger.info(f"Cleared FAISS index directory at {self.index_path}")
            except Exception as e:
                logger.error(f"Failed to clear FAISS index: {e}")

    def add_documents(self, documents):
        """Adds LangChain documents to the vector store."""
        if self.vector_store is None:
            self.load_index()  # Ensure we load existing data first

        embeddings = self.embed_mgr.load_embedding_model()
        if self.vector_store is None:
            logger.info(f"Creating new FAISS index for {self.index_path}...")
            self.vector_store = FAISS.from_documents(documents, embeddings)
        else:
            logger.info(
                f"Appending {len(documents)} documents to FAISS index at {self.index_path}..."
            )
            self.vector_store.add_documents(documents)
        self.save_index()

    def search(self, query: str, top_k: int = 5, filter_dict: dict = None):
        """Performs similarity search with optional metadata filtering."""
        if not self.vector_store:
            self.load_index()
        if not self.vector_store:
            return []

        logger.info("Searching %s vector index.", self.index_path)
        instruction_query = DEFAULT_MODEL_INSTRUCTION + query.strip()
        return self.vector_store.similarity_search(
            instruction_query,
            k=top_k,
            filter=filter_dict,
        )
