import asyncio
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
        self.sent = 0
        self.updated = 0

    async def send(self):
        self.sent += 1

    async def update(self):
        self.updated += 1


def test_repeated_quran_searches_are_distinct_top_level_steps():
    created: list[FakeStep] = []

    def factory(**kwargs):
        step = FakeStep(**kwargs)
        created.append(step)
        return step

    ticks = iter([1, 2, 3, 4])
    presenter = ToolStepPresenter(factory, lambda: next(ticks))

    async def scenario():
        await presenter.start("run-1", "search_quran", {"query": "signs"})
        await presenter.end("run-1")
        await presenter.start("run-2", "search_quran", {"query": "wisdom"})
        await presenter.end("run-2")

    asyncio.run(scenario())

    assert len(created) == 2
    assert created[0] is not created[1]
    assert all(step.kwargs["parent_id"] is None for step in created)
    assert all(step.sent == 1 and step.updated == 1 for step in created)
    assert [step.name for step in created] == ["Searched Quran", "Searched Quran"]
    assert [step.input["query"] for step in created] == ["signs", "wisdom"]
