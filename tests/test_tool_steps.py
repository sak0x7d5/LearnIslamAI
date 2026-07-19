import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.tool_steps import ToolStepPresenter  # noqa: E402


class FakeStep:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs["name"]
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


def test_repeated_and_overlapping_searches_share_one_ordered_turn_step():
    created: list[FakeStep] = []

    def factory(**kwargs):
        step = FakeStep(**kwargs)
        created.append(step)
        return step

    ticks = iter(["started", "finished"])
    presenter = ToolStepPresenter(
        factory,
        lambda: next(ticks),
        parent_id="on-message-run",
    )

    async def scenario():
        await presenter.start(
            "run-1",
            "search_quran",
            {"query": "signs <img src=x> [unsafe](https://example.test)"},
        )
        await presenter.start("run-2", "search_hadith", {"query": "wisdom"})
        # Complete in reverse order to model overlapping tool calls.
        await presenter.end("run-2", result_count=3)
        await presenter.end("run-1", result_count=5)
        await presenter.finish()

    asyncio.run(scenario())

    assert len(created) == 1
    step = created[0]
    assert step.kwargs == {
        "name": "Islamic sources",
        "type": "tool",
        "parent_id": "on-message-run",
        "default_open": False,
        "auto_collapse": True,
        "show_input": False,
    }
    assert step.input == ""
    assert step.start == "started"
    assert step.end == "finished"
    assert step.name == "Islamic sources · Quran ×1 · Hadith ×1"
    assert step.sent == 1
    assert step.updated == 4
    assert step.is_error is False
    assert presenter.active == {}
    assert "**Quran:** 1 search · 5 results" in step.output
    assert "**Hadith:** 1 search · 3 results" in step.output
    assert step.output.index("1. **Quran**") < step.output.index("2. **Hadith**")
    assert "<img" not in step.output
    assert r"&lt;img src=x\&gt;" not in step.output
    assert "&lt;img src=x&gt;" in step.output
    assert r"\[unsafe\]\(https://example\.test\)" in step.output


def test_no_tool_calls_create_no_empty_activity_step():
    created: list[FakeStep] = []
    presenter = ToolStepPresenter(
        lambda **kwargs: created.append(FakeStep(**kwargs)),
        lambda: "now",
        parent_id="on-message-run",
    )

    assert asyncio.run(presenter.finish()) is None
    assert created == []


def test_graph_failure_closes_the_step_without_exposing_error_text():
    created: list[FakeStep] = []

    def factory(**kwargs):
        step = FakeStep(**kwargs)
        created.append(step)
        return step

    ticks = iter(["started", "failed"])
    presenter = ToolStepPresenter(factory, lambda: next(ticks))

    async def scenario():
        await presenter.start("run-1", "search_quran", {"query": "test"})
        await presenter.fail_all("provider failure containing secret-key-value")

    asyncio.run(scenario())

    step = created[0]
    assert step.end == "failed"
    assert step.name == "Islamic sources · Quran ×1"
    assert step.is_error is True
    assert step.updated == 1
    assert "1 failed" in step.output
    assert "answer run was interrupted" in step.output
    assert "secret-key-value" not in step.output


def test_tool_status_translation_uses_natural_search_labels():
    translations = json.loads(
        (PROJECT_ROOT / ".chainlit" / "translations" / "en-US.json").read_text(encoding="utf-8")
    )

    status = translations["chat"]["messages"]["status"]
    assert status == {"using": "Searching", "used": "Searched"}
