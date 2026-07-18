from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class StepProtocol(Protocol):
    name: str
    input: Any
    output: str
    start: Any
    end: Any

    async def send(self) -> Any: ...
    async def update(self) -> Any: ...


def tool_label(tool_name: str, *, completed: bool) -> str:
    noun = tool_name.removeprefix("search_").replace("_", " ").title()
    return f"{'Searched' if completed else 'Searching'} {noun}"


class ToolStepPresenter:
    """Render each tool call independently without Chainlit context nesting."""

    def __init__(
        self,
        step_factory: Callable[..., StepProtocol],
        clock: Callable[[], Any],
    ):
        self.step_factory = step_factory
        self.clock = clock
        self.active: dict[str, tuple[StepProtocol, str]] = {}

    async def start(self, run_id: str, tool_name: str, tool_input: Any) -> StepProtocol:
        step = self.step_factory(
            name=tool_label(tool_name, completed=False),
            type="tool",
            parent_id=None,
        )
        step.start = self.clock()
        step.input = tool_input
        await step.send()
        self.active[run_id] = (step, tool_name)
        return step

    async def end(self, run_id: str, output: str | None = None) -> StepProtocol | None:
        item = self.active.pop(run_id, None)
        if item is None:
            return None
        step, tool_name = item
        step.name = tool_label(tool_name, completed=True)
        source = tool_name.removeprefix("search_").replace("_", " ")
        step.output = output or f"Retrieved relevant data from the {source}."
        step.end = self.clock()
        await step.update()
        return step

    async def fail_all(self, output: str) -> None:
        """Close every visible tool step after an interrupted graph run."""

        for run_id in list(self.active):
            await self.end(run_id, output)
