from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class StepProtocol(Protocol):
    name: str
    input: Any
    output: str
    start: Any
    end: Any
    is_error: bool

    async def send(self) -> Any: ...
    async def update(self) -> Any: ...


SearchStatus = Literal["running", "completed", "failed"]


@dataclass
class SearchActivity:
    run_id: str
    source: str
    query: str
    status: SearchStatus = "running"
    result_count: int | None = None


_SOURCE_LABELS = {
    "search_quran": "Quran",
    "search_hadith": "Hadith",
}
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_[\]{}()#+.!|>~-])")
_MAX_QUERY_LENGTH = 240


def _source_label(tool_name: str) -> str:
    return _SOURCE_LABELS.get(tool_name, "Sources")


def _query_text(tool_input: Any) -> str:
    query = tool_input.get("query") if isinstance(tool_input, dict) else None
    if not isinstance(query, str) or not query.strip():
        return "query unavailable"
    normalized = " ".join(query.split())
    if len(normalized) > _MAX_QUERY_LENGTH:
        normalized = f"{normalized[: _MAX_QUERY_LENGTH - 1].rstrip()}…"
    escaped_html = html.escape(normalized, quote=False)
    return _MARKDOWN_SPECIAL.sub(r"\\\1", escaped_html)


def _quantity(value: int, singular: str, plural: str | None = None) -> str:
    noun = singular if value == 1 else (plural or f"{singular}s")
    return f"{value} {noun}"


class ToolStepPresenter:
    """Aggregate a turn's searches into one safe, compact Chainlit step."""

    def __init__(
        self,
        step_factory: Callable[..., StepProtocol],
        clock: Callable[[], Any],
        *,
        parent_id: str | None = None,
    ):
        self.step_factory = step_factory
        self.clock = clock
        self.parent_id = parent_id
        self.active: dict[str, SearchActivity] = {}
        self.activities: list[SearchActivity] = []
        self.step: StepProtocol | None = None
        self._closed = False
        self._run_failed = False
        self._lock = asyncio.Lock()

    def _render(self) -> str:
        grouped: dict[str, list[SearchActivity]] = {}
        for activity in self.activities:
            grouped.setdefault(activity.source, []).append(activity)

        summary: list[str] = []
        for source, activities in grouped.items():
            result_total = sum(
                activity.result_count or 0
                for activity in activities
                if activity.status == "completed"
            )
            failed = sum(activity.status == "failed" for activity in activities)
            running = sum(activity.status == "running" for activity in activities)
            details = [
                _quantity(len(activities), "search", "searches"),
                _quantity(result_total, "result"),
            ]
            if failed:
                details.append(f"{failed} failed")
            if running:
                details.append(f"{running} searching")
            summary.append(f"**{source}:** {' · '.join(details)}")

        queries: list[str] = []
        for index, activity in enumerate(self.activities, start=1):
            if activity.status == "running":
                status = "Searching…"
            elif activity.status == "failed":
                status = "Failed"
            elif activity.result_count is None:
                status = "Completed"
            else:
                status = _quantity(activity.result_count, "result")
            queries.append(f"{index}. **{activity.source}** — “{activity.query}” — {status}")

        sections = ["  \n".join(summary), "\n".join(queries)]
        if self._run_failed:
            sections.append("_The answer run was interrupted before it could finish safely._")
        return "\n\n".join(section for section in sections if section)

    def _completed_label(self) -> str:
        counts: dict[str, int] = {}
        for activity in self.activities:
            counts[activity.source] = counts.get(activity.source, 0) + 1
        suffix = " · ".join(f"{source} ×{count}" for source, count in counts.items())
        return f"Islamic sources · {suffix}" if suffix else "Islamic sources"

    def _create_step(self) -> StepProtocol:
        step = self.step_factory(
            name="Islamic sources",
            type="tool",
            parent_id=self.parent_id,
            default_open=False,
            auto_collapse=True,
            show_input=False,
        )
        step.start = self.clock()
        step.input = ""
        self.step = step
        return step

    async def start(self, run_id: str, tool_name: str, tool_input: Any) -> StepProtocol:
        async with self._lock:
            existing = next(
                (activity for activity in self.activities if activity.run_id == run_id),
                None,
            )
            if existing is not None and self.step is not None:
                return self.step

            activity = SearchActivity(
                run_id=run_id,
                source=_source_label(tool_name),
                query=_query_text(tool_input),
            )
            self.activities.append(activity)
            self.active[run_id] = activity

            step = self.step or self._create_step()
            step.output = self._render()
            if len(self.activities) == 1:
                await step.send()
            else:
                await step.update()
            return step

    async def end(
        self,
        run_id: str,
        *,
        result_count: int | None = None,
        failed: bool = False,
    ) -> StepProtocol | None:
        async with self._lock:
            activity = self.active.pop(run_id, None)
            if activity is None or self.step is None:
                return None
            activity.status = "failed" if failed else "completed"
            activity.result_count = None if failed else result_count
            if failed:
                self.step.is_error = True
            self.step.output = self._render()
            await self.step.update()
            return self.step

    async def finish(self) -> StepProtocol | None:
        """Close the aggregate step once the graph can no longer start searches."""

        async with self._lock:
            if self.step is None or self._closed:
                return self.step
            for activity in self.active.values():
                activity.status = "failed"
                activity.result_count = None
            if self.active:
                self.step.is_error = True
            self.active.clear()
            self.step.name = self._completed_label()
            self.step.output = self._render()
            self.step.end = self.clock()
            self._closed = True
            await self.step.update()
            return self.step

    async def fail_all(self, _output: str | None = None) -> None:
        """Close the aggregate step without exposing provider or tool error text."""

        async with self._lock:
            if self.step is None:
                return
            self._run_failed = True
            for activity in self.active.values():
                activity.status = "failed"
                activity.result_count = None
            self.active.clear()
            self.step.is_error = True
            self.step.name = self._completed_label()
            self.step.output = self._render()
            if not self._closed:
                self.step.end = self.clock()
                self._closed = True
            await self.step.update()
