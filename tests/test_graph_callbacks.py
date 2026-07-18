import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, ANY

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.mark.asyncio
async def test_chatbot_propagates_runnable_config(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    import core.graph as graph_module

    ainvoke = AsyncMock(return_value=AIMessage(content="final answer"))
    monkeypatch.setattr(
        graph_module,
        "llm_with_tools",
        SimpleNamespace(ainvoke=ainvoke),
    )
    config = {"callbacks": [], "configurable": {"thread_id": "test-thread"}}

    result = await graph_module.chatbot(
        {"messages": [HumanMessage(content="Who was Khuzaimah?")]},
        config,
    )

    ainvoke.assert_awaited_once_with(ANY, config=config)
    invoked_messages = ainvoke.await_args.args[0]
    assert isinstance(invoked_messages[0], SystemMessage)
    assert result == {"messages": [AIMessage(content="final answer")]}
