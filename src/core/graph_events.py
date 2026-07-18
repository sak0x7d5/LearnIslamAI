from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import logger
from core.message_utils import extract_root_graph_output
from core.tool_steps import ToolStepPresenter


@dataclass(frozen=True)
class GraphRunResult:
    output: dict[str, Any] | None
    failed: bool = False


async def collect_graph_run(
    graph: Any,
    input_state: dict[str, Any],
    presenter: ToolStepPresenter,
) -> GraphRunResult:
    """Collect the authoritative root result and contain provider/runtime failures."""

    root_output: dict[str, Any] | None = None
    try:
        async for event in graph.astream_events(input_state, version="v2"):
            kind = event.get("event")
            name = str(event.get("name", ""))
            run_id = str(event.get("run_id", ""))
            if kind == "on_tool_start":
                await presenter.start(run_id, name, event.get("data", {}).get("input", {}))
            elif kind == "on_tool_end":
                await presenter.end(run_id)
            elif kind == "on_tool_error":
                await presenter.end(run_id, "The search failed before returning source data.")

            completed = extract_root_graph_output(event)
            if completed is not None:
                root_output = dict(completed)
    except Exception as exc:
        # Provider exceptions can contain request details. Log the class only and
        # expose a fixed message from the UI caller.
        logger.error("Answer generation failed (%s).", type(exc).__name__)
        await presenter.fail_all("The search was interrupted before it could finish safely.")
        return GraphRunResult(None, failed=True)

    return GraphRunResult(root_output)
