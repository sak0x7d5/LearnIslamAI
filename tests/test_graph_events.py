from __future__ import annotations

import asyncio

import core.graph_events as graph_events
from core.graph_events import collect_graph_run
from core.tool_steps import ToolStepPresenter


class FakeStep:
    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.parent_id = kwargs["parent_id"]
        self.input = None
        self.output = ""
        self.start = None
        self.end = None
        self.sent = 0
        self.updated = 0

    async def send(self):
        self.sent += 1

    async def update(self):
        self.updated += 1


class FailingGraph:
    async def astream_events(self, _state, *, version):
        assert version == "v2"
        yield {
            "event": "on_tool_start",
            "name": "search_quran",
            "run_id": "tool-1",
            "data": {"input": {"query": "test"}},
        }
        raise RuntimeError("provider failure containing secret-key-value")


def test_graph_failure_is_sanitized_and_closes_active_steps(monkeypatch):
    steps = []
    logged = []

    def factory(**kwargs):
        step = FakeStep(**kwargs)
        steps.append(step)
        return step

    class FakeLogger:
        def error(self, message, *args):
            logged.append(message % args)

    monkeypatch.setattr(graph_events, "logger", FakeLogger())
    presenter = ToolStepPresenter(factory, lambda: "now")

    result = asyncio.run(collect_graph_run(FailingGraph(), {"messages": []}, presenter))

    assert result.failed is True
    assert result.output is None
    assert presenter.active == {}
    assert steps[0].parent_id is None
    assert steps[0].updated == 1
    assert "interrupted" in steps[0].output
    assert logged == ["Answer generation failed (RuntimeError)."]
    assert "secret-key-value" not in " ".join(logged)
