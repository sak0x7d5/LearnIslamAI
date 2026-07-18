from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk


TEXT_BLOCK_TYPES = {"text", "output_text"}


def extract_text_content(content: Any) -> str:
    """Return user-visible text from string or structured model content."""
    if isinstance(content, str):
        return content

    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        return ""

    text_parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
            continue

        if not isinstance(block, Mapping):
            continue

        text = block.get("text")
        if block.get("type") in TEXT_BLOCK_TYPES and isinstance(text, str):
            text_parts.append(text)

    return "".join(text_parts)


def extract_final_ai_message_text(message: Any) -> str:
    """Extract text only from a completed assistant message, not a tool call."""
    if not isinstance(message, (AIMessage, AIMessageChunk)):
        return ""
    if getattr(message, "tool_calls", None):
        return ""

    text = extract_text_content(message.content)
    return text if text.strip() else ""


def extract_final_graph_answer(output: Any) -> str:
    """Extract the terminal assistant answer from a LangGraph state output."""
    if not isinstance(output, Mapping):
        return ""

    messages = output.get("messages")
    if (
        not isinstance(messages, Sequence)
        or isinstance(messages, (str, bytes, bytearray))
        or not messages
    ):
        return ""

    return extract_final_ai_message_text(messages[-1])


def extract_root_graph_answer(event: Any) -> str:
    """Extract an answer only from a root LangGraph v2 completion event."""
    output = extract_root_graph_output(event)
    return extract_final_graph_answer(output) if output is not None else ""


def extract_root_graph_output(event: Any) -> Mapping[str, Any] | None:
    """Return the completed root graph state, ignoring nested chain completions."""
    if not isinstance(event, Mapping):
        return None
    if event.get("event") != "on_chain_end" or event.get("parent_ids"):
        return None

    data = event.get("data")
    if not isinstance(data, Mapping):
        return None

    output = data.get("output")
    return output if isinstance(output, Mapping) else None
