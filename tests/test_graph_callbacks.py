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
    _route_after_chatbot,
    create_search_tools,
    make_chatbot,
    make_tool_node,
)


def test_chatbot_propagates_runnable_config():
    partial_answer = (
        "Khuzaimah ibn Thabit’s testimony counted as two witnesses. (Sahih al-Bukhari, Hadith 2807)"
    )
    ainvoke = AsyncMock(return_value=AIMessage(content=partial_answer))
    chatbot = make_chatbot(SimpleNamespace(ainvoke=ainvoke))
    config = {"callbacks": [], "configurable": {"thread_id": "test-thread"}}

    result = asyncio.run(
        chatbot({"messages": [HumanMessage(content="Who was Khuzaimah?")]}, config)
    )

    ainvoke.assert_awaited_once_with(ANY, config=config)
    invoked_messages = ainvoke.await_args.args[0]
    assert isinstance(invoked_messages[0], SystemMessage)
    assert result == {"messages": [AIMessage(content=partial_answer)]}


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

    assert "Reference: Q-2-255" in content
    assert "Source: Al-Baqarah — Quran 2:255" in content
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


def test_partial_hadith_answer_routes_directly_to_end():
    answer = AIMessage(
        content=(
            "The relevant portion says his witness equaled two men’s. "
            "(Sahih al-Bukhari, Hadith 2807)"
        )
    )

    assert _route_after_chatbot({"messages": [answer]}) == "end"


def test_tool_call_routes_back_to_search_tools():
    call = {
        "name": "search_hadith",
        "args": {"query": "Khuzaimah testimony"},
        "id": "call-1",
        "type": "tool_call",
    }

    assert _route_after_chatbot({"messages": [AIMessage(content="", tool_calls=[call])]}) == "tools"
