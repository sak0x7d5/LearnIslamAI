from parsers.base import BaseProcessor
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from core.config import logger, DEFAULT_MANIFEST, DATA_DIR
from core.embedding_manager import EmbeddingManager
from core.manifest_tracker import ManifestTracker
from core.vector_store import VectorStoreManager
from parsers.hadith_processor import HadithProcessor
from parsers.quran_processor import QuranProcessor
from parsers.base import BaseProcessor
# -------------------------------------------------------------------
# RAGCoordinator
# -------------------------------------------------------------------
class RAGCoordinator:
    """
    Coordinator class that ties together embedding, tracking, and storage.
    Acts as the entry point for the RAG system.
    """
    def __init__(self):
        self.embedding_manager = EmbeddingManager()
        self.manifest_tracker = ManifestTracker()
        self.vector_store = VectorStoreManager(self.embedding_manager)
        
    def process_data_source(self, processor: BaseProcessor):
        """
        Takes a processor instance, extracts documents, embeds them, 
        and adds them to the FAISS vector store.
        """
        text_splitter = self.embedding_manager.get_text_splitter()
        docs = processor.process(text_splitter)
        
        if docs:
            logger.info(f"Adding {len(docs)} chunked documents from {processor.file_path.name} to FAISS...")
            self.vector_store.add_documents(docs)
        else:
            logger.warning(f"No documents were produced by {processor.__class__.__name__} for {processor.file_path.name}")

    def sync_documents(self):
        """
        Scans the data directory, checks the manifest for each file, and processes new/changed ones.
        """
        if not DATA_DIR.exists():
            logger.info(f"Data directory {DATA_DIR} does not exist. Creating it.")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            return

        # 1. Detect if the embedding model changed
        if self.manifest_tracker.check_and_update_model():
            logger.warning("Triggering database wipe due to model change...")
            self.vector_store.clear_index()
 
        logger.info(f"Scanning for documents in target data directories...")
        
        processed_count = 0
        skipped_count = 0
        
        # Define paths explicitly
        quran_eng_dir = DATA_DIR / "quran" / "english"
        hadith_eng_dir = DATA_DIR / "hadith" / "editions" / "english"
        
        # Create directories if they don't exist
        for d in [quran_eng_dir, hadith_eng_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # Collect target files
        target_files = []
        if quran_eng_dir.exists():
            target_files.extend([(f, QuranProcessor) for f in quran_eng_dir.rglob("*.json") if f.is_file()])
            
        if hadith_eng_dir.exists():
            target_files.extend([(f, HadithProcessor) for f in hadith_eng_dir.rglob("*.json") if f.is_file()])
        
        for file_path, ProcessorClass in target_files:
            # If the file hasn't been embedded or has changed
            if not self.manifest_tracker.is_processed(file_path):
                logger.info(f"Detected new file: {file_path.name}")
                processor: BaseProcessor = ProcessorClass(file_path)
                
                self.process_data_source(processor)
                self.manifest_tracker.mark_processed(file_path)
                processed_count += 1
            else:
                # Use debug level so it doesn't spam the console by default
                logger.debug(f"Skipping {file_path.name}, already embedded.")
                skipped_count += 1
                
        logger.info(f"Sync complete. Processed {processed_count} files, skipped {skipped_count} up-to-date files.")

    def ask(self, query: str, top_k: int = 5, filter_type: Literal["quran", "hadith"] | None = None):
        """
        Search and return results. 
        Optional filter_type (e.g. 'quran', 'hadith', 'lecture') to search a specific dataset.
        """
        filter_dict = {"type": filter_type} if filter_type else None
        return self.vector_store.search(query, top_k=top_k, filter_dict=filter_dict)

if '__main__' == __name__:
    # Visual test stub
    coordinator = RAGCoordinator()
    print("RAG Coordinator initialized.")
    coordinator.sync_documents()
    
    # Test query (will likely return empty if no index exists)
    # results = coordinator.ask("What does the Quran say about charity?")
    # print(f"Results: {results}")
