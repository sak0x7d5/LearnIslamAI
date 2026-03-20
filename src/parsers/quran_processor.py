import json
from pathlib import Path
from typing import List
from langchain_core.documents import Document
from parsers.base import BaseProcessor
from core.config import logger
from langchain_text_splitters import SentenceTransformersTokenTextSplitter

class QuranProcessor(BaseProcessor):
    def process(self, verse_splitter: SentenceTransformersTokenTextSplitter) -> List[Document]:
        """
        Process Quran JSON file.
        Returns chunked Document objects.
        """
        logger.info(f"Processing Quran dataset: {self.file_path.name}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data: dict = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {self.file_path}: {e}")
            return []

        docs = []

        verses_list: dict = data if isinstance(data, list) else data.get("quran", {}).get("en.sahih", {})
  
        for idx in verses_list.keys():
            verse_data = verses_list[idx]
            
            verse = verse_data.get("verse", "")  

            if not verse.strip():
                continue
                
            metadata = {
                "surah_number": verse_data["surah"],
                "ayah_number": verse_data.get("ayah", str(idx)),
                "surah_name": verse_data["name"],
                "type": "quran"
            }
            
            docs.append(Document(page_content=verse, metadata=metadata))

        if not docs:
            logger.warning(f"No valid verse found to embed in {self.file_path.name}")
            return []

        logger.info(f"Chunking {len(docs)} verses for {self.file_path.name}...")
        chunked_docs = verse_splitter.split_documents(docs)
        
        return chunked_docs

if __name__ == "__main__":
    from src.core.config import DEFAULT_MODEL_NAME
    text_splitter = SentenceTransformersTokenTextSplitter(model_name=DEFAULT_MODEL_NAME)

    processor = QuranProcessor(Path("src\\data\\quran\\english\\en-sahih.json"))
    docs = processor.process(text_splitter)
    print(docs[:5])
    print(f"Processed {len(docs)} documents.")