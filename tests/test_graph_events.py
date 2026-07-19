from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
        self.is_error = False
        self.sent = 0
        self.updated = 0

    async def send(self):
        self.sent += 1

    async def update(self):
        self.updated += 1


class SuccessfulGraph:
    async def astream_events(self, _state, *, version):
        assert version == "v2"
        yield {
            "event": "on_tool_start",
            "name": "search_quran",
            "run_id": "tool-1",
            "data": {"input": {"query": "signs"}},
        }
        yield {
            "event": "on_tool_start",
            "name": "search_hadith",
            "run_id": "tool-2",
            "data": {"input": {"query": "wisdom"}},
        }
        yield {
            "event": "on_tool_end",
            "name": "search_hadith",
            "run_id": "tool-2",
            "data": {"output": SimpleNamespace(artifact=[{"id": "H-1"}, {"id": "H-2"}])},
        }
        yield {
            "event": "on_tool_end",
            "name": "search_quran",
            "run_id": "tool-1",
            "data": {"output": {"artifact": [{"id": "Q-1"}]}},
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "run_id": "root",
            "parent_ids": [],
            "data": {"output": {"messages": ["authoritative final state"]}},
        }


class NoToolGraph:
    async def astream_events(self, _state, *, version):
        assert version == "v2"
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "run_id": "root",
            "parent_ids": [],
            "data": {"output": {"messages": ["answer without retrieval"]}},
        }


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


def _factory_for(steps):
    def factory(**kwargs):
        step = FakeStep(**kwargs)
        steps.append(step)
        return step

    return factory


def test_graph_collects_one_step_and_returns_artifacts_in_search_start_order():
    steps = []
    ticks = iter(["start", "end"])
    presenter = ToolStepPresenter(
        _factory_for(steps),
        lambda: next(ticks),
        parent_id="on-message-run",
    )

    result = asyncio.run(collect_graph_run(SuccessfulGraph(), {"messages": []}, presenter))

    assert result.failed is False
    assert result.output == {"messages": ["authoritative final state"]}
    assert [record["id"] for record in result.tool_artifacts] == ["Q-1", "H-1", "H-2"]
    assert len(steps) == 1
    assert steps[0].parent_id == "on-message-run"
    assert steps[0].end == "end"
    assert steps[0].name == "Islamic sources · Quran ×1 · Hadith ×1"
    assert "**Quran:** 1 search · 1 result" in steps[0].output
    assert "**Hadith:** 1 search · 2 results" in steps[0].output
    assert steps[0].output.index("1. **Quran**") < steps[0].output.index("2. **Hadith**")


def test_graph_without_tools_preserves_root_fallback_without_creating_a_step():
    steps = []
    presenter = ToolStepPresenter(_factory_for(steps), lambda: "now")

    result = asyncio.run(collect_graph_run(NoToolGraph(), {"messages": []}, presenter))

    assert result.output == {"messages": ["answer without retrieval"]}
    assert result.tool_artifacts == ()
    assert steps == []


def test_graph_failure_is_sanitized_and_closes_active_step(monkeypatch):
    steps = []
    logged = []

    class FakeLogger:
        def error(self, message, *args):
            logged.append(message % args)

    monkeypatch.setattr(graph_events, "logger", FakeLogger())
    ticks = iter(["start", "end"])
    presenter = ToolStepPresenter(_factory_for(steps), lambda: next(ticks))

    result = asyncio.run(collect_graph_run(FailingGraph(), {"messages": []}, presenter))

    assert result.failed is True
    assert result.output is None
    assert result.tool_artifacts == ()
    assert presenter.active == {}
    assert steps[0].parent_id is None
    assert steps[0].end == "end"
    assert steps[0].is_error is True
    assert steps[0].updated == 1
    assert "interrupted" in steps[0].output
    assert logged == ["Answer generation failed (RuntimeError)."]
    assert "secret-key-value" not in " ".join(logged)
