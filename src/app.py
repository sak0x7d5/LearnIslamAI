import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from core.graph import graph, coordinator
import sys
from pathlib import Path

# Ensure src is in path for imports if needed
src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.append(src_path)


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Sahabi with doubled testimony & Quran compilation",
            message="Which Companion of the Prophet ﷺ had his testimony counted as equal to two witnesses, and how did this unique distinction later play a role during the compilation of the Qur'an?",
            icon="/public/quran_icon.svg",
        ),
    ]


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


@cl.on_message
async def main(message: cl.Message):
    """Handles incoming messages by streaming the LangGraph response."""
    messages = cl.user_session.get("messages")
    messages.append(HumanMessage(content=message.content))

    # Streaming response (for thinking / intermediate steps)
    response_msg = cl.Message(content="")
    await response_msg.send()

    tool_steps: dict[str, cl.Step] = {}

    final_answer = ""   # ← We will collect the full final answer here

    async for event in graph.astream_events(
        {"messages": messages},
        version="v2",
    ):
        kind = event["event"]
        name = event.get("name", "")

        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                if isinstance(chunk.content, str):
                    await response_msg.stream_token(chunk.content)
                    final_answer += chunk.content
                elif isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part["text"]
                            await response_msg.stream_token(text)
                            final_answer += text

        # Tool handling (same as before)
        elif kind == "on_tool_start":
            tool_input = event["data"].get("input", {})
            step = cl.Step(name=f" {name}", type="tool")
            await step.__aenter__()
            step.input = str(tool_input)
            tool_steps[event["run_id"]] = step

        elif kind == "on_tool_end":
            run_id = event["run_id"]
            if run_id in tool_steps:
                step = tool_steps.pop(run_id)
                output = event["data"].get("output", "")
                step.output = str(output)
                await step.__aexit__(None, None, None)

    # Finalize the streaming message
    await response_msg.update()

    # Update session history with the AI response
    messages.append(AIMessage(content=final_answer))
    cl.user_session.set("messages", messages)