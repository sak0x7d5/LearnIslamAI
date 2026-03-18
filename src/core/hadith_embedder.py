from core.embedding_manager import EmbeddingManager

class HadithEmbedder:
    def __init__(self):
        self.embedding_manager = EmbeddingManager()
        self.text_splitter = self.embedding_manager.get_text_splitter()
        self.embedding_model = self.embedding_manager.load_embedding_model()

    def embed_hadith(self, hadith: str) -> list[float]:
        """Embed a single hadith."""
        return self.embedding_manager.embed_query(hadith)