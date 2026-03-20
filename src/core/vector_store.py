import numpy as np
from typing import Any, Dict, List, Protocol
from langchain_community.vectorstores import FAISS
from core.config import logger
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
                self.index_path, 
                embeddings,
                allow_dangerous_deserialization=True
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

    def add_documents(self, documents):
        """Adds LangChain documents to the vector store."""
        embeddings = self.embed_mgr.load_embedding_model()
        if self.vector_store is None:
            self.vector_store = FAISS.from_documents(documents, embeddings)
        else:
            self.vector_store.add_documents(documents)
        self.save_index()

    def search(self, query: str, top_k: int = 5, filter_dict: dict = None):
        """Performs similarity search with optional metadata filtering."""
        if not self.vector_store:
            self.load_index()
        if not self.vector_store:
            return []
            
        if filter_dict:
            return self.vector_store.similarity_search(query, k=top_k, filter=filter_dict)
            
        return self.vector_store.similarity_search(query, k=top_k)
