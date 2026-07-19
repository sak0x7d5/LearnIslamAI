from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.config import logger
from core.message_utils import extract_root_graph_output
from core.tool_steps import ToolStepPresenter


@dataclass(frozen=True)
class GraphRunResult:
    output: dict[str, Any] | None
    failed: bool = False
    tool_artifacts: tuple[Any, ...] = ()


def _artifact_records(output: Any) -> tuple[Any, ...] | None:
    artifact: Any = None
    if hasattr(output, "artifact"):
        artifact = output.artifact
    elif isinstance(output, Mapping):
        artifact = output.get("artifact")
    elif isinstance(output, tuple) and len(output) == 2:
        artifact = output[1]

    if artifact is None:
        return None
    if isinstance(artifact, (list, tuple)):
        return tuple(artifact)
    if isinstance(artifact, Mapping):
        return (artifact,)
    return None


def _ordered_artifacts(
    run_order: list[str],
    artifacts_by_run: dict[str, tuple[Any, ...]],
) -> tuple[Any, ...]:
    return tuple(record for run_id in run_order for record in artifacts_by_run.get(run_id, ()))


async def collect_graph_run(
    graph: Any,
    input_state: dict[str, Any],
    presenter: ToolStepPresenter,
) -> GraphRunResult:
    """Collect the authoritative root result and contain provider/runtime failures."""

    root_output: dict[str, Any] | None = None
    tool_run_order: list[str] = []
    artifacts_by_run: dict[str, tuple[Any, ...]] = {}
    try:
        async for event in graph.astream_events(input_state, version="v2"):
            kind = event.get("event")
            name = str(event.get("name", ""))
            run_id = str(event.get("run_id", ""))
            if kind == "on_tool_start":
                if run_id not in tool_run_order:
                    tool_run_order.append(run_id)
                await presenter.start(run_id, name, event.get("data", {}).get("input", {}))
            elif kind == "on_tool_end":
                records = _artifact_records(event.get("data", {}).get("output"))
                if records is not None:
                    artifacts_by_run[run_id] = records
                await presenter.end(
                    run_id,
                    result_count=len(records) if records is not None else None,
                )
            elif kind == "on_tool_error":
                await presenter.end(run_id, failed=True)

            completed = extract_root_graph_output(event)
            if completed is not None:
                root_output = dict(completed)

        await presenter.finish()
    except Exception as exc:
        # Provider exceptions can contain request details. Log the class only and
        # expose a fixed message from the UI caller.
        logger.error("Answer generation failed (%s).", type(exc).__name__)
        await presenter.fail_all()
        return GraphRunResult(
            None,
            failed=True,
            tool_artifacts=_ordered_artifacts(tool_run_order, artifacts_by_run),
        )

    return GraphRunResult(
        root_output,
        tool_artifacts=_ordered_artifacts(tool_run_order, artifacts_by_run),
    )
