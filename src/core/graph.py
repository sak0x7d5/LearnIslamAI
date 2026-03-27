import os
import sys
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

# Ensure the parent directory is in the path to import rag_manager
base_path = Path(__file__).resolve().parent.parent
if str(base_path) not in sys.path:
    sys.path.append(str(base_path))

try:
    from rag_manager import RAGCoordinator
except ImportError as e:
    print(f"Error importing RAGCoordinator: {e}")
    RAGCoordinator = None


load_dotenv()

# Initialize the RAG Coordinator to be used by tools
# Ideally, this should be passed around or initialized globally for the app,
# but for the graph logic directly, we instantiate it here.
if RAGCoordinator:
    coordinator = RAGCoordinator()
else:
    coordinator = None


# 1. Define State
class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# 2. Define Tools
@tool
def search_quran(query: str, top_k: int = 5) -> str:
    """Searches the Quran for verses relevant to the query."""
    if not coordinator:
        return "Error: RAG Coordinator not initialized."
    
    results = coordinator.ask(query, top_k=top_k, filter_type="quran")
    if not results:
        return "No results found in the Quran."
    
    formatted = []
    for doc in results:
        content = doc.page_content
        meta = doc.metadata
        formatted.append(f"Content: {content}\nMetadata: {meta}")
    
    return "\n---\n".join(formatted)

@tool
def search_hadith(query: str, top_k: int = 5) -> str:
    """Searches Hadith collections for narrations relevant to the query."""
    if not coordinator:
        return "Error: RAG Coordinator not initialized."
        
    results = coordinator.ask(query, top_k=top_k, filter_type="hadith")
    if not results:
        return "No results found in Hadith collections."
    
    formatted = []
    for doc in results:
        content = doc.page_content
        meta = doc.metadata
        formatted.append(f"Content: {content}\nMetadata: {meta}")
    
    return "\n---\n".join(formatted)

tools = [search_quran, search_hadith]


# 3. Define the LLM
# Initialize Gemini model. Make sure GOOGLE_API_KEY is present in the environment (.env)
llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", temperature=0)
llm_with_tools = llm.bind_tools(tools)


# 4. Define Nodes
def chatbot(state: GraphState):
    messages = state["messages"]
    
    # Prepend a system message if one doesn't exist
    if not messages or not isinstance(messages[0], SystemMessage):
        sys_msg = SystemMessage(
            content="""You are a precise, knowledgeable, and respectful Islamic scholar AI. 
Your only goal is to answer questions about the Quran and Hadith using the tools provided. 
You must stay strictly grounded in the retrieved sources.

When using search tools:
- Reformulate the user's question into precise, scholar-level search queries.
- Use authentic Islamic terminology (e.g., "sadaqa", "reward for lawful act", "sexual intercourse with wife", "fulfilling desire lawfully", "Abu Dharr", "Sahih Muslim").
- Prefer specific Hadith phrasing over general words like "sex", "intimacy", "worship", or "charity".
- Break complex questions into 2–3 targeted searches if needed.
- Do NOT copy the user's words verbatim.
- Always prioritize exact or near-exact matches from Sahih Bukhari, Sahih Muslim, and other major collections.

After retrieving results:
- Critically evaluate which ones are relevant.
- Synthesize a clear, respectful answer.

IMPORTANT — HTML Formatting Rules:
When quoting from the Quran, wrap the citation in exactly this HTML:
<div class="quran">Surah Name (X:Y): "quoted text here."</div>

When quoting from a Hadith, wrap it in exactly this HTML:
<div class="hadith">Narrator – Collection (Book X, Hadith Y): "quoted text here."</div>

Only wrap direct citations. Do NOT wrap your own commentary in these tags.
Use these tags every time you cite a verse or hadith — do not skip them.

Be concise, accurate, and pious in tone. Never speculate or add information not present in the retrieved sources."""
        )
        messages = [sys_msg] + messages
        
    # Invoke LLM
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# 5. Build Graph
graph_builder = StateGraph(GraphState)
graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

graph = graph_builder.compile()


if __name__ == "__main__":
    print("Graph compiled successfully. Setting up RAG (this might take a few seconds)...")
    if coordinator:
        coordinator.sync_documents()
    
    print("\nExecuting test query: 'What does the Quran and Hadith say about patience?'")
    msg = HumanMessage(content="What does the Quran and Hadith say about patience in hard times?")
    
    for event in graph.stream({"messages": [msg]}):
        for key, value in event.items():
            if "messages" in value:
                # The latest message is appended to the list
                latest_message = value["messages"][-1]
                if hasattr(latest_message, "content") and latest_message.content:
                    print(f"\n[{key}] Assistant:\n{latest_message.content}")
                elif hasattr(latest_message, "tool_calls") and latest_message.tool_calls:
                    print(f"\n[{key}] Calling tools: {latest_message.tool_calls}")
