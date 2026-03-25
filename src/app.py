import chainlit as cl
from langchain_core.messages import HumanMessage
from core.graph import graph, coordinator
import sys
from pathlib import Path

# Ensure src is in path for imports if needed
src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.append(src_path)


@cl.on_chat_start
async def start():
    """Initializes the chat session and syncs the knowledge base."""
    cl.user_session.set("messages", [])

    if coordinator:
        async with cl.Step(name="System Initialization") as step:
            step.output = "Syncing Islamic knowledge base (Quran & Hadith)..."
            # Run sync in a thread to avoid blocking the event loop
            await cl.make_async(coordinator.sync_documents)()
            step.output = "Knowledge base is up to date and ready."

    await cl.Message(
        content="Assalam-o-Alaikum! I am IslamAI, your scholarly assistant. "
                "I can help you with questions about the Quran and Hadith. "
                "How can I assist you today?"
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """Handles incoming messages by streaming the LangGraph response token by token."""
    messages = cl.user_session.get("messages")
    messages.append(HumanMessage(content=message.content))

    # The streaming response message — tokens will be appended here
    response_msg = cl.Message(content="")
    await response_msg.send()

    # Track open tool steps so we can close them properly
    tool_steps: dict[str, cl.Step] = {}

    async for event in graph.astream_events(
        {"messages": messages},
        version="v2",
    ):
        kind = event["event"]
        name = event.get("name", "")

        # --- Token streaming from the LLM ---
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                # Only stream text content, not tool-call chunks
                if isinstance(chunk.content, str):
                    await response_msg.stream_token(chunk.content)
                elif isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            await response_msg.stream_token(part["text"])

        # --- Tool call starts ---
        elif kind == "on_tool_start":
            tool_input = event["data"].get("input", {})
            step = cl.Step(name=f"🔍 {name}", type="tool")
            await step.__aenter__()
            step.input = str(tool_input)
            tool_steps[event["run_id"]] = step

        # --- Tool call ends ---
        elif kind == "on_tool_end":
            run_id = event["run_id"]
            if run_id in tool_steps:
                step = tool_steps.pop(run_id)
                output = event["data"].get("output", "")
                step.output = str(output)
                await step.__aexit__(None, None, None)

    # Finalize the response message
    await response_msg.update()

    # Persist the full message history from the final graph state
    final_state = await graph.ainvoke({"messages": messages})
    cl.user_session.set("messages", final_state["messages"])
