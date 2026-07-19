import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.message_utils import (  # noqa: E402
    escape_model_markdown,
    extract_final_ai_message_text,
    extract_final_graph_answer,
    extract_root_graph_answer,
    extract_root_graph_output,
    extract_text_content,
    restore_conversation_messages,
)


def test_safe_markdown_allows_partial_quote_but_escapes_html():
    answer = '<img src=x onerror="alert(1)"> **Relevant excerpt:** “his witness equaled two men.”'

    rendered = escape_model_markdown(answer)

    assert "<img" not in rendered
    assert "&lt;img" in rendered
    assert "**Relevant excerpt:**" in rendered
    assert "his witness equaled two men" in rendered


def test_extract_text_content_handles_gemini_blocks():
    content = [
        {"type": "thinking", "text": "private reasoning"},
        {"type": "text", "text": "Khuzaimah ibn Thabit"},
        " was the Companion.",
        {"type": "tool_call", "text": "hidden tool data"},
    ]

    assert extract_text_content(content) == ("Khuzaimah ibn Thabit was the Companion.")


def test_final_ai_text_rejects_pending_tool_calls():
    message = AIMessage(
        content="I will search first.",
        tool_calls=[
            {
                "name": "search_hadith",
                "args": {"query": "Khuzaimah ibn Thabit"},
                "id": "tool-call-1",
                "type": "tool_call",
            }
        ],
    )

    assert extract_final_ai_message_text(message) == ""


def test_extract_final_graph_answer_from_structured_content():
    output = {
        "messages": [
            HumanMessage(content="Who was the Companion?"),
            AIMessage(
                content=[
                    {"type": "text", "text": "Khuzaimah ibn Thabit"},
                    {"type": "text", "text": " had the doubled testimony."},
                ]
            ),
        ]
    }

    assert extract_final_graph_answer(output) == ("Khuzaimah ibn Thabit had the doubled testimony.")


def test_root_graph_answer_ignores_nested_events():
    output = {"messages": [AIMessage(content="final answer")]}
    nested_event = {
        "event": "on_chain_end",
        "parent_ids": ["parent-run"],
        "data": {"output": output},
    }
    root_event = {
        "event": "on_chain_end",
        "parent_ids": [],
        "data": {"output": output},
    }

    assert extract_root_graph_answer(nested_event) == ""
    assert extract_root_graph_answer(root_event) == "final answer"
    assert extract_root_graph_output(nested_event) is None
    assert extract_root_graph_output(root_event) == output


def test_final_graph_answer_requires_terminal_ai_message():
    output = {
        "messages": [
            AIMessage(content="", tool_calls=[]),
            ToolMessage(content="retrieved text", tool_call_id="tool-call-1"),
        ]
    }

    assert extract_final_graph_answer(output) == ""


def test_restore_conversation_excludes_internal_setup_steps():
    steps = [
        {
            "type": "assistant_message",
            "output": "Preparing local indexes",
            "metadata": {"islamai_internal": True},
        },
        {"type": "user_message", "output": "What is the verse of light?"},
        {
            "type": "assistant_message",
            "output": "Key validated",
            "metadata": '{"islamai_internal": true}',
        },
        {"type": "assistant_message", "output": "A grounded answer."},
    ]

    restored = restore_conversation_messages(steps)

    assert [type(message) for message in restored] == [HumanMessage, AIMessage]
    assert [message.content for message in restored] == [
        "What is the verse of light?",
        "A grounded answer.",
    ]
