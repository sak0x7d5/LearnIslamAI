import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.graph import (  # noqa: E402
    GROUNDING_FAILURE_MESSAGE,
    NO_RESULTS_MESSAGE,
    create_search_tools,
    make_chatbot,
    make_tool_node,
    make_validation_node,
)


def test_chatbot_propagates_runnable_config():
    ainvoke = AsyncMock(return_value=AIMessage(content="final answer"))
    chatbot = make_chatbot(SimpleNamespace(ainvoke=ainvoke))
    config = {"callbacks": [], "configurable": {"thread_id": "test-thread"}}

    result = asyncio.run(
        chatbot({"messages": [HumanMessage(content="Who was Khuzaimah?")]}, config)
    )

    ainvoke.assert_awaited_once_with(ANY, config=config)
    invoked_messages = ainvoke.await_args.args[0]
    assert isinstance(invoked_messages[0], SystemMessage)
    assert result == {"messages": [AIMessage(content="final answer")]}


def test_search_tool_returns_content_and_structured_artifact(tmp_path):
    source = tmp_path / "quran.json"
    source.write_text('{"2:255": {"t": "Allah—there is no deity except Him."}}', encoding="utf-8")
    document = Document(
        page_content="chunk",
        metadata={
            "type": "quran",
            "source_file": str(source),
            "json_key": "2:255",
            "surah_number": 2,
            "ayah_number": 255,
            "surah_name": "Al-Baqarah",
        },
    )
    coordinator = SimpleNamespace(ask=lambda *args, **kwargs: [document])

    from core.source_manager import SourceManager

    quran_tool, _ = create_search_tools(
        coordinator,
        SourceManager(tmp_path, allowed_roots=(tmp_path,)),
    )
    content, artifact = quran_tool.func("throne verse", 5)

    assert "Source ID: Q-2-255" in content
    assert artifact[0]["id"] == "Q-2-255"
    assert "source_file" not in artifact[0]


def test_tool_node_preserves_citation_artifact(tmp_path):
    source = tmp_path / "quran.json"
    source.write_text('{"2:255": {"t": "Verse text"}}', encoding="utf-8")
    document = Document(
        page_content="chunk",
        metadata={
            "type": "quran",
            "source_file": str(source),
            "json_key": "2:255",
            "surah_number": 2,
            "ayah_number": 255,
            "surah_name": "Al-Baqarah",
        },
    )
    coordinator = SimpleNamespace(ask=lambda *args, **kwargs: [document])
    from core.source_manager import SourceManager

    tools = create_search_tools(coordinator, SourceManager(tmp_path, allowed_roots=(tmp_path,)))
    call = {
        "name": "search_quran",
        "args": {"query": "throne verse", "top_k": 5},
        "id": "call-1",
        "type": "tool_call",
    }

    result = asyncio.run(
        make_tool_node(tools)({"messages": [AIMessage(content="", tool_calls=[call])]})
    )

    message = result["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.artifact[0]["id"] == "Q-2-255"


def test_validation_repairs_unknown_citation_once():
    record = {
        "id": "Q-2-255",
        "kind": "quran",
        "text": "x",
        "title": "Al-Baqarah",
        "locator": "Quran 2:255",
        "grading": None,
    }
    messages = [
        ToolMessage(content="source", artifact=[record], tool_call_id="call-1"),
        AIMessage(content="Draft [[cite:Q-9-9]]"),
    ]
    llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=AIMessage(content="Repaired [[cite:Q-2-255]]"))
    )
    node = make_validation_node(llm)

    result = asyncio.run(node({"messages": messages}, {}))

    assert result["messages"][0].content == "Repaired [[cite:Q-2-255]]"
    assert llm.ainvoke.await_count == 1


def test_validation_fails_closed_after_bad_repair():
    record = {
        "id": "Q-2-255",
        "kind": "quran",
        "text": "x",
        "title": "Al-Baqarah",
        "locator": "Quran 2:255",
        "grading": None,
    }
    messages = [
        ToolMessage(content="source", artifact=[record], tool_call_id="call-1"),
        AIMessage(content="Uncited draft"),
    ]
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="Still uncited")))

    result = asyncio.run(make_validation_node(llm)({"messages": messages}, {}))

    assert result["messages"][0].content == GROUNDING_FAILURE_MESSAGE
    assert llm.ainvoke.await_count == 1


def test_validation_rejects_answer_that_never_searched():
    llm = SimpleNamespace(ainvoke=AsyncMock())

    result = asyncio.run(
        make_validation_node(llm)({"messages": [AIMessage(content="Answer from memory")]}, {})
    )

    assert result["messages"][0].content == GROUNDING_FAILURE_MESSAGE
    llm.ainvoke.assert_not_awaited()


def test_validation_replaces_ungrounded_answer_after_empty_search():
    llm = SimpleNamespace(ainvoke=AsyncMock())
    messages = [
        ToolMessage(content="No matching records.", artifact=[], tool_call_id="call-1"),
        AIMessage(content="An answer invented from model memory."),
    ]

    result = asyncio.run(make_validation_node(llm)({"messages": messages}, {}))

    assert result["messages"][0].content == NO_RESULTS_MESSAGE
    llm.ainvoke.assert_not_awaited()


def test_validation_replaces_answer_after_failed_search():
    llm = SimpleNamespace(ainvoke=AsyncMock())
    messages = [
        ToolMessage(
            content="The search failed.",
            artifact=None,
            tool_call_id="call-1",
            status="error",
        ),
        AIMessage(content="A confident answer despite the failure."),
    ]

    result = asyncio.run(make_validation_node(llm)({"messages": messages}, {}))

    assert result["messages"][0].content == NO_RESULTS_MESSAGE
    llm.ainvoke.assert_not_awaited()
