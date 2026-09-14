from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import SecretStr

from core.citations import (
    CitationRecord,
    citation_from_document,
    deduplicate_citations,
    format_tool_content,
)
from core.coordinator import RAGCoordinator
from core.llm import Provider
from core.source_manager import SourceManager


SYSTEM_PROMPT = """You are IslamAI, a careful retrieval assistant for Quran and Hadith.
Answer only from records returned by the search tools. You are not a mufti and must not
present personal legal rulings as authoritative fatwas.

Search behavior:
- Reformulate questions into precise searches using distinctive wording and names.
- Use two or three independent searches when a complex question genuinely needs them.
- Prefer exact, relevant records over broad thematic matches.

Answer behavior:
- Synthesize the retrieved evidence in respectful, clear Markdown prose.
- Quote only the relevant portion of a verse or Hadith when a shorter excerpt is clearer.
- Wrap only direct retrieved excerpts in <quran ref="SOURCE_ID">...</quran> or
  <hadith ref="SOURCE_ID">...</hadith>. The ref is optional; omit it if unsure.
- Use the exact Reference value supplied by the search tool. Do not put source tags inside
  each other, and do not emit any other HTML.
- Attribute other source-dependent claims in ordinary Markdown when useful.
- Do not expose file paths or internal metadata.
- If the retrieved records do not support an answer, say so plainly.
"""


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_search_tools(
    coordinator: RAGCoordinator,
    source_manager: SourceManager | None = None,
) -> list[BaseTool]:
    sources = source_manager or SourceManager()

    def search(kind: str, query: str, top_k: int) -> tuple[str, list[CitationRecord]]:
        safe_top_k = max(1, min(int(top_k), 8))
        documents = coordinator.ask(query.strip(), top_k=safe_top_k, filter_type=kind)
        records = deduplicate_citations(
            [
                citation_from_document(document, kind=kind, source_manager=sources)
                for document in documents
            ]
        )
        return format_tool_content(records), records

    @tool(response_format="content_and_artifact")
    def search_quran(query: str, top_k: int = 5) -> tuple[str, list[CitationRecord]]:
        """Search the English Quran corpus for passages relevant to a precise query."""
        return search("quran", query, top_k)

    @tool(response_format="content_and_artifact")
    def search_hadith(query: str, top_k: int = 5) -> tuple[str, list[CitationRecord]]:
        """Search the ten bundled English Hadith collections for relevant narrations."""
        return search("hadith", query, top_k)

    return [search_quran, search_hadith]


def make_chatbot(llm_with_tools: Any) -> Callable[..., Any]:
    async def chatbot(state: GraphState, config: RunnableConfig) -> dict[str, list[AIMessage]]:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT), *messages]
        response = await llm_with_tools.ainvoke(messages, config=config)
        return {"messages": [response]}

    return chatbot


def make_tool_node(tools: list[BaseTool]) -> Callable[..., Any]:
    """Execute tool calls without importing LangGraph's optional prebuilt bundle."""
    tools_by_name = {candidate.name: candidate for candidate in tools}

    async def execute_tools(state: GraphState) -> dict[str, list[ToolMessage]]:
        latest = state["messages"][-1]
        outputs: list[ToolMessage] = []
        for call in getattr(latest, "tool_calls", []) or []:
            name = str(call.get("name", ""))
            call_id = str(call.get("id", ""))
            candidate = tools_by_name.get(name)
            if candidate is None:
                outputs.append(
                    ToolMessage(
                        content=f"Unknown search tool: {name}",
                        tool_call_id=call_id,
                        status="error",
                    )
                )
                continue
            try:
                result = await candidate.ainvoke(call)
                if isinstance(result, ToolMessage):
                    outputs.append(result)
                else:
                    outputs.append(ToolMessage(content=str(result), tool_call_id=call_id))
            except Exception as exc:
                outputs.append(
                    ToolMessage(
                        content=f"The {name} search failed: {type(exc).__name__}",
                        tool_call_id=call_id,
                        status="error",
                    )
                )
        return {"messages": outputs}

    return execute_tools


def _route_after_chatbot(state: GraphState) -> str:
    latest = state["messages"][-1]
    return "tools" if getattr(latest, "tool_calls", None) else "end"


def build_graph(
    *,
    api_key: SecretStr,
    coordinator: RAGCoordinator,
    provider: Provider,
    model_name: str,
):
    """Build a session graph only after a validated provider API key is available."""
    active_data_dir = coordinator.quran_dir.parents[1]
    tools = create_search_tools(
        coordinator,
        SourceManager(
            active_data_dir,
            surah_metadata_path=active_data_dir / "quran" / "metadata" / "surah.json",
            allowed_roots=(active_data_dir,),
        ),
    )
    llm = provider.build(model_name, api_key)
    chatbot = make_chatbot(llm.bind_tools(tools))

    builder = StateGraph(GraphState)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", make_tool_node(tools))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges(
        "chatbot",
        _route_after_chatbot,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "chatbot")
    return builder.compile()
