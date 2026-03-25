from typing import Any, Dict, List, Optional, Literal
from pathlib import Path
from core.config import logger, DEFAULT_MANIFEST, DATA_DIR, QURAN_INDEX_PATH, HADITH_INDEX_PATH, QURAN_ENG_DIR, HADITH_ENG_DIR
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
    Acts as the entry point for the RAG system, managing multiple vector stores.
    """
    def __init__(self):
        self.embedding_manager = EmbeddingManager()
        self.manifest_tracker = ManifestTracker()
        
        # Initialize separate stores
        self.stores = {
            "quran": VectorStoreManager(self.embedding_manager, index_path=str(QURAN_INDEX_PATH)),
            "hadith": VectorStoreManager(self.embedding_manager, index_path=str(HADITH_INDEX_PATH))
        }
        
    def process_data_source(self, processor: BaseProcessor, store: VectorStoreManager):
        """
        Takes a processor instance, extracts documents, embeds them, 
        and adds them to the specified FAISS vector store.
        """
        text_splitter = self.embedding_manager.get_text_splitter()
        docs = processor.to_chunks(text_splitter)
        
        if docs:
            logger.info(f"Adding {len(docs)} chunked documents from {processor.file_path.name} to {store.index_path}...")
            store.add_documents(docs)
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
            for store in self.stores.values():
                store.clear_index()
  
        logger.info(f"Scanning for documents in target data directories...")
        
        processed_count = 0
        skipped_count = 0
        
        # directories to sync data from
        dir_to_sync = [QURAN_ENG_DIR, HADITH_ENG_DIR]
        
        # Create directories if they don't exist
        for d in dir_to_sync:
            if not d.exists():
                logger.warning(f"Directory {d} does not exist.\nCreating directory {d}.\nPlease add the data files to the directory.")
                d.mkdir(parents=True, exist_ok=True)
                continue
            
        # Collect target files
        target_files = []
        if QURAN_ENG_DIR.exists():
            target_files.extend([(f, QuranProcessor, self.stores["quran"]) for f in QURAN_ENG_DIR.rglob("*.json") if f.is_file()])
            
        if HADITH_ENG_DIR.exists():
            target_files.extend([(f, HadithProcessor, self.stores["hadith"]) for f in HADITH_ENG_DIR.rglob("*.json") if f.is_file()])
        
        for file_path, ProcessorClass, target_store in target_files:
            # If the file hasn't been embedded or has changed
            if not self.manifest_tracker.is_processed(file_path):
                logger.info(f"Detected new file: {file_path.name}")
                processor: BaseProcessor = ProcessorClass(file_path)
                
                self.process_data_source(processor, target_store)
                self.manifest_tracker.mark_processed(file_path)
                processed_count += 1
            else:
                # Use debug level so it doesn't spam the console by default
                logger.debug(f"Skipping {file_path.name}, already embedded.")
                skipped_count += 1
                
        logger.info(f"Sync complete. Processed {processed_count} files, skipped {skipped_count} up-to-date files.")

    def ask(self, query: str, top_k: int = 5, filter_type: Literal["quran", "hadith"] | None = None):
        """
        Search and return results from the appropriate store.
        """
        if filter_type in self.stores:
            return self.stores[filter_type].search(query, top_k=top_k)
        
        # Fallback: if no filter, default to quran
        logger.warning(f"No specific store found for filter_type: {filter_type}. Defaulting to Quran.")
        return self.stores["quran"].search(query, top_k=top_k)

if '__main__' == __name__:
    # Visual test stub
    coordinator = RAGCoordinator()
    print("RAG Coordinator initialized with multi-store support.")
    coordinator.sync_documents()
    
    # Test query (will likely return empty if no index exists)
    # results = coordinator.ask("What does the Quran say about charity?")
    # print(f"Results: {results}")
