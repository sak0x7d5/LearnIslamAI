import json
from pathlib import Path
from typing import List
from langchain_core.documents import Document
from parsers.base import BaseProcessor
from core.config import logger
from langchain_text_splitters import SentenceTransformersTokenTextSplitter

class HadithProcessor(BaseProcessor):
    def process(self, text_splitter: SentenceTransformersTokenTextSplitter) -> List[Document]:
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

        book_metadata: dict = data["metadata"]
        sections: dict = book_metadata["sections"]
        name: str = book_metadata["name"]
    
        for hadith_data in data['hadiths']:
                
                text = hadith_data["text"]

                if not text.strip():
                    logger.warning(f'Blank hadith: {hadith_data}\n\nBook name: {name}')
                    continue

                reference = hadith_data['reference']
                metadata = {
                    "name": name,
                    "section": sections[str(reference['book'])],
                    "hadithnumber": hadith_data["hadithnumber"],
                    "arabicnumber": hadith_data.get("arabicnumber"),
                    "reference": reference,
                    "type": "hadith"
                }
                if hadith_data.get("grades"):
                    metadata["grades"] = hadith_data["grades"]

                docs.append(Document(page_content=text, metadata=metadata))

        if not docs:
            logger.warning(f"No valid hadith found to embed in {self.file_path.name}")
            return []

        logger.info(f"Chunking {len(docs)} hadiths for {self.file_path.name}...")
        chunked_docs = text_splitter.split_documents(docs)
            
        return chunked_docs

if __name__ == "__main__":
    from core.config import DEFAULT_MODEL_NAME
    text_splitter = SentenceTransformersTokenTextSplitter(model_name=DEFAULT_MODEL_NAME)

    processor = HadithProcessor(Path("data\\hadith\\editions\\english\\eng-bukhari.json"))
    docs = processor.process(text_splitter)
    print(docs[3604:3604+25])