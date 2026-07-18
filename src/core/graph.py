from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import SecretStr

from core.citations import (
    CitationRecord,
    citation_from_document,
    collect_citations,
    deduplicate_citations,
    format_tool_content,
    validate_citations,
)
from core.config import DEFAULT_LLM_MODEL
from core.coordinator import RAGCoordinator
from core.message_utils import extract_final_ai_message_text
from core.source_manager import SourceManager


GROUNDING_FAILURE_MESSAGE = (
    "I’m sorry, but I couldn’t produce an answer whose citations could be verified "
    "against the retrieved Quran and Hadith records. Please try rephrasing the question."
)
NO_RESULTS_MESSAGE = (
    "I couldn’t find a Quran or Hadith record that verifies an answer to that question. "
    "Please try a more specific wording."
)

SYSTEM_PROMPT = """You are IslamAI, a careful retrieval assistant for Quran and Hadith.
Answer only from records returned by the search tools. You are not a mufti and must not
present personal legal rulings as authoritative fatwas.

Search behavior:
- Reformulate questions into precise searches using distinctive wording and names.
- Use two or three independent searches when a complex question genuinely needs them.
- Prefer exact, relevant records over broad thematic matches.

Answer behavior:
- Synthesize the retrieved evidence in respectful, clear Markdown.
- Cite every source-dependent statement with the exact marker [[cite:SOURCE_ID]].
- SOURCE_ID must be copied from a tool result. Never invent or alter an ID.
- Do not emit HTML. Do not expose file paths or internal metadata.
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


def make_validation_node(llm: Any) -> Callable[..., Any]:
    async def validate_answer(
        state: GraphState,
        config: RunnableConfig,
    ) -> dict[str, list[AIMessage]]:
        messages = state["messages"]
        answer = extract_final_ai_message_text(messages[-1]) if messages else ""
        records = collect_citations(messages)
        searched = any(isinstance(message, ToolMessage) for message in messages)
        if searched and not records:
            # Empty and failed searches carry no evidence. Replace any model-authored
            # prose with a fixed response so an ungrounded answer cannot pass through.
            return {"messages": [AIMessage(content=NO_RESULTS_MESSAGE)]}
        if not searched:
            return {"messages": [AIMessage(content=GROUNDING_FAILURE_MESSAGE)]}
        validation = validate_citations(answer, records)
        if answer and validation.valid:
            return {}

        if answer and records:
            allowed = "\n".join(
                f"- {record['id']}: {record['title']}, {record['locator']}" for record in records
            )
            repair_prompt = (
                "Rewrite the draft so every source-dependent claim uses only the allowed "
                "citation markers. Preserve the meaning, emit Markdown rather than HTML, "
                "and do not add facts.\n\n"
                f"Allowed citations:\n{allowed}\n\nDraft:\n{answer}"
            )
            repaired_message = await llm.ainvoke(
                [
                    SystemMessage(content="You repair citations; you do not answer from memory."),
                    HumanMessage(content=repair_prompt),
                ],
                config=config,
            )
            repaired = extract_final_ai_message_text(repaired_message)
            if repaired and validate_citations(repaired, records).valid:
                return {"messages": [AIMessage(content=repaired)]}

        return {"messages": [AIMessage(content=GROUNDING_FAILURE_MESSAGE)]}

    return validate_answer


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
    return "tools" if getattr(latest, "tool_calls", None) else "validate"


def build_graph(
    *,
    api_key: SecretStr,
    coordinator: RAGCoordinator,
    model_name: str = DEFAULT_LLM_MODEL,
):
    """Build a session graph only after a validated Google API key is available."""
    active_data_dir = coordinator.quran_dir.parents[1]
    tools = create_search_tools(
        coordinator,
        SourceManager(
            active_data_dir,
            surah_metadata_path=active_data_dir / "quran" / "metadata" / "surah.json",
            allowed_roots=(active_data_dir,),
        ),
    )
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        google_api_key=api_key,
    )
    chatbot = make_chatbot(llm.bind_tools(tools))
    validate_answer = make_validation_node(llm)

    builder = StateGraph(GraphState)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", make_tool_node(tools))
    builder.add_node("validate", validate_answer)
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges(
        "chatbot",
        _route_after_chatbot,
        {"tools": "tools", "validate": "validate"},
    )
    builder.add_edge("tools", "chatbot")
    builder.add_edge("validate", END)
    return builder.compile()
