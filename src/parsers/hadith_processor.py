import json
from pathlib import Path
from typing import List
from langchain_core.documents import Document
from src.parsers.base import BaseProcessor
from src.core.config import logger
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
        section_details: dict = book_metadata["section_details"] 
        book_name: str = book_metadata["name"]
    
        for section_idx in section_details.keys():
            section_detail: dict = section_details[section_idx]
            section_name: str = sections[section_idx] 

            for hadith_idx in range(section_detail["hadithnumber_first"], section_detail["hadithnumber_last"] + 1):
                
                hadith_data: dict = data["hadiths"][hadith_idx]
                text = hadith_data["text"]
                if not text.strip():
                    continue
                    
                metadata = {
                    "book_name": book_name,
                    "section_name": section_name,
                    "hadithnumber": hadith_data.get("hadithnumber", str(hadith_idx)) ,
                    "arabicnumber": hadith_data.get("arabicnumber", ""),
                    "reference": hadith_data.get("reference", {})
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
    from src.core.config import DEFAULT_MODEL_NAME
    text_splitter = SentenceTransformersTokenTextSplitter(model_name=DEFAULT_MODEL_NAME)

    processor = HadithProcessor(Path("src/data/hadith/editions/english/eng-bukhari.json"))
    docs = processor.process(text_splitter)
    print(docs[:10])