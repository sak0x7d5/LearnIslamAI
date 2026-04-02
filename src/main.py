import os
import sys
from pathlib import Path

# 1. Setup paths
# Add the 'src' directory to the Python path so core modules can be imported
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.coordinator import RAGCoordinator
from core.database import initialize_database
from core.config import logger, DB_PATH
from core.data_manager import sync_hadith_data

def main():
    """
    Main entry point for the IslamAI application.
    Initializes the database and RAG system, then launches the Chainlit UI.
    """
    logger.info("========================================")
    logger.info("       IslamAI: Starting System         ")
    logger.info("========================================")

    # 1. Pre-flight checks: Database & Tables
    try:
        logger.info(f"Checking database at {DB_PATH}...")
        initialize_database(str(DB_PATH))
    except Exception as e:
        logger.error(f"Critical error during database initialization: {e}")
        sys.exit(1)

    # 2. Pre-flight checks: Data Sync & RAG
    try:
        logger.info("Ensuring local data is up-to-date...")
        sync_hadith_data()
        
        logger.info("Syncing knowledge base (Quran & Hadith)...")
        coordinator = RAGCoordinator()
        coordinator.sync_documents()
    except Exception as e:
        logger.error(f"Critical error during RAG synchronization: {e}")
        # We continue even if sync fails, as the UI might still be useful
    
    # 3. Launch the Chainlit UI
    try:
        from chainlit.cli import run_chainlit
    except ImportError:
        logger.error("Chainlit is not installed. Please install requirements.")
        sys.exit(1)

    try:
        app_path = str(SRC_DIR / "app.py")
        logger.info(f"Launching UI from {app_path}...")
        
        # This will programmatically call 'chainlit run src/app.py'
        # Note: run_chainlit is a blocking call.
        run_chainlit(app_path)
    except Exception as e:
        logger.error(f"Failed to launch UI: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()