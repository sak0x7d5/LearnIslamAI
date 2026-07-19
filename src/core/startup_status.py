"""Process-wide, secret-free knowledge-base startup progress."""

from __future__ import annotations

from dataclasses import dataclass

from core.knowledge_base import ProgressEvent


PHASE_LABELS = {
    "validating_corpus": "Validating the English corpus",
    "loading_embeddings": "Loading the local BGE embedding model",
    "index_quran": "Building the Quran search index",
    "index_hadith": "Building the Hadith search index",
    "ready": "Local Quran and Hadith search is ready",
}


@dataclass(frozen=True)
class StartupSnapshot:
    version: int
    state: str
    event: ProgressEvent | None
    failure: str | None = None

    def render(self) -> str:
        if self.state == "failed":
            return (
                "**Local search setup failed safely.**\n\n"
                f"{self.failure or 'The previous local corpus and indexes were retained.'}"
            )
        if self.state == "ready":
            return "**Local Quran and Hadith search is ready.**"

        event = self.event
        if event is None:
            detail = "Starting local corpus validation."
        else:
            detail = PHASE_LABELS.get(event.phase, "Preparing local search")
            if event.total_items > 0:
                detail += f" ({event.current_item}/{event.total_items})"
            if event.detail:
                detail += f" — {event.detail}"
            detail += "."

        return (
            "**Preparing IslamAI locally**\n\n"
            f"{detail}\n\n"
            "This CPU-only first-run setup continues if you switch tabs or reconnect."
        )


class StartupStatus:
    """Keep the latest progress event so every UI session can replay it."""

    def __init__(self) -> None:
        self._version = 0
        self._state = "idle"
        self._event: ProgressEvent | None = None
        self._failure: str | None = None

    def begin(self) -> None:
        self._version += 1
        self._state = "running"
        self._event = ProgressEvent("validating_corpus", 0, 1, "Bundled release")
        self._failure = None

    def record(self, event: ProgressEvent) -> None:
        self._version += 1
        self._event = event
        self._failure = None
        self._state = "ready" if event.phase == "ready" else "running"

    def fail(self, detail: str) -> None:
        self._version += 1
        self._state = "failed"
        self._failure = detail

    def snapshot(self) -> StartupSnapshot:
        return StartupSnapshot(
            version=self._version,
            state=self._state,
            event=self._event,
            failure=self._failure,
        )
