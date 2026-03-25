import os
from dotenv import load_dotenv
from core.config import logger
from rag_manager import RAGCoordinator

def main():
    # 1. Setup Environment
    load_dotenv()
    logger.info("Starting IslamAI application...")

    # 2. Initialize and Sync Knowledge Base
    # RAGCoordinator internally uses ManifestTracker to check what's already embedded
    coordinator = RAGCoordinator()
    
    logger.info("Syncing knowledge base with data folder...")
    # This will check the data/ directory, embed any new/modified files, and update manifest
    coordinator.sync_documents() 

    # 3. Start the Application Interface (e.g., interactive terminal for now)
    logger.info("System ready. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("\nAsk a question about Islam: ")
            filter = input("where to search? 'hadith' or 'quran': ")
            if filter not in ['hadith', 'quran']:
                print("Invalid filter. Please try again.")
                continue
            if user_input.lower() in ['exit', 'quit']:
                break
            
            if not user_input.strip():
                continue

            # Query the RAG system
            response = coordinator.ask(user_input, filter_type=filter)
            for i, doc in enumerate(response):
                print(f'{i+1}.\n{doc.page_content}\nMetadata: {doc.metadata}\n')
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break

if __name__ == "__main__":
    main()
    # pass