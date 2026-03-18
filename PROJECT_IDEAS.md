# IslamAI - Project Architecture & Ideas

## 1. High-Level Goals & Architecture
The main objective is to create a complete, offline-first RAG (Retrieval-Augmented Generation) system for answering questions about Islam using the Quran and Hadith.

### Data Layer (Ingestion & Chunking)
- **Scope**: Initial dataset will focus purely on English text for both Hadith and Quran, to match the embedding model's capabilities.
- **Source**: Hadith books from JSON files in the `hadith_data` folder and the Quran corpus from a single JSON file.
- **Tracking (Manifest)**: Track embedded books in a manifest file (e.g., `manifest.json` with a "files" dictionary). 
    - When adding new books or updating files, check the manifest to embed only unprocessed/modified ones.
    - Detect embedding model changes (via string comparison) to trigger a full corpus re-embed.
- **Chunking**: Chunk text into fixed-size segments (e.g., 512 tokens with 50-token overlap) using `RecursiveCharacterTextSplitter`. 
    - This ensures embeddings capture meaningful semantics since whole-Hadith embedding often fails for long texts.
- **Robustness**: Handle errors gracefully (e.g., skip malformed JSON, log warnings for empty texts).
- **Best Practice**: Keep a clear separation between Arabic/Urdu datasets and English datasets during the vectorization phase. English chunk metadata can be mapped back to Arabic datasets later using IDs.

### Retrieval Layer (Vector DB)
- **Database**: Use a vector database like FAISS (current) or Chroma to store embeddings alongside metadata (source, ID, chunk index).
- **Retrieval Strategy**: 
    - Match user query to the chunks.
    - Use metadata (e.g., "full_id") from the matched chunk to fetch and return the *full* original text from a stored dictionary or DB, providing complete context.
    - Deduplicate results (using a set of full IDs) to avoid feeding the LLM redundant full texts.
- **Features**: Support top-k retrieval with similarity thresholds and log distances for debugging.

### Generation Layer (LLM Integration)
- **Local Execution**: Integrate local LLMs (e.g., via `llama.cpp-python` for an OpenAI-compatible API) for offline generation.
- **Configurability**: Fallback to CPU if no GPU is present. Configurable models (e.g., Llama 3.1-Instruct GGUF).
- **RAG Execution**: Feed retrieved full texts as context to the LLM to generate accurate explanations and summaries.

### Orchestration & Routing (LangGraph)
- **Workflows**: Use LangGraph for stateful agents/chains (e.g., `Embed Query` -> `Retrieve` -> `Generate Response`).
- **Nodes**: Create nodes for ingestion checks, tool calls, and human-in-the-loop confirmations.
- **Persistence**: Store graph state to enable multi-turn conversations.

### UI Layer
- **Interface**: Start with Open WebUI (via Pipes for agent integration) for chat interactions.
- **Alternatives**: Custom Gradio or Streamlit interface for tailored features (search bar, result filters, toggle LLM).
- **UX**: Ensure an offline-first experience with user-friendly error messages (e.g., "No results—try different keywords").

---

## 2. Implementation Tasks & Refactoring

### `rag_manager.py` Cleanup
- [x] **Conflicting Manifest Logic**: Removed manifest tracking from `EmbeddingManager` and delegated it to `ManifestTracker`.
- [x] **Clean up imports**: Removed unused imports to make the script leaner.

### RAG Initialization Workflow
*Initialization must happen automatically to scan for new files.*
- [x] Create an initialization pipeline in `src/main.py`.
- [x] Initialize the `ManifestTracker` and `RAGCoordinator`.
- [ ] Iterate through `./data/quran` and `./data/hadith` (ignoring Arabic/Urdu for now).
- [ ] For each English file, check if it's processed using `ManifestTracker.is_processed()`.
- [ ] Implement text chunking (using `RecursiveCharacterTextSplitter`) and embedding creation.
- [ ] Call `ManifestTracker.mark_processed()` to update `manifest.json`.

### General Practices
- Use environment variables (`.env` with `python-dotenv`) for hardcoded constants.

---

## 3. Confirmed Architecture Decisions

1. **Vector Database**: **FAISS** is locked in as the primary vector store for simplicity.
2. **LLM Integration**: **Gemini** will be the primary LLM used during generation to handle rate limits and get off the ground quickly. The system will be built with high **modularity** so that local LLMs can be swapped in seamlessly later.
3. **Data Retrieval Strategy**: After identifying chunks using FAISS, we will use the chunk metadata (like its specific file name or ID) to re-read the raw file inside the `data/` folder and fetch the complete Hadith or Quranic text, feeding that full context to the LLM.
