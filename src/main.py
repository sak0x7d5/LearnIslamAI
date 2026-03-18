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
            if user_input.lower() in ['exit', 'quit']:
                break
            
            if not user_input.strip():
                continue

            # Query the RAG system
            response = coordinator.ask(user_input)
            print(f"\nResponse:\n{response}")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break

if __name__ == "__main__":
    # main()
    pass