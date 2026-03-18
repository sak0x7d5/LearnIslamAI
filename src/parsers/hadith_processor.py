import json
from pathlib import Path
from typing import List
from langchain_core.documents import Document
from parsers.base import BaseProcessor
from core.config import logger

class HadithProcessor(BaseProcessor):
    def process(self, text_splitter) -> List[Document]:
        """
        Process Hadith JSON file.
        Returns chunked Document objects.
        """
        logger.info(f"Processing Hadith dataset: {self.file_path.name}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {self.file_path}: {e}")
            return []

        docs = []
        # -------------------------------------------------------------------
        # TODO: The exact JSON keys depend on your actual data format. 
        # Update this logic to correctly parse your particular JSON schema.
        # Below is just a skeletal assumption for demonstration.
        # -------------------------------------------------------------------
        
        # Example heuristic logic:
        # We assume the file contains a list of hadiths.
        items = data if isinstance(data, list) else data.get("hadiths", [])
        
        for idx, item in enumerate(items):
            # Extract the actual English translation text
            # E.g., text = item.get("english_text", "")
            text = item.get("text", "") 
            
            if not text.strip():
                continue
                
            metadata = {
                "source": self.file_path.name,
                "type": "hadith",
                "id": item.get("id", str(idx)),
                # "book": item.get("book", "unknown"),
                # "chapter": item.get("chapter", "unknown"),
            }
            
            # The full_id will let us look up the real raw JSON again later
            metadata["full_id"] = f"{metadata['source']}::{metadata['id']}"

            docs.append(Document(page_content=text, metadata=metadata))

        if not docs:
            logger.warning(f"No valid text found to embed in {self.file_path.name}")
            return []

        # Chunk the documents to ensure they fit within context window and embed properly
        logger.info(f"Chunking {len(docs)} documents for {self.file_path.name}...")
        chunked_docs = text_splitter.split_documents(docs)
        
        return chunked_docs
